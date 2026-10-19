"""Failure/resume/ownership tests for full create/destroy. No AWS calls."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch,Mock

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'bin'),str(ROOT/'lib')]
import manage,project,templates
from awscli import AwsError


class PurgeAws:
    def __init__(self,tags,versions=None,error=False):
        self.tags=tags;self.versions=versions or [];self.error=error;self.calls=[];self.batches=[];self.upload=True
    def call(self,service,operation,*args):
        self.calls.append(operation)
        if operation=='get-bucket-tagging':return {'TagSet':self.tags}
        if operation=='list-multipart-uploads':return {'Uploads':[{'Key':'upload','UploadId':'u'}]} if self.upload else {}
        if operation=='abort-multipart-upload':self.upload=False;return {}
        if operation=='list-object-versions':return {'Versions':self.versions,'DeleteMarkers':[{'Key':'marker','VersionId':'m'}]} if self.versions else {}
        if operation=='delete-objects':
            p=Path(args[args.index('--delete')+1].removeprefix('file://'));batch=json.loads(p.read_text())['Objects'];self.batches.append(batch)
            if self.error:return {'Errors':[{'Code':'AccessDenied'}]}
            keys={(v['Key'],v['VersionId']) for v in batch};self.versions=[v for v in self.versions if (v['Key'],v['VersionId']) not in keys]
            return {}
        raise AssertionError(operation)


class PurgeSafety(unittest.TestCase):
    def setUp(self):
        self.c=project.load(ROOT/'config/project.example.json');self.a=self.c['accounts'][0]
        self.name=project.artifact_bucket(self.c,self.a);self.tags=templates.tags(self.c)
    def test_foreign_bucket_never_touched(self):
        aws=PurgeAws(self.tags)
        with self.assertRaises(AwsError):manage.purge_bucket(aws,self.c,self.a,'original-music-source')
        self.assertEqual(aws.calls,[])
    def test_tag_mismatch_never_deletes_data(self):
        aws=PurgeAws([{'Key':'Project','Value':'another-project'}])
        with self.assertRaises(AwsError):manage.purge_bucket(aws,self.c,self.a,self.name)
        self.assertEqual(aws.calls,['get-bucket-tagging'])
    def test_versions_markers_and_uploads_removed_in_batches(self):
        aws=PurgeAws(self.tags,[{'Key':'key-'+str(i),'VersionId':str(i)} for i in range(2001)])
        with tempfile.TemporaryDirectory() as tmp,patch.object(manage,'ROOT',Path(tmp)):
            self.assertTrue(manage.purge_bucket(aws,self.c,self.a,self.name))
        self.assertFalse(aws.upload);self.assertEqual(aws.versions,[])
        self.assertTrue(all(len(b)<=1000 for b in aws.batches))
        self.assertTrue(any(v['Key']=='marker' for b in aws.batches for v in b))
        self.assertNotIn('delete-bucket',aws.calls)
    def test_partial_s3_failure_stops_teardown(self):
        aws=PurgeAws(self.tags,[{'Key':'k','VersionId':'v'}],error=True)
        with tempfile.TemporaryDirectory() as tmp,patch.object(manage,'ROOT',Path(tmp)):
            with self.assertRaises(AwsError):manage.purge_bucket(aws,self.c,self.a,self.name)
        self.assertNotIn('delete-bucket',aws.calls)


class PreflightAws:
    def __init__(self,c,a,missing):self.c=c;self.a=a;self.missing=missing;self.calls=[]
    def call(self,service,operation,*args):
        self.calls.append(operation)
        if operation=='describe-stacks':return {'Stacks':[{'StackId':'stack-id','StackStatus':'CREATE_COMPLETE','Tags':templates.tags(self.c)}]}
        if operation=='get-template':
            t=templates.bootstrap(self.c,self.a)
            if self.missing:t['Resources'].pop('PeeringBoundary',None);t['Resources']['ExecutionRole']['Properties']['Policies'][0]['PolicyDocument']['Statement']=[]
            return {'TemplateBody':t}
        if operation=='get-service-quota':return {'Quota':{'Value':640}}
        if operation=='describe-availability-zones':return {'AvailabilityZones':[{'ZoneId':'apne2-az'+str(i),'State':'available'} for i in range(1,4)]}
        if operation=='describe-instance-types':return {'InstanceTypes':[{'InstanceType':t,'Hypervisor':'nitro','VCpuInfo':{'DefaultVCpus':2},'MemoryInfo':{'SizeInMiB':m},'ProcessorInfo':{'SupportedArchitectures':['x86_64']}} for t,m in [('t3.small',2048),('t3.medium',4096),('t3.large',8192)]]}
        if operation=='describe-instance-type-offerings':return {'InstanceTypeOfferings':[{'InstanceType':t,'Location':'apne2-az'+str(i)} for t in ('t3.small','t3.medium','t3.large') for i in range(1,4)]}
        if operation=='describe-vpcs':return {'Vpcs':[]}
        raise AssertionError('Unexpected operation: '+operation)


class LifecycleSafety(unittest.TestCase):
    def setUp(self):self.c=project.load(ROOT/'config/project.example.json')
    def test_every_control_is_terminated_before_data_and_s3(self):
        steps=manage.teardown_steps(self.c);controls=[steps.index(('encore1','compute-'+name)) for name in ('control-a','control-b')]
        others=[i for i,(_,k) in enumerate(steps) if k.startswith('compute-') and not k.startswith('compute-control')]
        self.assertLess(max(controls),min(others))
        self.assertLess(max(others),min(i for i,(_,k) in enumerate(steps) if k=='storage'))
        self.assertFalse(any(k=='bootstrap' for _,k in steps))
    def test_destroy_waits_for_control_termination_before_any_data_delete(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager=object.__new__(manage.Manager);manager.c=self.c;manager.run=Path(tmp);events=[]
            manager.preflight=lambda **_:None;manager.discover=lambda:{};manager.transition=lambda state:events.append(('state',state))
            def delete(profile,kind):
                events.append(('delete',kind));return 'i-'+kind if kind.startswith('compute-') else None
            manager.delete_stack=delete;manager.wait_terminated=lambda profile,iid:events.append(('terminated',iid))
            manager.residuals=lambda:{a['profile']:[] for a in self.c['accounts']}
            aws=Mock();aws.call.side_effect=AwsError('NoSuchBucket');manager.aws=lambda _:aws
            manager.destroy(project.prefix(self.c))
            last_control=max(events.index(('terminated','i-compute-'+n)) for n in ('control-a','control-b'))
            first_data=min(i for i,(action,kind) in enumerate(events) if action=='delete' and kind.startswith('compute-') and not kind.startswith('compute-control-'))
            self.assertLess(last_control,first_data)
            self.assertEqual(events[-1],('state','destroyed'))
    def test_destroy_requires_environment_confirmation(self):
        manager=object.__new__(manage.Manager);manager.c=self.c
        with self.assertRaises(ValueError):manager.destroy('another-environment')
    def test_replace_or_remove_never_executes_from_create(self):
        for action,replacement in [('Remove','False'),('Modify','True'),('Modify','Conditional')]:
            with self.assertRaises(AwsError):manage.validate_changes('network',{'Changes':[{'ResourceChange':{'Action':action,'Replacement':replacement}}]})
        with self.assertRaises(AwsError):manage.validate_changes('compute-control-a',{'Changes':[{'ResourceChange':{'Action':'Modify','Replacement':'False'}}]})
    def test_missing_bootstrap_permissions_fail_before_paid_operations(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(manage,'ROOT',Path(tmp)):
            source=Path(tmp)/'config.json';source.write_text(json.dumps(self.c));manager=manage.Manager(self.c,source,False)
            clients={a['profile']:PreflightAws(self.c,a,a['profile']=='encore2') for a in self.c['accounts']}
            manager.aws=lambda p:clients[p]
            manager.ensure=Mock()
            with self.assertRaisesRegex(ValueError,'one-time bootstrap update needed'):manager.create()
            manager.ensure.assert_not_called()
            self.assertEqual(json.loads(manager.current.read_text())['state'],'preflight_failed')
            self.assertFalse(any(op in ('create-change-set','execute-change-set','run-instances') for a in clients.values() for op in a.calls))
            # User can fix missing inputs after preflight failure, without a false active-config lock.
            fixed=copy.deepcopy(self.c);fixed['ami_id']='ami-0123456789abcdef0';source.write_text(json.dumps(fixed))
            again=manage.Manager(fixed,source,False);self.assertIsNone(again.run)
    def test_source_edit_does_not_change_destroyed_resource_scope(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(manage,'ROOT',Path(tmp)):
            source=Path(tmp)/'config.json';source.write_text(json.dumps(self.c));first=manage.Manager(self.c,source,False);first.start();first.transition('ready')
            original=first.c['generation'];source.write_text(source.read_text()+'\n')
            again=manage.Manager(self.c,source,False)
            self.assertTrue(again.input_changed);self.assertEqual(again.c['generation'],original)
            with self.assertRaisesRegex(ValueError,'Active input changed'):again.create()
    def test_unknown_create_outcome_is_not_resubmitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager=object.__new__(manage.Manager);manager.c=self.c;manager.run=Path(tmp)
            name=project.stack_name(self.c,'encore1','network');folder=Path(tmp)/'templates';folder.mkdir()
            (folder/(name+'.json')).write_text(json.dumps(templates.network(self.c,self.c['accounts'][0])))
            record=Path(tmp)/'encore1-network.json';record.write_text(json.dumps({'token':'stable','status':'unknown create outcome'}))
            api=Mock()
            with patch.object(manage.infra,'stack_spec',return_value=(api,name,{},name,False)),patch.object(manage.infra,'get_stack',return_value=None):
                with self.assertRaisesRegex(AwsError,'unknown'):manager.ensure('encore1','network')
            api.call.assert_not_called()
    def test_unknown_execute_outcome_is_not_resubmitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager=object.__new__(manage.Manager);manager.c=self.c;manager.run=Path(tmp)
            name=project.stack_name(self.c,'encore1','network');folder=Path(tmp)/'templates';folder.mkdir()
            (folder/(name+'.json')).write_text(json.dumps(templates.network(self.c,self.c['accounts'][0])))
            (Path(tmp)/'encore1-network.json').write_text(json.dumps({'token':'t','change_set_id':'cs','execution_requested':True}))
            api=Mock();api.call.side_effect=[{'Status':'CREATE_COMPLETE','ExecutionStatus':'AVAILABLE','StackName':name,'Changes':[]},{'OperationEvents':[]}]
            with patch.object(manage.infra,'stack_spec',return_value=(api,name,{},name,False)),patch.object(manage.infra,'get_stack',return_value=None):
                with self.assertRaisesRegex(AwsError,'unknown'):manager.ensure('encore1','network')
            self.assertFalse(any(call.args[1]=='execute-change-set' for call in api.call.call_args_list))
    def test_unknown_delete_outcome_is_not_resubmitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager=object.__new__(manage.Manager);manager.c=self.c;manager.run=Path(tmp)
            (Path(tmp)/'delete-encore1-network.json').write_text(json.dumps({'delete_requested':True}))
            api=Mock();manager.aws=lambda _:api
            with patch.object(manage.infra,'get_stack',return_value={'StackStatus':'CREATE_COMPLETE'}):
                with self.assertRaisesRegex(AwsError,'unknown'):manager.delete_stack('encore1','network')
            api.call.assert_not_called()
    def test_peering_boundary_is_kept_outside_disposable_network(self):
        a=self.c['accounts'][1];boot=templates.bootstrap(self.c,a);net=templates.network(self.c,a)
        self.assertEqual(boot['Resources']['PeeringAccepter']['Properties']['PermissionsBoundary'],{'Ref':'PeeringBoundary'})
        self.assertNotIn('PeeringBoundary',net['Resources'])
        self.assertIn('AccepterPolicy',net['Resources'])
        statement=net['Resources']['AccepterPolicy']['Properties']['PolicyDocument']['Statement'][1]
        self.assertIn('${Vpc}',statement['Condition']['ArnEquals']['ec2:AccepterVpc']['Fn::Sub'])


if __name__=='__main__':unittest.main()
