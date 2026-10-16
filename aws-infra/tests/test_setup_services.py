"""Dependency barriers and unknown-submission protection without SSM or EC2 access."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

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


if __name__=='__main__':unittest.main()
