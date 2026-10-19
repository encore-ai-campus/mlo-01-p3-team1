"""Dependency barriers and unknown-submission protection without SSM or EC2 access."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'lib'),str(ROOT/'bin')]
import project
from awscli import AwsError
spec=importlib.util.spec_from_file_location('services_setup',ROOT/'bin/setup-services.py')
setup=importlib.util.module_from_spec(spec);spec.loader.exec_module(setup)


class ServiceSetup(unittest.TestCase):
    def setUp(self):
        self.c=project.load(ROOT/'config/project.example.json');self.c['generation']='setup-test'

    def test_three_node_barriers_precede_workers_and_role_stages(self):
        phases=setup.phases(self.c);names=[p[0] for p in phases]
        self.assertEqual(len(phases[0][1]),14)
        self.assertEqual(len(phases[names.index('common')][1]),11)
        self.assertLess(names.index('zookeeper-health'),names.index('spark-master'))
        self.assertLess(names.index('spark-master-health'),names.index('spark-worker'))
        self.assertEqual(len(phases[names.index('spark-master-health')][1]),3)
        self.assertEqual(phases[names.index('postgresql')][1],['postgresql'])
        self.assertEqual(phases[names.index('application-host')][1],['advertising'])
        self.assertFalse(set(names)&{'pipeline','ha','connectors','catalog'})

    def test_unknown_submission_is_not_resent(self):
        with tempfile.TemporaryDirectory() as folder:
            receipt=Path(folder)/'postgresql-postgresql.json'
            receipt.write_text(json.dumps({'generation':'setup-test','node':'postgresql','stage':'postgresql','status':'intent'}))
            with patch.object(setup.install,'send') as send,patch.object(setup,'Aws') as aws:
                with self.assertRaisesRegex(AwsError,'outcome unknown'):setup.run_step(self.c,Path(folder),'postgresql','postgresql')
                send.assert_not_called();aws.assert_not_called()

    def test_success_receipt_is_not_submitted_again(self):
        with tempfile.TemporaryDirectory() as folder:
            receipt=Path(folder)/'postgresql-postgresql.json'
            receipt.write_text(json.dumps({'generation':'setup-test','node':'postgresql','stage':'postgresql','command_id':'existing','status':'Success'}))
            with patch.object(setup.install,'send') as send,patch.object(setup,'Aws') as aws:
                setup.run_step(self.c,Path(folder),'postgresql','postgresql')
                send.assert_not_called();aws.assert_not_called()

    def test_prior_failure_requires_inspection_before_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            receipt=Path(folder)/'postgresql-postgresql.json'
            receipt.write_text(json.dumps({'generation':'setup-test','node':'postgresql','stage':'postgresql','command_id':'existing','status':'Failed'}))
            with patch.object(setup.install,'send') as send:
                with self.assertRaises(AwsError):setup.run_step(self.c,Path(folder),'postgresql','postgresql')
                send.assert_not_called()


class SsmCommandObservation(unittest.TestCase):
    def invocation(self,status,plugins=()):
        return {'CommandId':'saved-command','InstanceId':'saved-instance','Status':status,
                'CommandPlugins':list(plugins)}

    def test_document_step_names_do_not_control_whole_command_success(self):
        aws=Mock();value=self.invocation('Success',[{'Name':'aws:runShellScript','Status':'Success'}])
        aws.call.return_value={'CommandInvocations':[value]}
        self.assertEqual(setup.install.poll(aws,'saved-command','saved-instance'),value)
        aws.call.assert_called_once_with('ssm','list-command-invocations','--command-id','saved-command',
                                         '--instance-id','saved-instance','--details')

    def test_eventual_visibility_and_all_steps_must_finish_before_success(self):
        aws=Mock();pending=self.invocation('InProgress',[{'Name':'downloadContent','Status':'InProgress'},
                                                       {'Name':'runShellScript','Status':'Success'}])
        done=self.invocation('Success')
        aws.call.side_effect=[{'CommandInvocations':[]},{'CommandInvocations':[pending]},
                              {'CommandInvocations':[done]}]
        def bounded_wait(fn,predicate,**kwargs):
            self.assertFalse(predicate(fn()))
            self.assertFalse(predicate(fn()))
            value=fn();self.assertTrue(predicate(value));return value
        with patch.object(setup.install,'wait_until',side_effect=bounded_wait):
            self.assertEqual(setup.install.poll(aws,'saved-command','saved-instance'),done)
        self.assertEqual(aws.call.call_count,3)

    def test_failed_invocation_is_not_hidden_by_a_successful_plugin_or_resent(self):
        aws=Mock();aws.call.return_value={'CommandInvocations':[self.invocation('Failed',[
            {'Name':'downloadContent','Status':'Failed'},{'Name':'runShellScript','Status':'Success'}])]}
        with self.assertRaisesRegex(AwsError,'SSM stage Failed'):
            setup.install.poll(aws,'saved-command','saved-instance')
        self.assertEqual(aws.call.call_count,1)

    def test_unexpected_or_duplicate_invocation_identity_is_rejected(self):
        value=self.invocation('Success')
        for items in ([{**value,'CommandId':'another-command'}],
                      [{**value,'InstanceId':'another-instance'}],[value,value]):
            aws=Mock();aws.call.return_value={'CommandInvocations':items}
            with self.subTest(items=items),self.assertRaisesRegex(AwsError,'identity differs'):
                setup.install.poll(aws,'saved-command','saved-instance')


if __name__=='__main__':unittest.main()
