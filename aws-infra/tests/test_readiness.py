"""Offline preparation, config compatibility and AWS isolation regressions."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'lib'), str(ROOT / 'bin')]
import infra
import manage
import project
import readiness
import templates


class WebPortCompatibility(unittest.TestCase):
    def setUp(self):
        self.c = project.load(ROOT / 'config/project.example.json')

    def load(self, config):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / 'config.json'
            file.write_text(json.dumps(config))
            return project.load(file)

    def test_legacy_config_preserved_and_same_network_rules(self):
        legacy = copy.deepcopy(self.c)
        legacy['service_ports']['gunicorn'] = legacy['service_ports'].pop('web')
        self.assertEqual(self.load(legacy), legacy)
        for a, old in zip(self.c['accounts'], legacy['accounts']):
            self.assertEqual(templates.network(self.c, a), templates.network(legacy, old))
        self.assertEqual(project.blockers(self.c, 'alb'), project.blockers(legacy, 'alb'))

    def test_conflicting_aliases_fail_without_echoing_values(self):
        self.c['service_ports']['gunicorn'] = 8001
        with self.assertRaisesRegex(ValueError, 'conflicts'):
            self.load(self.c)

    def test_matching_aliases_allowed(self):
        self.c['service_ports']['gunicorn'] = self.c['service_ports']['web']
        self.assertEqual(project.web_port(self.load(self.c)), 8000)

    def test_invalid_web_port_rejected(self):
        for port in (True, 0, 65536, '8000'):
            with self.subTest(port=port):
                self.c['service_ports']['web'] = port
                with self.assertRaises(ValueError):
                    self.load(self.c)

    def test_web_and_legacy_alb_parameters_identical(self):
        self.c['network_reviewed'] = True
        self.c['az_ids'] = {s: 'apne2-az' + str(i) for i, s in enumerate('abc', 1)}
        self.c['alb'].update(protocol='HTTP', allowed_client_cidr='192.0.2.1/32')
        legacy = copy.deepcopy(self.c)
        legacy['service_ports']['gunicorn'] = legacy['service_ports'].pop('web')
        outputs = {'VpcId': 'vpc-example', 'PublicSubnetA': 'subnet-a', 'PublicSubnetB': 'subnet-b',
                   'AlbSecurityGroupId': 'sg-example', 'InstanceId': 'i-example'}
        with patch.object(infra, 'Aws', return_value=Mock()), patch.object(infra, 'outputs', return_value=outputs):
            new = infra.stack_spec(self.c, self.c['accounts'][0], 'alb')[2]
            old = infra.stack_spec(legacy, legacy['accounts'][0], 'alb')[2]
        self.assertEqual(new, old)


class OfflinePreparation(unittest.TestCase):
    def setUp(self):
        self.c = project.load(ROOT / 'config/project.example.json')
        self.c['network_reviewed'] = True
        self.c['az_ids'] = {s: 'apne2-az' + str(i) for i, s in enumerate('abc', 1)}
        self.c['ami_id'] = 'ami-0123456789abcdef0'
        self.c['alb'].update(protocol='HTTP', allowed_client_cidr='192.0.2.1/32')

    def check(self):
        with patch.object(readiness.shutil, 'which', return_value='/example/aws'), \
             patch.object(readiness, 'source_identity', return_value={'code_version': 'test'}):
            return readiness.check(self.c)

    def test_upstream_hashes_match_reviewed_patches_are_explicit(self):
        report = readiness.source_checks(ROOT)
        self.assertFalse(report['issues'])
        self.assertGreater(report['verified_upstream_files'], 0)
        self.assertIn('40-control.sh', report['reviewed_aws_patch_files'])

    def test_no_aws_calls_no_generation_mutation_or_completion_claim(self):
        before = copy.deepcopy(self.c)
        with patch.object(manage, 'Aws', side_effect=AssertionError('AWS is forbidden')), \
             patch.object(manage, 'Manager', side_effect=AssertionError('Lifecycle is forbidden')):
            report = self.check()
        self.assertEqual(self.c, before)
        self.assertFalse(report['core_missing_inputs'])
        self.assertFalse(report['alb_missing_inputs'])
        self.assertEqual(report['aws_deployment'], 'not performed')
        self.assertEqual(report['service_verification'], 'not performed')
        self.assertFalse(report['business_app_source_required_for_infra_preparation'])

    def test_cli_writes_only_offline_receipt_before_lifecycle(self):
        with patch.object(sys, 'argv', ['manage.py', '--config', str(ROOT / 'config/project.example.json'), 'readiness']), \
             patch.object(manage, 'Manager') as manager, patch.object(manage, 'Aws') as aws, \
             patch.object(manage, 'write') as write, patch('builtins.print'):
            self.assertEqual(manage.main(), 1)  # unresolved public sample
        manager.assert_not_called()
        aws.assert_not_called()
        self.assertEqual(write.call_args.args[0], ROOT / '.state/readiness/latest.json')

    def test_unrestricted_invalid_and_ipv6_cidrs_block_offline_readiness(self):
        for cidr in ('0.0.0.0/0', '::/0', 'not-a-network', '192.0.2.5/24'):
            with self.subTest(cidr=cidr):
                self.c['alb']['allowed_client_cidr'] = cidr
                report = self.check()
                self.assertFalse(report['ready_for_aws_preflight'])
                self.assertTrue(any('allowed_client_cidr' in issue for issue in report['alb_missing_inputs']))

    def test_health_path_and_wrong_region_certificate_block(self):
        self.c['alb'].update(protocol='HTTPS', health_path='health\n',
                             certificate_arn='arn:aws:acm:us-east-1:111111111111:certificate/abcd')
        issues = self.check()['alb_missing_inputs']
        self.assertTrue(any('health_path' in issue for issue in issues))
        self.assertTrue(any('certificate_arn' in issue for issue in issues))

    def test_report_contains_no_config_values(self):
        self.c['private_note'] = 'NEVER_ECHO_THIS_VALUE'
        value = json.dumps(self.check())
        for secret in (self.c['private_note'], self.c['operator_principal_arn'],
                       self.c['alb']['allowed_client_cidr'], self.c['ami_id'],
                       *(a['account_id'] for a in self.c['accounts'])):
            self.assertNotIn(secret, value)

    def test_missing_tool_blocks_preflight_readiness(self):
        with patch.object(readiness.shutil, 'which', return_value=None):
            report = readiness.check(self.c)
        self.assertFalse(report['ready_for_aws_preflight'])
        self.assertIn('tool unavailable: aws_cli_on_path', report['preparation_issues'])

    def test_source_corruption_and_missing_patched_file_detected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'installer/core').mkdir(parents=True)
            (root / 'installer/core/file.sh').write_text('changed')
            (root / 'installer/source-manifest.json').write_text(json.dumps({
                'source_files_sha256': {'file.sh': '0' * 64, 'patch.sh': '0' * 64},
                'aws_patches': {'patch.sh': 'reviewed change'}}))
            issues = readiness.source_checks(root)['issues']
        self.assertEqual(len(issues), 2)
        self.assertTrue(any('hash mismatch' in issue for issue in issues))
        self.assertTrue(any('missing or unsafe' in issue for issue in issues))


if __name__ == '__main__':
    unittest.main()
