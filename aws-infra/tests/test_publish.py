"""Publishing and preflight regression tests; no AWS calls or Git initialization."""
import ast
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'lib'), str(ROOT / 'bin')]
import project
import preflight
from awscli import Aws, AwsError

spec = importlib.util.spec_from_file_location('public_scan', ROOT / 'bin/check-public.py')
public = importlib.util.module_from_spec(spec)
spec.loader.exec_module(public)


class PublishingSafety(unittest.TestCase):
    def setUp(self):
        self.c = project.load(ROOT / 'config/project.example.json')
        self.rules = (ROOT / '.gitignore').read_text().splitlines()

    def load(self, c):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'config.json'
            path.write_text(json.dumps(c))
            return project.load(path)

    def test_example_cannot_contact_aws(self):
        with patch.object(Aws, 'call') as call:
            with self.assertRaisesRegex(AwsError, 'example configuration'):
                Aws(self.c, self.c['accounts'][0])
            call.assert_not_called()

    def test_distinct_string_accounts_and_operator_identity_required(self):
        self.c['accounts'][1]['account_id'] = self.c['accounts'][0]['account_id']
        with self.assertRaises(ValueError):
            self.load(self.c)
        self.c = project.load(ROOT / 'config/project.example.json')
        self.c['operator_principal_arn'] = 'arn:aws:iam::222222222222:user/REPLACE_ME'
        with self.assertRaises(ValueError):
            self.load(self.c)

    def test_account_leading_zero_preserved(self):
        self.c['accounts'][3]['account_id'] = '012345678901'
        self.assertEqual(self.load(self.c)['accounts'][3]['account_id'], '012345678901')

    def test_all_sensitive_paths_ignored_and_sources_publishable(self):
        for path in ('config/project.json', '.env', '.env.dev', 'nested/.env', 'nested/prod.env',
                     '.aws/credentials', '.state/receipt.json', '.private/node.json', '.local/history/docs/file.md',
                     '.tools/bin/tool', 'tls/node.key', 'payload.tgz', 'package.zip'):
            self.assertTrue(public.ignored(path, self.rules), path)
        for path in ('config/project.example.json', 'README.md', 'lib/templates.py',
                     'templates/peering.json', 'tests/test_publish.py'):
            self.assertFalse(public.ignored(path, self.rules), path)

    def test_secret_findings_do_not_echo_values(self):
        secret = 'AK' + 'IA' + 'A' * 16
        key = '-' * 5 + 'BEGIN PRIVATE KEY' + '-' * 5
        issues = public.findings('unsafe.txt', secret + '\n' + key)
        self.assertEqual(len(issues), 2)
        self.assertNotIn(secret, json.dumps(issues))
        self.assertNotIn(key, json.dumps(issues))
        self.assertEqual([i['line'] for i in issues], [1, 2])

    def test_literal_secret_and_local_identifiers_detected(self):
        value = 'example' + 'A' * 24
        text = 'aws_secret_access_key="' + value + '"'
        self.assertTrue(public.findings('file.py', text))
        self.assertTrue(public.findings('file.json', '012345678901', ['012345678901']))

    def test_scan_skips_private_directory_and_rejects_public_symlink(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / '.private').mkdir()
            (root / '.private/secret').write_text('AK' + 'IA' + 'B' * 16)
            (root / 'README.md').write_text('safe')
            (root / 'link').symlink_to(root / '.private/secret')
            count, issues = public.scan(root, self.rules)
            self.assertEqual(count, 1)
            self.assertEqual(issues, [{'path': 'link', 'category': 'public symlink requires review'}])


