import copy
from dataclasses import asdict, replace
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'lib'), str(ROOT / 'bin')]
from control_coordinator import ZkCoordinator, coordinator_path, encode, authenticated_client
from control_fencing import FencingError, Owner
from control_runtime import Ec2Fence, LiveBackend, Workload, supervise
from control_observation import SparkIdleObserver, SsmSparkSource
from control_policy import controls_template, observer_template
from control_aws import InstanceAws
spec = importlib.util.spec_from_file_location('control_prepare', ROOT / 'bin/control-fencing.py')
prepare = importlib.util.module_from_spec(spec);spec.loader.exec_module(prepare)
spec = importlib.util.spec_from_file_location('control_observe', ROOT / 'installer/control-observe.py')
guest = importlib.util.module_from_spec(spec);spec.loader.exec_module(guest)


def owners():
    a = Owner('example-project', 'aws-test', 'g-test', 'canary', 'control-a', 'i-00000000000000001', 1)
    return a, replace(a, node='control-b', instance_id='i-00000000000000002', epoch=0)


class Ec2Tests(unittest.TestCase):
    def setUp(self):
        self.old, self.candidate = owners();self.aws = Mock();self.require = Mock()
        self.controls = {o.node: {'instance_id': o.instance_id, 'generation': 'g-test', 'private_ip': '10.0.0.' + str(i),
            'vpc_id': 'vpc-00000001', 'eni_id': 'eni-0000000' + str(i)} for i, o in enumerate((self.old, self.candidate), 1)}
        self.instance = {'InstanceId': self.old.instance_id, 'PrivateIpAddress': '10.0.0.1', 'VpcId': 'vpc-00000001',
            'RootDeviceType': 'ebs', 'Placement': {'AvailabilityZone': 'ap-northeast-2a'},
            'NetworkInterfaces': [{'NetworkInterfaceId': 'eni-00000001'}],
            'Tags': [{'Key': k, 'Value': v} for k, v in {'Project': 'example-project', 'Environment': 'aws-test', 'Node': 'control-a', 'Role': 'control'}.items()]}
        self.states = ['running', 'stopping', 'stopped'];self.stops = []
        def call(service, action, *args):
            if action == 'stop-instances':self.stops.append(args);return {}
            item = copy.deepcopy(self.instance);item['State'] = {'Name': self.states.pop(0) if len(self.states) > 1 else self.states[0]}
            return {'Reservations': [{'OwnerId': '111111111111', 'Instances': [item]}]}
        self.aws.call.side_effect = call
        self.fence = Ec2Fence(self.aws, self.candidate, self.controls, '111111111111', 'ap-northeast-2', self.require, sleep=lambda _: None)

    def test_stop_is_exact_peer_and_confirmed_not_request_acceptance(self):
        self.assertTrue(self.fence.stop_and_confirm_old_instance(self.old))
        self.assertEqual(self.stops, [('--instance-ids', self.old.instance_id)])
        self.assertGreaterEqual(self.require.call_count, 4)

    def test_already_stopping_stopped_or_terminated_never_resends_stop(self):
        for state in ('stopping', 'stopped', 'terminated'):
            with self.subTest(state=state):
                self.states = [state, 'stopped'];self.stops.clear()
                self.assertTrue(self.fence.stop_and_confirm_old_instance(self.old));self.assertFalse(self.stops)

    def test_terminated_identity_may_have_no_network_interface(self):
        self.states = ['terminated'];self.instance.pop('NetworkInterfaces');self.instance.pop('PrivateIpAddress')
        self.assertTrue(self.fence.stop_and_confirm_old_instance(self.old));self.assertFalse(self.stops)

    def test_self_foreign_generation_or_unknown_instance_cannot_be_stopped(self):
        for owner in (replace(self.old, node=self.candidate.node), replace(self.old, generation='another'), replace(self.old, instance_id='i-00000000000000009')):
            with self.subTest(owner=owner):
                with self.assertRaises(FencingError):self.fence.stop_and_confirm_old_instance(owner)
        self.assertFalse(self.stops)

    def test_tag_network_and_region_mismatches_block_before_stop(self):
        mutations = [lambda d: d.update(VpcId='vpc-00000009'), lambda d: d.update(PrivateIpAddress='10.0.0.9'),
            lambda d: d.update(NetworkInterfaces=[]), lambda d: d.update(RootDeviceType='instance-store'),
            lambda d: d.update(Placement={'AvailabilityZone': 'us-east-1a'}), lambda d: d.update(Tags=[])]
        original = copy.deepcopy(self.instance)
        for mutate in mutations:
            self.instance = copy.deepcopy(original);mutate(self.instance)
            with self.assertRaises(FencingError):self.fence.stop_and_confirm_old_instance(self.old)
        self.assertFalse(self.stops)

    def test_unknown_stop_response_is_not_retried(self):
        original = self.aws.call.side_effect
        def call(s, op, *args):
            if op == 'stop-instances':raise TimeoutError('unknown')
            return original(s, op, *args)
        self.aws.call.side_effect = call
        with self.assertRaises(TimeoutError):self.fence.stop_and_confirm_old_instance(self.old)
        self.assertEqual(sum(c.args[1] == 'stop-instances' for c in self.aws.call.call_args_list), 1)

    def test_lease_loss_prevents_stop(self):
        self.require.side_effect = FencingError('lost')
        with self.assertRaises(FencingError):self.fence.stop_and_confirm_old_instance(self.old)
        self.aws.call.assert_not_called()


