"""No-AWS tests for adding HTTPS after core creation without changing core scope."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'lib'),str(ROOT/'bin')]
import manage,project
from awscli import AwsError


class AlbExtension(unittest.TestCase):
    def fixture(self,tmp):
        c=project.load(ROOT/'config/project.example.json')
        source=Path(tmp)/'input.json';source.write_text(json.dumps(c))
        first=manage.Manager(c,source,False);first.start();first.transition('ready')
        generation=first.c['generation']
        wanted=copy.deepcopy(c);wanted['alb']={'certificate_arn':'example-certificate','allowed_client_cidr':'192.0.2.1/32','health_path':'/health/'}
        source.write_text(json.dumps(wanted))
        return source,wanted,generation

    def test_addition_changes_only_alb_preserving_generation(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(manage,'ROOT',Path(tmp)):
            source,wanted,generation=self.fixture(tmp)
            manager=manage.Manager(wanted,source,True);manager.preflight=Mock();manager.ensure=Mock()
            manager.add_alb();manager.ensure.assert_called_once_with('encore1','alb')
            result=json.loads(manager.current.read_text())
            self.assertTrue(result['include_alb']);self.assertEqual(result['state'],'ready')
            resolved=json.loads(Path(result['resolved_config']).read_text())
            self.assertEqual(resolved['generation'],generation);self.assertEqual(resolved['alb'],wanted['alb'])
            self.assertEqual(resolved['accounts'],wanted['accounts'])
            again=manage.Manager(wanted,source,True);self.assertFalse(again.input_changed);self.assertFalse(again.scope_changed)

    def test_core_changes_are_rejected_before_any_api(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(manage,'ROOT',Path(tmp)):
            source,wanted,_=self.fixture(tmp);wanted['service_ports']['web']=8001;source.write_text(json.dumps(wanted))
            manager=manage.Manager(wanted,source,True);manager.preflight=Mock();manager.ensure=Mock()
            with self.assertRaisesRegex(ValueError,'only ALB settings'):manager.add_alb()
            manager.preflight.assert_not_called();manager.ensure.assert_not_called()

    def test_failed_extension_can_resume_and_destroy_keeps_recorded_scope(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(manage,'ROOT',Path(tmp)):
            source,wanted,generation=self.fixture(tmp)
            manager=manage.Manager(wanted,source,True);manager.preflight=Mock();manager.ensure=Mock(side_effect=AwsError('outcome unknown'))
            with self.assertRaises(AwsError):manager.add_alb()
            state=json.loads(manager.current.read_text());self.assertEqual(state['state'],'adding_alb');self.assertFalse(state['include_alb'])
            again=manage.Manager(wanted,source,True);self.assertEqual(again.c['generation'],generation)
            again.preflight=Mock();again.ensure=Mock();again.add_alb()
            self.assertTrue(json.loads(again.current.read_text())['include_alb'])


if __name__=='__main__':unittest.main()