class SharedDocumentSafety(unittest.TestCase):
    def test_shared_docs_reuse_private_account_identifier_checks(self):
        with tempfile.TemporaryDirectory() as folder:
            repository=Path(folder);root=repository/'aws-infra';(root/'config').mkdir(parents=True)
            rules=['/config/project.json','.env','*.key','.private/','.state/']
            account='012345678901';(root/'config/project.json').write_text(json.dumps({'accounts':[{'account_id':account}]}))
            docs=repository/'docs/handoff/infra';docs.mkdir(parents=True)
            (docs/'README.md').write_text('account='+account)
            with patch.object(public,'tracked_private_files',return_value=[]):
                _,issues,scopes=public.scan_project(root,rules)
            self.assertIn('docs/handoff/infra',scopes)
            self.assertEqual(issues,[{'path':'docs/handoff/infra/README.md','line':1,'category':'local AWS account identifier'}])
            self.assertNotIn(account,json.dumps(issues))

    def test_relative_package_root_still_scans_parent_documents(self):
        import os
        with tempfile.TemporaryDirectory() as folder:
            repository=Path(folder);root=repository/'aws-infra';root.mkdir()
            docs=repository/'docs/handoff/infra';docs.mkdir(parents=True)
            (docs/'README.md').write_text('AK'+'IA'+'Z'*16)
            previous=Path.cwd()
            try:
                os.chdir(root)
                with patch.object(public,'tracked_private_files',return_value=[]):
                    _,issues,scopes=public.scan_project(Path('.'),[])
            finally:os.chdir(previous)
            self.assertIn('docs/handoff/infra',scopes)
            self.assertEqual(issues[0]['path'],'docs/handoff/infra/README.md')

    def test_shared_docs_ignore_keys_and_reject_symlinks(self):
        with tempfile.TemporaryDirectory() as folder:
            repository=Path(folder);root=repository/'aws-infra';root.mkdir()
            docs=repository/'docs/handoff/infra';docs.mkdir(parents=True)
            (docs/'private.key').write_text('private')
            (docs/'README.md').write_text('safe')
            (docs/'link').symlink_to(docs/'private.key')
            with patch.object(public,'tracked_private_files',return_value=[]):
                count,issues,_=public.scan_project(root,['*.key'])
            self.assertEqual(count,1)
            self.assertEqual(issues,[{'path':'docs/handoff/infra/link','category':'public symlink requires review'}])

    def test_root_workflow_is_checked_for_credential_leaks(self):
        with tempfile.TemporaryDirectory() as folder:
            repository=Path(folder);root=repository/'aws-infra';root.mkdir()
            workflow=repository/'.github/workflows';workflow.mkdir(parents=True)
            secret='AK'+'IA'+'X'*16
            (workflow/'aws-infra-check.yml').write_text(secret)
            with patch.object(public,'tracked_private_files',return_value=[]):
                _,issues,_=public.scan_project(root,[])
            self.assertEqual(issues[0]['path'],'.github/workflows/aws-infra-check.yml')
            self.assertEqual(issues[0]['category'],'AWS access key ID')
            self.assertNotIn(secret,json.dumps(issues))


class ReadOnlyPreflight(unittest.TestCase):
    def setUp(self):
        self.c = project.load(ROOT / 'config/project.example.json')
        self.c['example_only'] = False
        self.observed = []
        for a in self.c['accounts']:
            record = {'profile': a['profile'], 'bootstrap_template_matches': True,
                      'bootstrap_resources_complete': True, 'outputs_match': True,
                      'physical_zones': {f'apne2-az{i}': f'zone-{i}' for i in range(1, 4)},
                      'invalid_instance_specs': [], 'required_vcpu': 6, 'vcpu_quota': 640,
                      'cidr_collisions': [], 'certificate_issued': False}
            offers = {(n['instance_type'], f'apne2-az{i}') for n in a['nodes'] for i in range(1, 4)}
            images = [{'id': 'ami-0123456789abcdef0', 'name': 'ubuntu-noble-24.04', 'created_at': '2026-10-01'}]
            self.observed.append((record, offers, images))

    def test_core_ready_still_does_not_claim_full_deployment(self):
        resolved, report = preflight.readiness(self.c, self.observed, ['192.168.0.0/24'])
        self.assertTrue(report['core_infrastructure_prerequisites_ready'])
        self.assertFalse(report['full_infrastructure_prerequisites_ready'])
        self.assertFalse(report['resources_created'])
        self.assertIsNone(resolved['generation'])
        self.assertIsNone(self.c['ami_id'])
        self.assertEqual(len(set(resolved['az_ids'].values())), 3)

    def test_collision_or_policy_mismatch_blocks_readiness(self):
        _, report = preflight.readiness(self.c, self.observed, ['10.80.0.0/16'])
        self.assertFalse(report['core_infrastructure_prerequisites_ready'])
        self.assertTrue(report['issues'])
        self.observed[2][0]['bootstrap_template_matches'] = False
        _, report = preflight.readiness(self.c, self.observed, ['192.168.0.0/24'])
        self.assertFalse(report['core_infrastructure_prerequisites_ready'])

    def test_ami_must_be_visible_in_every_account(self):
        self.observed[3][2].clear()
        _, report = preflight.readiness(self.c, self.observed, ['192.168.0.0/24'])
        self.assertFalse(report['core_infrastructure_prerequisites_ready'])
        self.assertTrue(any('AMI' in issue for issue in report['issues']))

    def test_missing_instance_offering_blocks_three_az_selection(self):
        self.observed[4][1].difference_update({(t, 'apne2-az3') for t in ('t3.small', 't3.medium')})
        _, report = preflight.readiness(self.c, self.observed, ['192.168.0.0/24'])
        self.assertFalse(report['core_infrastructure_prerequisites_ready'])

    def test_preflight_aws_operations_are_read_only(self):
        tree = ast.parse((ROOT / 'bin/preflight.py').read_text())
        operations = [call.args[1].value for call in ast.walk(tree)
                      if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                      and call.func.attr == 'call' and len(call.args) > 1 and isinstance(call.args[1], ast.Constant)]
        self.assertTrue(operations)
        self.assertTrue(all(op.startswith(('describe-', 'get-', 'list-')) for op in operations))


if __name__ == '__main__':
    unittest.main()