class SparkObservationTests(unittest.TestCase):
    def setUp(self):
        self.old, self.candidate = owners()
        self.members = [{**dict(zip(('project', 'environment', 'generation'), self.old.namespace[:3])), 'region': 'ap-northeast-2',
            'node': f'spark-0{i}', 'instance_id': f'i-0000000000000001{i}', 'private_ip': f'10.0.1.{i}', 'account_id': '111111111111'} for i in (1, 2, 3)]
        workers = [{'host': m['private_ip'], 'id': 'w' + str(i), 'state': 'ALIVE'} for i, m in enumerate(self.members)]
        self.snapshots = [{**m, 'schema': 1, 'observed_at': 1000, 'nonce': 'a' * 32,
            'master': {'url': 'spark://' + m['private_ip'] + ':7077', 'status': 'ALIVE' if i == 0 else 'STANDBY',
                'activeapps': [], 'activedrivers': [], 'aliveworkers': 3 if i == 0 else 0, 'workers': copy.deepcopy(workers) if i == 0 else [], 'coresused': 0, 'memoryused': 0},
            'worker': {'id': 'w' + str(i), 'masterurl': 'spark://10.0.1.1:7077', 'executors': [], 'coresused': 0, 'memoryused': 0, 'resourcesused': {}},
            'workload_process_counts': {'executor': 0, 'driver': 0, 'python_worker': 0}} for i, m in enumerate(self.members)]
        self.source = Mock();self.source.observe.side_effect = lambda n: copy.deepcopy(self.snapshots[self.members.index(n)])
        self.observer = SparkIdleObserver(self.members, self.source, self.old.namespace, clock=lambda: 1001)

    def test_all_three_actual_schema_members_must_agree_and_be_idle(self):
        self.assertTrue(self.observer.confirm_idle(self.old));self.assertEqual(self.source.observe.call_count, 3)

    def test_absent_and_active_master_worker_or_process_fields_fail(self):
        mutations = [lambda s: s['master'].update(activeapps=None), lambda s: s['master'].update(activedrivers=[{}]),
            lambda s: s['worker'].update(executors=None), lambda s: s['worker'].update(coresused=True),
            lambda s: s['worker'].update(memoryused=1), lambda s: s['workload_process_counts'].update(python_worker=1),
            lambda s: s['worker'].update(resourcesused={'gpu': []}),
            lambda s: s['workload_process_counts'].update(driver=False)]
        original = copy.deepcopy(self.snapshots)
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                self.snapshots = copy.deepcopy(original);mutate(self.snapshots[1])
                with self.assertRaises(FencingError):self.observer.confirm_idle(self.old)

    def test_stale_foreign_missing_or_disagreeing_membership_blocks(self):
        mutations = [lambda s: s.update(observed_at=0), lambda s: s.update(observed_at=1002), lambda s: s.update(generation='old'),
            lambda s: s['worker'].update(id='other'), lambda s: s['worker'].update(masterurl='spark://other:7077'),
            lambda s: s['master'].update(status='ALIVE')]
        original = copy.deepcopy(self.snapshots)
        for mutate in mutations:
            self.snapshots = copy.deepcopy(original);mutate(self.snapshots[1])
            with self.assertRaises(FencingError):self.observer.confirm_idle(self.old)
        self.source.observe.side_effect = TimeoutError('unreachable')
        with self.assertRaises(TimeoutError):self.observer.confirm_idle(self.old)

    def test_duplicate_or_incomplete_node_configuration_is_rejected(self):
        for nodes in (self.members[:2], [self.members[0]] * 3):
            with self.assertRaises(FencingError):SparkIdleObserver(nodes, self.source, self.old.namespace)

    def test_initial_owner_also_requires_idle_observation_before_cas(self):
        coord, ec2, spark = Mock(), Mock(), Mock();spark.confirm_idle.return_value=False
        backend=LiveBackend(coord,ec2,spark)
        self.assertFalse(backend.publish_owner_if_current(Mock(owner=self.old)));coord.publish_owner_if_current.assert_not_called()


