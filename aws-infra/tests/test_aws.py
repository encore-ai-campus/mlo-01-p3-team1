"""Offline failure-path tests: no AWS mutation, guest installation or local VM access."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'lib'),str(ROOT/'bin')]
import project,templates,infra,install


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
identity=module('aws_identity',ROOT/'installer/aws-identity.py')
disk=module('disk',ROOT/'installer/init-disk.py')
masters=module('masters',ROOT/'installer/spark-master-health.py')
guest_preflight=module('guest_preflight',ROOT/'installer/core/lib/preflight.py')
sys.path.insert(0,str(ROOT/'installer/core/lib'))
guest_health=module('guest_health',ROOT/'installer/core/lib/health.py')
sys.path.pop(0)


class Topology(unittest.TestCase):
    def setUp(self):self.c=project.load(ROOT/'config/project.example.json')
    def load(self,c):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'c.json';p.write_text(json.dumps(c));return project.load(p)
    def test_approved_counts(self):
        self.assertEqual(infra.plan(self.c)['counts'],{'accounts':5,'vpcs':5,'ec2':14,'physical_azs':3,'nat_gateways':5,'peerings':7})
    def test_96_hour_account_budget(self):
        b=self.c['budget']
        self.assertEqual(b['duration_hours'],96)
        self.assertEqual(b['per_account_usd_cap'],45)
        self.assertEqual(b['total_usd_cap'],200)
        self.assertEqual(b['daily_ec2_hours'],24)
        self.assertTrue(b['estimate_accepted'])
        self.assertNotIn('budget.total_usd_cap',project.blockers(self.c))
    def test_budget_cap_consistency(self):
        self.c['budget']['total_usd_cap']=100
        self.assertIn('budget.total_usd_cap must cover all per-account caps',project.blockers(self.c))
    def test_nonuniform_caps_fit_total(self):
        self.assertEqual(project.account_budget_cap(self.c,'encore5'),20)
        self.assertNotIn('budget.total_usd_cap must cover all per-account caps',project.blockers(self.c))
    def test_invalid_account_budget_rejected(self):
        self.c['budget']['account_usd_caps']['encore6']=20
        self.assertTrue(any('must name only the five approved profiles' in x for x in project.blockers(self.c)))
    def test_missing_standard_credit_blocks(self):
        a=self.c['accounts'][1];n=a['nodes'][0];n.pop('credit_mode')
        self.assertIn('kafka-01.credit_mode (selected budget requires standard)',project.blockers(self.c))
        with self.assertRaises(ValueError):templates.compute(self.c,a,n)
    def test_missing_duration_blocks(self):
        self.c['budget']['duration_hours']=None
        self.assertIn('budget.duration_hours',project.blockers(self.c))
    def test_numeric_account_rejected(self):
        self.c['accounts'][3]['account_id']=84375572210
        with self.assertRaises(ValueError):self.load(self.c)
    def test_colliding_cidr_rejected(self):
        self.c['accounts'][1]['cidr']=self.c['accounts'][0]['cidr']
        with self.assertRaises(ValueError):self.load(self.c)
    def test_missing_peer_rejected(self):
        self.c['peering_pairs'].pop()
        with self.assertRaises(ValueError):self.load(self.c)
    def test_single_data_az_rejected(self):
        n=self.c['accounts'][2]['nodes'][0];n['az_slot']='a';n['private_ip']='10.82.16.10'
        with self.assertRaises(ValueError):self.load(self.c)
    def test_same_control_az_rejected(self):
        n=self.c['accounts'][0]['nodes'][1];n['az_slot']='a';n['private_ip']='10.80.16.11'
        with self.assertRaises(ValueError):self.load(self.c)
    def test_duplicate_az_ids_rejected(self):
        self.c['az_ids']={'a':'apne2-az1','b':'apne2-az1','c':'apne2-az3'}
        with self.assertRaises(ValueError):self.load(self.c)
    def test_unselected_specs_blocked(self):
        self.c['accounts'][1]['nodes'][0]['instance_type']=None
        self.assertIn('ami_id (verified Canonical Ubuntu 24.04 amd64)',project.blockers(self.c))
        self.assertTrue(any(x.startswith('kafka-01.instance_type') for x in project.blockers(self.c)))
    def test_reserved_ip_rejected(self):
        self.c['accounts'][0]['nodes'][0]['private_ip']='10.80.16.3'
        with self.assertRaises(ValueError):self.load(self.c)
    def test_volume_encryption_and_eni_lifecycle(self):
        t=templates.compute(self.c,self.c['accounts'][0],self.c['accounts'][0]['nodes'][0])
        p=t['Resources']['Instance']['Properties']
        self.assertTrue(all(x['Ebs']['Encrypted'] for x in p['BlockDeviceMappings']))
        self.assertNotIn('DeleteOnTermination',p['NetworkInterfaces'][0])
        self.assertEqual(p['MetadataOptions']['HttpTokens'],'required')
    def test_checkpoint_scope(self):
        p=templates.storage(self.c,self.c['accounts'][0])['Resources']['CheckpointsPolicy']['Properties']['PolicyDocument']['Statement']
        allow=[s for s in p if s['Effect']=='Allow']
        principals=allow[0]['Principal']['AWS']
        self.assertEqual(len(principals),5)
        self.assertFalse(any('mongodb' in p or 'kafka' in p for p in principals))
        self.assertTrue(allow[-1]['Resource'].endswith('/aws/aws-dev/*'))
    def test_passrole_scoped(self):
        t=templates.bootstrap(self.c,self.c['accounts'][1])
        p=t['Resources']['ExecutionRole']['Properties']['Policies'][0]['PolicyDocument']['Statement']
        s=next(s for s in p if 'iam:PassRole' in s['Action'])
        self.assertEqual(len(s['Resource']),3)
        self.assertNotIn('*',str(s['Resource']))
        self.assertEqual(s['Condition']['StringEquals']['iam:PassedToService'],'ec2.amazonaws.com')
    def test_cfn_iam_mutation_has_exact_targets(self):
        for account in self.c['accounts']:
            t=templates.bootstrap(self.c,account)
            p=t['Resources']['ExecutionRole']['Properties']['Policies'][0]['PolicyDocument']['Statement']
            for s in p:
                actions=[s['Action']] if isinstance(s['Action'],str) else s['Action']
                writes=set(actions)&{'iam:PutRolePolicy','iam:DeleteRolePolicy','iam:CreateServiceLinkedRole'}
                if 'iam:PutRolePolicy' in writes:
                    self.assertEqual(s['Resource'],f"arn:aws:iam::{account['account_id']}:role/mlo-p3-team1-aws-dev-peering-accepter")
                    self.assertIn('PermissionsBoundary',t['Resources']['PeeringAccepter']['Properties'])
                if 'iam:CreateServiceLinkedRole' in writes:
                    self.assertEqual(account['profile'],'encore1')
                    self.assertEqual(s['Condition']['StringEquals']['iam:AWSServiceName'],'elasticloadbalancing.amazonaws.com')
            actions={a for s in p for a in ([s['Action']] if isinstance(s['Action'],str) else s['Action'])}
            self.assertNotIn('iam:CreateRole',actions)
            self.assertNotIn('iam:UpdateAssumeRolePolicy',actions)
            self.assertNotIn('iam:PutRolePermissionsBoundary',actions)
    def test_peering_trust_is_requester_role_only(self):
        p=templates.bootstrap(self.c,self.c['accounts'][3])['Resources']['PeeringAccepter']['Properties']['AssumeRolePolicyDocument']['Statement'][0]
        arns=p['Condition']['ArnEquals']['aws:PrincipalArn']
        self.assertEqual(len(arns),3)
        self.assertTrue(all(a.endswith('-cfn-execution') for a in arns))
    def test_stack_ownership_guard(self):
        self.assertFalse(infra.owned({'Tags':[{'Key':'Project','Value':'another'}]},self.c))
        self.assertTrue(infra.owned({'Tags':templates.tags(self.c)},self.c))
    def test_generation_scope(self):
        self.c['generation']='g1';self.assertEqual(project.checkpoint_prefix(self.c),'aws/aws-dev/g1/')
        self.c['generation']='g2';self.assertEqual(project.checkpoint_prefix(self.c),'aws/aws-dev/g2/')
    def test_spark_retry_port_range(self):
        n=self.c['accounts'][1]['nodes'][1];rules=templates.ingress_sources(self.c,n)
        self.assertTrue(any(r['FromPort']==39100 and r['ToPort']==39132 for r in rules))


class GuestSafety(unittest.TestCase):
    def runtime(self):return {'env':{'ENVIRONMENT':'aws','AWS_REGION':'ap-northeast-2'},'aws':{'generation':'g1'},
        'node':{'account_id':'444444444444','instance_id':'i-123','instance_type':'t3.medium','address':'10.83.18.20'}}
    def actual(self):return {'accountId':'444444444444','instanceId':'i-123','instanceType':'t3.medium','privateIp':'10.83.18.20','region':'ap-northeast-2'}
    def test_identity_pass(self):identity.verify(self.runtime(),self.actual)
    def test_local_vm_rejected(self):
        c=self.runtime();c['env']['ENVIRONMENT']='local'
        with self.assertRaises(ValueError):identity.verify(c,self.actual)
    def test_wrong_account_rejected(self):
        value=self.actual();value['accountId']='111111111111'
        with self.assertRaises(ValueError):identity.verify(self.runtime(),lambda:value)
    def test_wrong_instance_rejected(self):
        value=self.actual();value['instanceId']='i-wrong'
        with self.assertRaises(ValueError):identity.verify(self.runtime(),lambda:value)
    def test_wrong_or_missing_instance_type_rejected(self):
        for value in ({**self.actual(),'instanceType':'t3.small'},
                      {k:v for k,v in self.actual().items() if k!='instanceType'}):
            with self.subTest(actual=value),self.assertRaises(ValueError):identity.verify(self.runtime(),lambda:value)
    def test_aws_guest_kernel_reserve_does_not_reject_correct_nominal_capacity(self):
        guest_preflight.verify_memory(4096,3832,'aws')
    def test_aws_guest_with_significant_capacity_shortage_still_rejected(self):
        for guest in (2048,3500,3800):
            with self.subTest(guest=guest),self.assertRaises(ValueError):
                guest_preflight.verify_memory(4096,guest,'aws')
    def test_local_guest_memory_threshold_is_preserved(self):
        with self.assertRaises(ValueError):guest_preflight.verify_memory(4096,3832,'local')
        guest_preflight.verify_memory(4096,3900,'local')
    def test_zookeeper_tls_quorum_check_works_before_spark_certificates_exist(self):
        nodes=[{'name':'spark-'+str(i),'address':'192.0.2.'+str(i),'roles':['spark']} for i in (1,2,3)]
        with tempfile.TemporaryDirectory() as tmp:
            tls=Path(tmp)/'zookeeper/tls';tls.mkdir(parents=True)
            for name in ('ca.crt','node.crt','node.key'):(tls/name).write_text('test material')
            self.assertFalse((Path(tmp)/'spark/tls').exists())
            observed=[]
            def voting_mode(address,*,tls_directory=None):
                self.assertTrue(all((Path(tls_directory)/name).is_file() for name in ('ca.crt','node.crt','node.key')))
                observed.append(address)
                return 'leader' if address=='192.0.2.1' else 'follower'
            with patch.object(guest_health,'CONF',tmp),patch.object(guest_health,'zk_mode',side_effect=voting_mode):
                guest_health.zookeeper({'inventory':{'nodes':nodes}})
            self.assertEqual(set(observed),{n['address'] for n in nodes})
    def test_volume_identified_by_serial(self):
        value=disk.find_disk([{'name':'nvme0n1','type':'disk','serial':'volroot'},
            {'name':'nvme1n1','type':'disk','serial':'vol012345'}],'vol-012345')
        self.assertEqual(value['name'],'nvme1n1')
    def test_partitioned_volume_rejected(self):
        with self.assertRaises(ValueError):disk.find_disk([{'type':'disk','serial':'vol123','children':[{}]}],'vol-123')
    def test_unknown_volume_rejected(self):
        with self.assertRaises(ValueError):disk.find_disk([{'type':'disk','serial':'volroot'}],'vol-data')
    def test_dual_active_master_rejected(self):
        with self.assertRaises(ValueError):masters.verify(['ALIVE','ALIVE','STANDBY'])
    def test_master_barrier(self):masters.verify(['STANDBY','ALIVE','STANDBY'])
    def test_ca_key_never_packaged(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'ca.key';p.write_text('test')
            with self.assertRaises(ValueError):list(install.safe_members([('pki/ca.key',p)]))
    def test_path_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'file';p.write_text('test')
            with self.assertRaises(ValueError):list(install.safe_members([('../runtime.json',p)]))
    def test_wrong_stage_role(self):
        self.assertFalse(install.stage_allowed('spark-worker',{'role':'kafka'}))
    def test_existing_receipt_does_not_resend(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'receipt.json';p.write_text('{}')
            with patch.object(install,'inventory') as api:
                with self.assertRaises(ValueError):install.send({},'kafka-01','common',p,None)
                api.assert_not_called()


class ChangeSetSafety(unittest.TestCase):
    def test_compute_update_never_executes(self):
        self.check('compute-kafka-01','AWS::EC2::Instance','Modify','False')
    def test_eni_replacement_never_executes(self):
        self.check('network','AWS::EC2::NetworkInterface','Modify','Conditional')
    def check(self,kind,resource_type,action,replacement):
        c=project.load(ROOT/'config/project.example.json');name=project.stack_name(c,'encore2',kind)
        aws=unittest.mock.Mock()
        aws.call.return_value={'StackName':name,'Status':'CREATE_COMPLETE','ExecutionStatus':'AVAILABLE',
              'Changes':[{'ResourceChange':{'Action':action,'ResourceType':resource_type,'Replacement':replacement}}]}
        with tempfile.TemporaryDirectory() as d:
            config=Path(d)/'config.json';config.write_text(json.dumps(c));review=Path(d)/'review.json'
            review.write_text(json.dumps({'profile':'encore2','kind':kind,'stack_name':name,'change_set_id':'fake',
                'config_sha256':infra.digest(config),'admin':False}))
            infra.CONFIG=config
            with patch.object(infra,'Aws',return_value=aws):
                with self.assertRaises(infra.AwsError):infra.apply(c,review)
        self.assertEqual(aws.call.call_count,1)


class CostEstimate(unittest.TestCase):
    def inputs(self):
        return (json.loads((ROOT/'config/project.example.json').read_text()),json.loads((ROOT/'tests/fixtures/pricing-seoul-20261014.json').read_text()))
    def test_proposal_has_five_account_limits(self):
        c,p=self.inputs();estimate=module('estimate_cost',ROOT/'bin/estimate-cost.py').estimate(c,p)
        self.assertEqual([r['node_count'] for r in estimate['accounts']],[3,3,3,3,2])
        self.assertTrue(all(r['base_within_cap'] for r in estimate['accounts']))
        self.assertEqual([r['cap_usd'] for r in estimate['accounts']],['45.00']*4+['20.00'])
    def test_no_rounding_of_unit_rates(self):
        c,p=self.inputs();estimate=module('estimate_cost',ROOT/'bin/estimate-cost.py').estimate(c,p)
        self.assertEqual(estimate['variable_rates']['nat_processing_usd_per_gb'],'0.0590000000')
    def test_total_rounded_after_aggregation(self):
        c,p=self.inputs();estimate=module('estimate_cost',ROOT/'bin/estimate-cost.py').estimate(c,p)
        self.assertEqual(estimate['base_total_usd'],'150.71')
    def test_ambiguous_alb_product_rejected(self):
        c,p=self.inputs();cost=module('estimate_cost',ROOT/'bin/estimate-cost.py')
        with self.assertRaises(ValueError):cost.rate(p,'alb_hour')

if __name__=='__main__':unittest.main()
