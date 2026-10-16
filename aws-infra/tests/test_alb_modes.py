"""Temporary HTTP is explicit; HTTPS still requires a regional certificate."""
import copy,json
from pathlib import Path
import sys,tempfile,unittest
from unittest.mock import patch,Mock
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'bin'),str(ROOT/'lib')]
import project,templates,infra,manage
from awscli import AwsError

class AlbModes(unittest.TestCase):
    def setUp(self):
        self.c=project.load(ROOT/'config/project.example.json')
        self.c['alb'].update(protocol='HTTP',allowed_client_cidr='192.0.2.1/32')
        self.c['network_reviewed']=True;self.c['az_ids']={s:'apne2-az'+str(i) for i,s in enumerate('abc',1)}
    def test_http_without_certificate_and_https_with_certificate_required(self):
        self.assertNotIn('alb.certificate_arn',project.blockers(self.c,'alb'))
        self.c['alb']['protocol']='HTTPS'
        self.assertIn('alb.certificate_arn',project.blockers(self.c,'alb'))
    def test_same_listener_and_no_certificate_property_for_http(self):
        t=templates.alb(self.c)
        self.assertEqual(t['Parameters']['Protocol']['Default'],'HTTPS')
        import re
        pattern=t['Parameters']['ClientCidr']['AllowedPattern']
        self.assertIsNone(re.fullmatch(pattern,'0.0.0.0/0'))
        self.assertIsNotNone(re.fullmatch(pattern,'192.0.2.1/32'))
        listener=t['Resources']['Listener']['Properties']
        self.assertEqual(listener['Protocol'],{'Ref':'Protocol'})
        self.assertEqual(listener['Certificates']['Fn::If'][2],{'Ref':'AWS::NoValue'})
        self.assertEqual(listener['Port']['Fn::If'],['UseHttps',443,80])
        self.assertNotIn('Condition',t['Resources']['Listener'])
        self.assertEqual(t['Resources']['Targets']['Properties']['Port'],{'Ref':'TargetPort'})
    def test_http_stack_parameters_do_not_need_acm_or_allow_unrestricted_cidr(self):
        aws=Mock();a=self.c['accounts'][0]
        out={'VpcId':'vpc-example','PublicSubnetA':'subnet-a','PublicSubnetB':'subnet-b','AlbSecurityGroupId':'sg-example','InstanceId':'i-example'}
        with patch.object(infra,'Aws',return_value=aws),patch.object(infra,'outputs',return_value=out):
            _,_,params,_,_=infra.stack_spec(self.c,a,'alb')
            self.assertEqual(params['Protocol'],'HTTP');self.assertEqual(params['CertificateArn'],'')
            aws.call.assert_not_called()
            self.c['alb']['allowed_client_cidr']='0.0.0.0/0'
            with self.assertRaises(ValueError):infra.stack_spec(self.c,a,'alb')
    def test_only_dedicated_ingress_rule_can_be_replaced(self):
        r={'Action':'Modify','Replacement':'True','LogicalResourceId':'Ingress','ResourceType':'AWS::EC2::SecurityGroupIngress'}
        manage.validate_changes('alb',{'Changes':[{'ResourceChange':r}]})
        for overrides in ({'LogicalResourceId':'LoadBalancer','ResourceType':'AWS::ElasticLoadBalancingV2::LoadBalancer'},
                          {'LogicalResourceId':'Targets'}, {'Action':'Remove'}):
            with self.assertRaises(AwsError):manage.validate_changes('alb',{'Changes':[{'ResourceChange':{**r,**overrides}}]})
    def test_finished_alb_receipt_is_not_reused_for_a_new_update(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager=object.__new__(manage.Manager);manager.c=self.c;manager.run=Path(tmp)
            template=manager.run/'templates'/'alb.json';template.parent.mkdir();template.write_text(json.dumps(templates.alb(self.c)))
            receipt=manager.run/'encore1-alb.json';receipt.write_text(json.dumps({'status':'ready','change_set_id':'old-id'}))
            aws=Mock();aws.call.side_effect=AwsError('new request outcome unknown')
            with patch.object(infra,'stack_spec',return_value=(aws,'alb-stack',{'Protocol':'HTTP'},'alb',False)),patch.object(infra,'get_stack',return_value=None):
                with self.assertRaises(AwsError):manager.ensure('encore1','alb')
            record=json.loads(receipt.read_text());self.assertNotIn('change_set_id',record)
            self.assertIn('unknown',record['status'])
            aws.call.assert_called_once();self.assertEqual(aws.call.call_args.args[1],'create-change-set')
            self.assertEqual(len(list(manager.run.glob('encore1-alb-*.json'))),1)

    def test_http_to_https_update_preserves_core_generation(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(manage,'ROOT',Path(tmp)):
            source=Path(tmp)/'config.json';source.write_text(json.dumps(self.c))
            first=manage.Manager(self.c,source,True);first.start();first.transition('ready');gen=first.c['generation']
            wanted=copy.deepcopy(self.c);wanted['alb'].update(protocol='HTTPS',certificate_arn='example-certificate');source.write_text(json.dumps(wanted))
            later=manage.Manager(wanted,source,True);later.preflight=Mock();later.ensure=Mock();later.add_alb()
            state=json.loads(later.current.read_text());resolved=json.loads(Path(state['resolved_config']).read_text())
            self.assertEqual(resolved['generation'],gen);self.assertEqual(resolved['accounts'],self.c['accounts'])
            self.assertEqual(resolved['alb']['protocol'],'HTTPS');later.ensure.assert_called_once_with('encore1','alb')

if __name__=='__main__':unittest.main()
