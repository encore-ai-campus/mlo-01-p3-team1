"""Offline bundle integrity and fail-closed promotion tests; no AWS access."""
import copy
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'lib'),str(ROOT/'installer'),str(ROOT/'installer/core/lib')]
import control_fencing as fence
import connectors
from integration_scope import checkpoint_paths
sys.path.insert(0,str(ROOT/'bin'))
import install,project,integration_preparation


class ConnectorIntegrity(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.home=self.root/'spark home';(self.home/'jars').mkdir(parents=True)
        self.bundle=self.root/'bundle';self.bundle.mkdir()
        self.versions=json.loads((ROOT/'installer/core/versions.json').read_text())
        (self.root/'core').mkdir();(self.root/'core/versions.json').write_text(json.dumps(self.versions))
        (self.home/'jars/base.jar').write_bytes(b'verified distribution fixture')
        self.manifest={'schema_version':2,'spark_version':self.versions['spark']['version'],'hadoop_version':self.versions['spark']['hadoop'],
            'coordinates':[self.versions['connectors'][k]['coordinate'] for k in ('kafka','s3a')],
            'provided_dependencies':self.versions['connectors'].get('provided_dependencies',{}),
            'distribution_jars':connectors.distribution(self.home),'jars':[]}
        for i,coord in enumerate(self.manifest['coordinates']):
            p=self.bundle/('connector-'+str(i)+'.jar');p.write_bytes(('complete fixture '+str(i)).encode())
            self.manifest['jars'].append({'filename':p.name,'coordinate':coord,'sha256':connectors.digest(p)})
        self.save();self.reviewed=self.root/'reviewed.json';self.reviewed.write_text(json.dumps(self.manifest))

    def save(self):
        (self.bundle/'connectors.lock.json').write_text(json.dumps(self.manifest))

    def test_valid_bundle_and_exact_distribution_pass(self):
        value,sources=connectors.validate_bundle(self.bundle,self.home,self.reviewed)
        self.assertEqual(value,self.manifest);self.assertEqual(len(sources),2)

    def test_corrupt_last_jar_does_not_publish_any_jar(self):
        (self.bundle/self.manifest['jars'][-1]['filename']).write_bytes(b'tampered')
        with patch.object(connectors,'ROOT',self.root/'core'),self.assertRaises(ValueError):
            shutil.copyfile(self.reviewed,self.root/'connectors.lock.json');connectors.install(self.bundle,self.home)
        self.assertEqual([p.name for p in (self.home/'jars').iterdir()],['base.jar'])

    def test_baseline_change_blocks_install(self):
        (self.home/'jars/base.jar').write_bytes(b'drift')
        with self.assertRaisesRegex(ValueError,'distribution differs'):connectors.validate_bundle(self.bundle,self.home)

    def test_unknown_extra_classpath_jar_is_rejected(self):
        (self.home/'jars/unreviewed.jar').write_bytes(b'unknown version')
        with self.assertRaisesRegex(ValueError,'extra Spark jar'):connectors.validate_bundle(self.bundle,self.home)

    def test_symlink_destination_is_rejected_even_if_hash_matches(self):
        source=self.bundle/self.manifest['jars'][0]['filename'];(self.home/'jars'/source.name).symlink_to(source)
        with self.assertRaises(ValueError):connectors.validate_bundle(self.bundle,self.home)

    def test_reviewed_lock_cannot_be_changed_by_bundle(self):
        self.manifest['jars'][0]['sha256']='0'*64;self.save()
        with self.assertRaisesRegex(ValueError,'reviewed'):connectors.validate_bundle(self.bundle,self.home,self.reviewed)

    def test_missing_connector_root_is_rejected(self):
        self.manifest['jars'].pop();self.save()
        with self.assertRaisesRegex(ValueError,'root missing'):connectors.validate_bundle(self.bundle,self.home)

    def test_traversal_and_distribution_replacement_are_rejected(self):
        for name in ('../outside.jar','base.jar'):
            with self.subTest(name=name):
                self.manifest['jars'][0]['filename']=name;self.save()
                with self.assertRaises(ValueError):connectors.validate_bundle(self.bundle,self.home)

    def test_install_is_idempotent_and_preserves_distribution(self):
        shutil.copyfile(self.reviewed,self.root/'connectors.lock.json')
        before=connectors.digest(self.home/'jars/base.jar')
        with patch.object(connectors,'ROOT',self.root/'core'):
            connectors.install(self.bundle,str(self.home));connectors.install(self.bundle,str(self.home))
        self.assertEqual(connectors.digest(self.home/'jars/base.jar'),before)
        self.assertEqual(len(list((self.home/'jars').glob('*.jar'))),3)

    def test_resolution_isolates_settings_and_preserves_space_arguments(self):
        home=self.root/'resolution home';(home/'jars').mkdir(parents=True)
        def jar(path,group,artifact,version):
            path.parent.mkdir(parents=True,exist_ok=True)
            with zipfile.ZipFile(path,'w') as z:z.writestr('META-INF/maven/'+group+'/'+artifact+'/pom.properties','groupId='+group+'\nartifactId='+artifact+'\nversion='+version+'\n')
        h=self.versions['spark']['hadoop'];jar(home/'jars'/('hadoop-client-api-'+h+'.jar'),'org.apache.hadoop','hadoop-client-api',h)
        jar(home/'jars/slf4j-api-2.0.17.jar','org.slf4j','slf4j-api','2.0.17')
        jar(home/'jars/scala-library-2.13.17.jar','org.scala-lang','scala-library','2.13.17')
        # The actual snappy distribution JAR has no Maven pom.properties.
        with zipfile.ZipFile(home/'jars/snappy-java-1.1.10.8.jar','w') as z:z.writestr('fixture','no Maven metadata')
        def resolve(argv,**kwargs):
            self.assertNotIn('MAVEN_ARGS',kwargs['env'])
            settings=Path(argv[argv.index('--settings')+1]).read_text();self.assertIn('<mirrorOf>*</mirrorOf>',settings);self.assertIn('https://repo.maven.apache.org/maven2',settings)
            pom=Path(argv[argv.index('-f')+1]);self.assertIn('2.0.17',pom.read_text())
            repo=Path(next(a.split('=',1)[1] for a in argv if a.startswith('-Dmaven.repo.local=')))
            paths=[]
            for coord in self.manifest['coordinates']:
                group,artifact,version=coord.split(':');p=repo/group.replace('.','/')/artifact/version/(artifact+'-'+version+'.jar');jar(p,group,artifact,version);paths.append(str(p))
            Path(next(a.split('=',1)[1] for a in argv if a.startswith('-Dmdep.outputFile='))).write_text(connectors.os.pathsep.join(paths))
            return Mock(returncode=0)
        target=self.root/'new bundle'
        with patch.object(connectors.shutil,'which',return_value='mvn'),patch.object(connectors.subprocess,'run',side_effect=resolve),patch.dict(connectors.os.environ,{'MAVEN_ARGS':'unreviewed mirror arguments'}):
            connectors.prepare(home,target,self.root/'resolution.log')
        connectors.validate_bundle(target,home)


class ControlPromotion(unittest.TestCase):
    def setUp(self):
        self.old=fence.Owner('example-project','aws-dev','generation-test','weather','control-a','i-00000000000000001',1)
        self.lease=fence.Lease(replace(self.old,node='control-b',instance_id='i-00000000000000002',epoch=2),'a'*32)
        self.backend=Mock();self.backend.lease_is_current.return_value=True;self.backend.previous_owner.return_value=self.old
        self.backend.stop_and_confirm_old_instance.return_value=True;self.backend.old_spark_work_is_gone.return_value=True;self.backend.publish_owner_if_current.return_value=True

    def test_old_ec2_and_spark_termination_precede_publication(self):
        permit=fence.authorize(self.lease,self.backend);permit.assert_current()
        names=[x[0] for x in self.backend.method_calls]
        self.assertLess(names.index('stop_and_confirm_old_instance'),names.index('old_spark_work_is_gone'))
        self.assertLess(names.index('old_spark_work_is_gone'),names.index('publish_owner_if_current'))

    def test_unknown_fence_or_executor_state_blocks_promotion(self):
        for method in ('stop_and_confirm_old_instance','old_spark_work_is_gone'):
            for value in (False,None,'true'):
                with self.subTest(method=method,value=value):
                    backend=copy.deepcopy(self.backend);getattr(backend,method).return_value=value
                    with self.assertRaises(fence.FencingError):fence.authorize(self.lease,backend)
                    backend.publish_owner_if_current.assert_not_called()

    def test_lost_lease_during_fencing_never_publishes(self):
        self.backend.lease_is_current.side_effect=[True,True,False]
        with self.assertRaises(fence.FencingError):fence.authorize(self.lease,self.backend)
        self.backend.publish_owner_if_current.assert_not_called()

    def test_missing_coordinator_observation_is_not_first_boot(self):
        self.backend.previous_owner.side_effect=TimeoutError('coordinator unavailable')
        with self.assertRaises(TimeoutError):fence.authorize(self.lease,self.backend)
        self.backend.stop_and_confirm_old_instance.assert_not_called();self.backend.publish_owner_if_current.assert_not_called()

    def test_wrong_namespace_or_stale_epoch_cannot_fence_an_instance(self):
        for owner in (replace(self.old,project='another'),replace(self.old,generation='another'),replace(self.old,epoch=3),replace(self.old,query='other')):
            self.backend.previous_owner.return_value=owner
            with self.assertRaises(fence.FencingError):fence.authorize(self.lease,self.backend)
        self.backend.stop_and_confirm_old_instance.assert_not_called()

    def test_self_fencing_and_failed_owner_cas_are_rejected(self):
        self.backend.previous_owner.return_value=replace(self.lease.owner,epoch=1)
        with self.assertRaises(fence.FencingError):fence.authorize(self.lease,self.backend)
        self.backend.stop_and_confirm_old_instance.assert_not_called()
        self.backend.previous_owner.return_value=self.old;self.backend.publish_owner_if_current.return_value=False
        with self.assertRaises(fence.FencingError):fence.authorize(self.lease,self.backend)

    def test_authenticated_empty_previous_owner_is_initial_install_only(self):
        self.backend.previous_owner.return_value=None
        fence.authorize(self.lease,self.backend)
        self.backend.stop_and_confirm_old_instance.assert_not_called();self.backend.publish_owner_if_current.assert_called_once()

    def test_permit_requires_a_current_lease(self):
        permit=fence.authorize(self.lease,self.backend);self.backend.lease_is_current.return_value=False
        with self.assertRaises(fence.FencingError):permit.assert_current()


class CheckpointNamespace(unittest.TestCase):
    def setUp(self):
        self.runtime={'aws':{'project':'example-project','environment':'aws-dev','generation':'g-test'},'env':{'ENVIRONMENT':'aws','S3_BUCKET':'example-project-aws-dev-111111111111-checkpoints','S3_CHECKPOINT_PREFIX':'aws/aws-dev/g-test/'}}

    def test_test_prefix_is_unique_and_never_business_checkpoint(self):
        first=checkpoint_paths(self.runtime,'a'*32);second=checkpoint_paths(self.runtime,'b'*32)
        self.assertNotEqual(first['checkpoint'],second['checkpoint'])
        self.assertIn('/aws/aws-dev/g-test/_infra-tests/checkpoint-',first['checkpoint'])

    def test_wrong_generation_and_traversal_are_rejected(self):
        for prefix in ('aws/aws-dev/old/','aws/aws-dev/g-test/../','aws/aws-dev/g-test'):
            self.runtime['env']['S3_CHECKPOINT_PREFIX']=prefix
            with self.assertRaises(ValueError):checkpoint_paths(self.runtime,'a'*32)

    def test_local_environment_and_implicit_run_id_are_rejected(self):
        for run_id in ('','../test','A'*32):
            with self.assertRaises(ValueError):checkpoint_paths(self.runtime,run_id)
        self.runtime['env']['ENVIRONMENT']='local'
        with self.assertRaises(ValueError):checkpoint_paths(self.runtime,'a'*32)

    def test_original_music_and_other_project_buckets_are_rejected(self):
        for bucket in ('original-music-source','other-project-aws-dev-111111111111-checkpoints'):
            self.runtime['env']['S3_BUCKET']=bucket
            with self.assertRaises(ValueError):checkpoint_paths(self.runtime,'a'*32)


class IntegrationPlanning(unittest.TestCase):
    setUp=ConnectorIntegrity.setUp
    save=ConnectorIntegrity.save
    def test_offline_plan_does_not_claim_installation_or_fencing(self):
        (self.root/'installer').mkdir();shutil.copyfile(self.reviewed,self.root/'installer/connectors.lock.json')
        with patch('awscli.Aws') as aws:
            report=integration_preparation.plan(project.load(ROOT/'config/project.example.json'),self.bundle,root=self.root)
        aws.assert_not_called()
        self.assertTrue(report['connector_bundle_verified']);self.assertEqual(len(report['connector_install_targets']),5)
        self.assertFalse(report['ready_for_full_integration']);self.assertTrue(report['live_fencing_controller_implemented']);self.assertFalse(report['live_fencing_controller_installed']);self.assertFalse(report['physical_control_fencing_verified'])
        self.assertFalse(report['business_application_source_required_for_preparation'])

    def test_invalid_bundle_fails_before_private_payload_creation(self):
        (self.bundle/self.manifest['jars'][-1]['filename']).write_bytes(b'tampered')
        with patch.object(install,'ROOT',self.root),patch.object(install,'blockers',return_value=[]),patch.object(install,'Aws') as aws:
            with self.assertRaises((ValueError,OSError)):install.prepare({},self.root/'nonexistent-inventory.json',self.bundle)
        self.assertFalse((self.root/'.private').exists());aws.assert_not_called()

    def test_connector_and_checkpoint_dispatch_require_explicit_bundle(self):
        c={'environment':'aws-test','generation':'g-test'};packages=self.root/'.private/aws-test/g-test/packages.json';packages.parent.mkdir(parents=True)
        packages.write_text(json.dumps([{'node':'spark-01','connector_lock_sha256':None}]))
        (self.root/'installer').mkdir();shutil.copyfile(self.reviewed,self.root/'installer/connectors.lock.json')
        with patch.object(install,'ROOT',self.root),patch.object(install,'inventory') as inventory:
            for stage in ('connectors','checkpoint-smoke'):
                with self.assertRaisesRegex(ValueError,'not explicitly included'):install.send(c,'spark-01',stage,self.root/'receipt.json',None)
        inventory.assert_not_called()

    def test_checkpoint_probe_targets_only_spark_nodes(self):
        self.assertTrue(install.stage_allowed('checkpoint-smoke',{'role':'spark'}))
        for role in ('control','kafka','es','postgresql','mongodb','advertising'):
            with self.subTest(role=role):self.assertFalse(install.stage_allowed('checkpoint-smoke',{'role':role}))


if __name__=='__main__':unittest.main()