class SsmObservationTests(unittest.TestCase):
    def setUp(self):
        self.aws=Mock();self.nonce=None;self.require=Mock();self.attempts=0
        self.node={'instance_id':'i-00000000000000011','observer_document':'example-observe','observer_document_version':'3','observer_document_hash':'a'*64}
        def call(service, op, *args):
            if op=='send-command':
                self.nonce=json.loads(args[args.index('--parameters')+1])['ObservationNonce'][0];return {'Command':{'CommandId':'command-test'}}
            if op=='list-command-invocations':return {'CommandInvocations':[{'CommandId':'command-test','InstanceId':self.node['instance_id'],'Status':'Success','CommandPlugins':[{'Name':'observeSpark','Status':'Success'}]}]}
            return {'CommandId':'command-test','InstanceId':self.node['instance_id'],'Status':'Success','ResponseCode':0,'StandardOutputContent':json.dumps({'nonce':self.nonce})}
        self.aws.call.side_effect=call
        self.source=SsmSparkSource(lambda _:self.aws,self.require,sleep=lambda _:None)

    def test_fresh_nonce_and_pinned_document_are_sent(self):
        value=self.source.observe(self.node);self.assertEqual(value['nonce'],self.nonce)
        args=self.aws.call.call_args_list[0].args;self.assertIn('--document-hash',args);self.assertIn('--document-version',args)

    def test_replay_is_rejected(self):
        original=self.aws.call.side_effect
        def call(service, op, *args):
            if op=='get-command-invocation':return {'CommandId':'command-test','InstanceId':self.node['instance_id'],'Status':'Success','ResponseCode':0,'StandardOutputContent':json.dumps({'nonce':'wrong'})}
            return original(service,op,*args)
        self.aws.call.side_effect=call
        with self.assertRaises(FencingError):self.source.observe(self.node)

    def test_unknown_send_outcome_never_resubmits(self):
        self.aws.call.side_effect=TimeoutError('unknown')
        with self.assertRaises(TimeoutError):self.source.observe(self.node)
        self.assertEqual(self.aws.call.call_count,1)

    def test_different_command_or_instance_response_is_rejected(self):
        original=self.aws.call.side_effect
        for key in ('CommandId','InstanceId'):
            def call(service, op, *args):
                value=original(service,op,*args)
                if op=='get-command-invocation':value[key]='different'
                return value
            self.aws.call.side_effect=call
            with self.assertRaises(FencingError):self.source.observe(self.node)


