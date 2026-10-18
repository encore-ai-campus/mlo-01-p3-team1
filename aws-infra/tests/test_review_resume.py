"""Recorded empty review-stack identity and scoped validation-reader regressions."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'lib'),str(ROOT/'bin')]
import infra,manage,project,templates
from awscli import AwsError


class ReviewStackOwnership(unittest.TestCase):
    def setUp(self):
        self.c=project.load(ROOT/'config/project.example.json')
        self.name=project.stack_name(self.c,'encore1','network')
        self.record={'profile':'encore1','kind':'network','name':self.name,'change_set_id':'cs-example'}
        self.stack={'StackId':'stack-example','StackStatus':'REVIEW_IN_PROGRESS','Tags':[],
                    'RoleARN':'arn:aws:iam::'+self.c['accounts'][0]['account_id']+':role/'+project.prefix(self.c)+'-cfn-execution'}
        self.cs={'ChangeSetId':'cs-example','StackId':'stack-example','StackName':self.name,
                 'Status':'CREATE_COMPLETE','ExecutionStatus':'AVAILABLE',
                 'RoleARN':'arn:aws:iam::'+self.c['accounts'][0]['account_id']+':role/'+project.prefix(self.c)+'-cfn-execution',
                 'Tags':templates.tags(self.c)}

    def lookup(self,record,stack=None,cs=None,resources=()):
        aws=Mock();aws.call.side_effect=[{'Stacks':[stack or self.stack]},cs or self.cs,
                                        {'StackResourceSummaries':list(resources)}]
        return infra.get_stack(aws,self.name,self.c,review_record=record)

    def test_saved_verified_change_set_can_resume_empty_review_stack(self):
        self.assertEqual(self.lookup(self.record),self.stack)

    def test_no_record_cannot_adopt_untagged_stack(self):
        with self.assertRaises(AwsError):self.lookup(None)

    def test_receipt_name_and_profile_must_match(self):
        for changes in ({'name':'other'},{'profile':'encore2'},{'kind':'storage'},{'change_set_id':None}):
            with self.subTest(changes=changes),self.assertRaises(AwsError):
                self.lookup({**self.record,**changes})

    def test_change_set_identity_role_status_and_tags_must_match(self):
        for changes in ({'ChangeSetId':'other'},{'StackId':'other'},{'StackName':'other'},
                        {'RoleARN':'other'},{'Status':'FAILED'},{'ExecutionStatus':'EXECUTE_COMPLETE'},{'Tags':[]}):
            with self.subTest(changes=changes),self.assertRaises(AwsError):
                self.lookup(self.record,cs={**self.cs,**changes})

    def test_review_resume_does_not_adopt_existing_resources(self):
        with self.assertRaises(AwsError):self.lookup(self.record,resources=[{'LogicalResourceId':'Existing'}])

    def test_untagged_other_stack_states_still_refused(self):
        for status in ('CREATE_IN_PROGRESS','CREATE_COMPLETE','ROLLBACK_COMPLETE'):
            with self.subTest(status=status),self.assertRaises(AwsError):
                self.lookup(self.record,stack={**self.stack,'StackStatus':status})

    def test_tagged_stack_keeps_normal_ownership_path(self):
        stack={**self.stack,'StackStatus':'CREATE_COMPLETE','Tags':templates.tags(self.c)}
        self.assertEqual(self.lookup(None,stack=stack),stack)

    def test_real_api_role_is_proved_from_stack_when_absent_on_change_set(self):
        cs=copy.deepcopy(self.cs);cs.pop('RoleARN')
        self.assertEqual(self.lookup(self.record,cs=cs),self.stack)
        with self.assertRaises(AwsError):self.lookup(self.record,stack={**self.stack,'RoleARN':'other'},cs=cs)

    def test_manager_passes_saved_receipt_to_resolution_before_any_execute(self):
        with tempfile.TemporaryDirectory() as folder:
            manager=object.__new__(manage.Manager);manager.c=self.c;manager.run=Path(folder)
            (manager.run/'templates').mkdir()
            (manager.run/'templates'/(self.name+'.json')).write_text(json.dumps(templates.network(self.c,self.c['accounts'][0])))
            (manager.run/'encore1-network.json').write_text(json.dumps(self.record))
            api=Mock();api.call.side_effect=[{**self.cs,'Changes':[]},{'OperationEvents':[{'EventType':'VALIDATION_ERROR'}]}]
            with patch.object(infra,'stack_spec',return_value=(api,self.name,{},self.name,False)) as resolve, \
                 patch.object(infra,'get_stack',return_value=self.stack) as lookup:
                with self.assertRaisesRegex(AwsError,'validation findings'):manager.ensure('encore1','network')
            self.assertEqual(resolve.call_args.kwargs['review_record'],self.record)
            self.assertEqual(lookup.call_args.kwargs['review_record'],self.record)
            self.assertFalse(any(call.args[1]=='execute-change-set' for call in api.call.call_args_list))


class ValidationReadPolicy(unittest.TestCase):
    def test_all_five_validation_read_exceptions_are_single_action_and_regional(self):
        c=project.load(ROOT/'config/project.example.json')
        for a in c['accounts']:
            with self.subTest(profile=a['profile']):
                t=templates.bootstrap(c,a)
                policy=t['Resources']['OperatorRole']['Properties']['Policies'][0]['PolicyDocument'] if a['profile']=='encore1' else t['Resources']['OperatorPolicy']['Properties']['PolicyDocument']
                grants=[s for s in policy['Statement'] if s['Action']=='cloudformation:DescribeEvents']
                self.assertEqual(len(grants),1)
                s=grants[0]
                self.assertEqual(s['Resource'],'*')
                self.assertEqual(s['Condition']['StringEquals'],{'aws:RequestedRegion':c['region']})
                self.assertEqual(s['Effect'],'Allow')

    def test_public_sample_never_reads_private_receipts(self):
        c=project.load(ROOT/'config/project.example.json')
        with patch.object(project.Path,'glob',side_effect=AssertionError('Private receipts must not be read')):
            for a in c['accounts']:templates.bootstrap(c,a)

    def test_event_read_exception_does_not_add_global_cloudformation_writes_or_iam(self):
        c=project.load(ROOT/'config/project.example.json')
        allowed_global={'cloudformation:DescribeEvents','cloudformation:ListStacks',
                        'cloudformation:ValidateTemplate','cloudformation:GetTemplateSummary'}
        for a in c['accounts']:
            t=templates.bootstrap(c,a)
            policy=t['Resources']['OperatorRole']['Properties']['Policies'][0]['PolicyDocument'] if a['profile']=='encore1' else t['Resources']['OperatorPolicy']['Properties']['PolicyDocument']
            for s in policy['Statement']:
                actions=s['Action'] if isinstance(s['Action'],list) else [s['Action']]
                self.assertFalse(any(x.startswith('iam:') and x!='iam:PassRole' for x in actions))
                if s['Resource']=='*':
                    self.assertTrue({x for x in actions if x.startswith('cloudformation:')}<=allowed_global)


class AlbAccountAttributeRead(unittest.TestCase):
    def test_only_seoul_encore1_execution_role_gets_account_attribute_read(self):
        c=project.load(ROOT/'config/project.example.json')
        for a in c['accounts']:
            t=templates.bootstrap(c,a)
            policies=[('execution',t['Resources']['ExecutionRole']['Properties']['Policies'][0]['PolicyDocument'])]
            operator=t['Resources']['OperatorRole']['Properties']['Policies'][0]['PolicyDocument'] if a['profile']=='encore1' else t['Resources']['OperatorPolicy']['Properties']['PolicyDocument']
            policies.append(('operator',operator))
            for role,policy in policies:
                with self.subTest(profile=a['profile'],role=role):
                    grants=[s for s in policy['Statement'] if 'ec2:DescribeAccountAttributes' in (s['Action'] if isinstance(s['Action'],list) else [s['Action']])]
                    if a['profile']=='encore1' and role=='execution':
                        self.assertEqual(grants,[{'Effect':'Allow','Action':'ec2:DescribeAccountAttributes','Resource':'*',
                            'Condition':{'StringEquals':{'aws:RequestedRegion':c['region']}}}])
                    else:self.assertEqual(grants,[])


if __name__=='__main__':unittest.main()