class CoordinatorTests(unittest.TestCase):
    def setUp(self):
        _,self.candidate=owners();self.client=Mock(connected=True);self.client.client_id=(9,b'');self.acl=['private']
        self.coord=ZkCoordinator(self.client,self.candidate,self.acl)

    def test_suspend_then_reconnect_never_revives_client(self):
        self.coord._connection_state('SUSPENDED');self.coord._connection_state('CONNECTED')
        with self.assertRaises(FencingError):self.coord.acquire()
        self.client.create.assert_not_called()

    def test_missing_owner_or_epoch_is_not_initial_boot(self):
        self.client.get.side_effect=FileNotFoundError('missing')
        with self.assertRaises(FileNotFoundError):self.coord.acquire()
        self.client.create.assert_not_called()

    def test_unknown_or_wrapped_election_children_block(self):
        for children in (['unrecognized'],['a'*32+'-candidate--2147483648'],['a'*32+'-candidate-9999999999']):
            self.client.get_children.return_value=children
            with self.assertRaises(FencingError):self.coord._first()

    def test_election_is_sorted_by_sequence_not_nonce(self):
        first='f'*32+'-candidate-0000000001';second='a'*32+'-candidate-0000000002'
        self.client.get_children.return_value=[second,first];self.assertEqual(self.coord._first(),first)

    def test_namespace_acl_and_persistent_state_are_required(self):
        self.client.get.return_value=(encode({'schema':1,'value':0}),SimpleNamespace(ephemeralOwner=0,version=0))
        self.client.get_acls.return_value=(['world'],None)
        with self.assertRaises(FencingError):self.coord._state()

    def test_owner_publish_requires_a_fresh_previous_read(self):
        with self.assertRaises(FencingError):self.coord.publish_owner_if_current(Mock())

    def test_close_keeps_persistent_owner_epoch(self):
        self.coord.close();self.client.delete.assert_not_called();self.client.set.assert_not_called()
        self.client.stop.assert_called_once();self.client.close.assert_called_once()


class ProcessTests(unittest.TestCase):
    def test_command_contract_rejects_shell_and_all_cluster_mode_spellings(self):
        for argv in (('/bin/sh','-c','sleep 1'),('python','x'),('/bin/echo','--deploy-mode'),
                     ('/bin/echo','--deploy-mode','client','--deploy-mode','cluster'),('/bin/echo','--deploy-mode=cluster')):
            with self.subTest(argv=argv):
                with self.assertRaises(FencingError):Workload(argv,'/tmp')

    def test_suspension_kills_actual_process_and_never_releases_owner(self):
        with tempfile.TemporaryDirectory() as temporary:
            pidfile=Path(temporary)/'pid';coord=Mock(lost=threading.Event());permit=Mock(assert_current=Mock());permit.lease.owner=owners()[0]
            backend=Mock();errors=[]
            def work():
                try:supervise(permit,coord,backend,[Workload((sys.executable,'-c','import os,time;open('+repr(str(pidfile))+',"w").write(str(os.getpid()));time.sleep(30)'),temporary)],grace=.1)
                except FencingError:errors.append(True)
            thread=threading.Thread(target=work);thread.start()
            end=time.monotonic()+5
            while not pidfile.exists() and time.monotonic()<end:time.sleep(.02)
            self.assertTrue(pidfile.exists());pid=int(pidfile.read_text());coord.lost.set();thread.join(timeout=5)
            self.assertFalse(thread.is_alive());self.assertEqual(errors,[True]);coord.release_after_termination.assert_not_called()
            with self.assertRaises(ProcessLookupError):os.kill(pid,0)


class GuestAndPolicyTests(unittest.TestCase):
    def test_runtime_uses_only_instance_profile_and_never_retries_unknown_requests(self):
        with patch('control_aws.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout='aws-cli/2.33.0 Python/3 Linux exe/x86_64')):
            aws=InstanceAws('ap-northeast-2','/usr/local/bin/aws','2.33.0',env={
                'AWS_PROFILE':'other','AWS_ACCESS_KEY_ID':'example-only','AWS_SESSION_TOKEN':'example-only','AWS_MAX_ATTEMPTS':'8','PATH':'/usr/bin'})
        self.assertNotIn('AWS_PROFILE',aws.env);self.assertNotIn('AWS_ACCESS_KEY_ID',aws.env);self.assertNotIn('AWS_SESSION_TOKEN',aws.env)
        self.assertEqual(aws.env['AWS_MAX_ATTEMPTS'],'1');self.assertEqual(aws.env['AWS_CONFIG_FILE'],'/dev/null')

    def test_separate_canary_payload_preserves_foundation_and_excludes_ca_key(self):
        from project import load
        c=load(ROOT/'config/project.example.json');c['generation']='g-canary-test'
        nodes=[{**n,'name':n['name'],'account_id':a['account_id'],'profile':a['profile'],
            'instance_id':f'i-{i:017x}','eni_id':f'eni-{i:017x}'} for i,(a,n) in enumerate(
                [(a,n) for a in c['accounts'] for n in a['nodes']],1)]
        inventory={'nodes':nodes};names=prepare.stack_names(c)
        controls={n['name']:{'instance_id':n['instance_id'],'eni_id':n['eni_id'],'vpc_id':'vpc-00000001'} for n in nodes if n['role']=='control'}
        spark={n['name']:{'instance_id':n['instance_id'],'observer_role_arn':'arn:aws:iam::'+n['account_id']+':role/'+names['observer']+'-observer',
            'observer_document':names['observer']+'-observe','observer_document_version':'1','observer_document_hash':'a'*64} for n in nodes if n['role']=='spark'}
        bindings={'generation':c['generation'],'controls':controls,'spark':spark,'aws_cli':'/usr/local/bin/aws','aws_cli_version':'2.33.0'}
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name in ('installer','lib'):shutil.copytree(ROOT/name,root/name,ignore=shutil.ignore_patterns('__pycache__'))
            bundle=root/'bundle';bundle.mkdir();(bundle/'fixture.whl').write_bytes(b'fixture artifact')
            lock={'packages':[{'name':'fixture','version':'1','filename':'fixture.whl','sha256':prepare.sha(bundle/'fixture.whl')}]}
            for p in (root/'installer/control-fencing.lock.json',bundle/'control-fencing.lock.json'):p.write_text(json.dumps(lock))
            private=root/'.private'/c['environment']/c['generation'];private.mkdir(parents=True)
            (private/'secrets.env').write_text('ZK_HA_PASSWORD=fixture-only\n');(private/'packages.json').write_text('foundation bytes unchanged')
            (private/'pki').mkdir();(private/'pki/ca.crt').write_bytes(b'public cert');(private/'pki/ca.key').write_bytes(b'excluded fixture')
            for name in controls:
                (private/'pki'/name).mkdir()
                for f in ('node.crt','node.key'):(private/'pki'/name/f).write_bytes(b'fixture '+f.encode())
            with patch.object(prepare,'ROOT',root),patch.object(prepare.install,'checked_inventory'):
                broken=copy.deepcopy(bindings);broken['spark']['spark-01']['observer_document_hash']='unknown'
                with self.assertRaises(ValueError):prepare.prepare(c,inventory,broken,'infra-canary',bundle)
                self.assertFalse((private/'control-fencing').exists())
                report=prepare.prepare(c,inventory,bindings,'infra-canary',bundle)
                self.assertEqual(report['control_packages_prepared'],2)
                with self.assertRaises(ValueError):prepare.prepare(c,inventory,bindings,'infra-canary',bundle)
            self.assertEqual((private/'packages.json').read_text(),'foundation bytes unchanged')
            packages=json.loads((private/'control-fencing/infra-canary/packages.json').read_text())
            self.assertEqual({p['node'] for p in packages},{'control-a','control-b'})
            for package in packages:
                with tarfile.open(package['file']) as archive:
                    self.assertNotIn('pki/ca.key',archive.getnames())
                    runtime=json.load(archive.extractfile('runtime.json'));self.assertEqual(runtime['fencing']['workload_kind'],'isolated local canary; no business/S3 workload')
                    self.assertTrue(all(h.endswith(':'+str(prepare.ZK_TLS_PORT)) for h in runtime['fencing']['zk_hosts']))
                    self.assertEqual(prepare.ZK_TLS_PORT,2281)
                    self.assertNotIn('apps',archive.getnames())

    def test_observer_never_reads_configurable_paths_or_commands(self):
        document=observer_template()['Resources']['ObserverDocument']['Properties']['Content']
        self.assertEqual(set(document['parameters']),{'ObservationNonce'})
        self.assertEqual(document['parameters']['ObservationNonce']['interpolationType'],'ENV_VAR')
        command=document['mainSteps'][0]['inputs']['runCommand'][0]['Fn::Sub']
        self.assertIn('IMDS',command);self.assertNotIn('{{ ObservationNonce }}',command)

    def test_policies_cannot_start_terminate_self_stop_or_send_arbitrary_shell(self):
        controls=controls_template();text=json.dumps(controls)
        self.assertNotIn('StartInstances',text);self.assertNotIn('TerminateInstances',text);self.assertNotIn('ResourceTag/Generation',text)
        statement=controls['Resources']['ControlAFencePolicy']['Properties']['PolicyDocument']['Statement'][1]
        self.assertIn('${ControlBInstanceId}',statement['Resource']['Fn::Sub'])
        observer=observer_template();role=observer['Resources']['ObserverRole']['Properties']
        self.assertEqual(len(role['AssumeRolePolicyDocument']['Statement'][0]['Principal']['AWS']),2)
        self.assertNotIn('AWS-RunShellScript',json.dumps(role));self.assertNotIn('iam:PassRole',json.dumps(role))

    def test_corrupted_bundle_is_blocked_before_private_state_creation(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);(folder/'control-fencing.lock.json').write_text('{}')
            with self.assertRaises(ValueError):prepare.bundle_checked(folder)

    def test_actual_worker_schema_has_no_driver_field_requirement(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);marker=root/'marker';proc=root/'proc';proc.mkdir()
            expected={'project':'example','environment':'aws-test','generation':'g-test','node':'spark-01','account_id':'111111111111','instance_id':'i-00000000000000011','private_ip':'10.0.0.1','region':'ap-northeast-2'}
            marker.write_text(json.dumps({k:expected[k] for k in ('project','environment','generation','node')}))
            identity={'accountId':expected['account_id'],'instanceId':expected['instance_id'],'privateIp':expected['private_ip'],'region':expected['region']}
            master={k:[] for k in ('activeapps','activedrivers','workers')};master.update(url='spark://10.0.0.1:7077',status='STANDBY',aliveworkers=0,coresused=0,memoryused=0)
            worker={'id':'w1','masterurl':'spark://10.0.0.2:7077','executors':[],'coresused':0,'memoryused':0,'resourcesused':{}}
            value=guest.collect(expected,'a'*32,fetch=lambda:identity,http=lambda _,p:master if p==8080 else worker,marker=marker,proc=proc)
            self.assertEqual(value['worker'],worker);self.assertEqual(value['workload_process_counts'],{'executor':0,'driver':0,'python_worker':0})


if __name__ == '__main__':unittest.main()
