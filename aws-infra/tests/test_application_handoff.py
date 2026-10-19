"""Handoff preparation must never turn unreviewed team input into deployment."""
import copy
import hashlib
import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
from application_contract import plan
from application_handoff import configuration, prepare, previews
from project import load, prefix, checkpoint_bucket, checkpoint_prefix


class HandoffSafety(unittest.TestCase):
    def setUp(self):
        self.c = load(ROOT / 'config/project.example.json')
        self.c['generation'] = 'g-unit-test'
        self.contract = json.loads((ROOT / 'config/application-contract.example.json').read_text())
        # Fixture choices exercise formatting only; they do not select a project server/version.
        self.contract['weather_mongodb']['writer_process'] = 'weather Driver on the active Control'
        self.contract['elasticsearch'].update(application_transport='rest-bulk', writer_execution='control-driver',
            document_id_rule='stable source id', ordering_rule='reject stale source revision',
            failure_retry_rule='fail incomplete batches; bounded retry',
            credential_reference='/etc/music-cluster/control/weather-search.env')
        self.contract['web'].update(asgi_program='fixture-asgi', asgi_version='1.2.3',
            entrypoint='weather.api:app', workers=1, stop_timeout_seconds=60,
            dependency_lock_reference='/opt/music-apps/control/requirements.lock', dependency_lock_sha256='a' * 64,
            start_argv=['/opt/music-apps/control/venv/bin/fixture-asgi', 'weather.api:app', '--host', '{CONTROL_PRIVATE_IP}', '--port', '8000'])
        self.contract['single_active'].update(supervised_argv=['/opt/music-cluster/spark/bin/spark-submit',
            '--deploy-mode', 'client', '/opt/music-apps/control/weather.py'], driver_application_identity='weather-driver',
            query_key='weather-query', stop_evidence='process group gone plus Spark globally idle')
        self.contract['single_active']['checkpoint_reference'] = ('s3a://' + checkpoint_bucket(self.c)
            + '/' + checkpoint_prefix(self.c) + 'weather-query/')

    def test_complete_inputs_are_review_only_and_per_node_bind_is_rendered(self):
        c_before = copy.deepcopy(self.c);contract_before = copy.deepcopy(self.contract)
        with patch('awscli.Aws') as aws, patch('subprocess.run') as run:
            report = plan(self.c, self.contract);files = previews(self.c, self.contract)
        aws.assert_not_called();run.assert_not_called()
        self.assertTrue(report['contract_inputs_complete']);self.assertFalse(report['application_or_ha_verified'])
        self.assertEqual(self.c, c_before);self.assertEqual(self.contract, contract_before)
        controls = [n for a in self.c['accounts'] for n in a['nodes'] if n['role'] == 'control']
        self.assertEqual(len(files), 4)
        for node in controls:
            unit = files[node['name'] + '/music-web.service']
            self.assertIn('"' + node['private_ip'] + '"', unit);self.assertNotIn('{CONTROL_PRIVATE_IP}', unit)
            self.assertIn('ExecStart=:', unit);self.assertIn('KillMode=control-group', unit)
            supervisor = json.loads(files[node['name'] + '/supervisor-patch.review.json'])
            self.assertEqual(supervisor['checkpoint_reference'], self.contract['single_active']['checkpoint_reference'])
            self.assertFalse(supervisor['epoch_owner_or_checkpoint_initialization'])
            self.assertTrue(supervisor['requires_new_business_supervisor_installation_review'])

    def test_pending_contract_produces_only_templates_with_private_permissions(self):
        pending = json.loads((ROOT / 'config/application-contract.example.json').read_text())
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / '.state/handoff/review'
            with patch('awscli.Aws') as aws, patch('subprocess.run') as run:
                report = prepare(self.c, pending, out, root=tmp)
            aws.assert_not_called();run.assert_not_called()
            self.assertFalse(report['review_artifacts_rendered']);self.assertEqual(report['aws_calls'], 0)
            self.assertFalse(report['application_deployed']);self.assertFalse(report['service_verified'])
            self.assertFalse(list(out.rglob('*.service')))
            self.assertTrue((out / 'templates/application-web.service.in').is_file())
            manifest = json.loads((out / 'manifest.json').read_text())
            for name, digest in manifest['files'].items():
                self.assertEqual(hashlib.sha256((out / name).read_bytes()).hexdigest(), digest)
            for path in [out, *out.rglob('*')]:
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700 if path.is_dir() else 0o600)

    def test_ready_bundle_does_not_run_or_install_review_units(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / '.state/handoff'
            with patch('awscli.Aws') as aws, patch('subprocess.run') as run:
                report = prepare(self.c, self.contract, out, root=tmp)
            aws.assert_not_called();run.assert_not_called()
            self.assertTrue(report['review_artifacts_rendered']);self.assertEqual(report['commands_executed'], 0)
            self.assertFalse(report['application_deployed']);self.assertEqual(len(list(out.rglob('*.service'))), 2)

    def test_invalid_types_and_unknown_fields_block_without_traceback(self):
        cases = [('web', None), ('web', {'workers': False}), ('web', {'start_argv': 'shell string'}),
                 ('single_active', {'working_directory': []}), ('single_active', {'query_key': 4}),
                 ('elasticsearch', {'application_transport': {}}), ('web', {'unknown': 'value'})]
        for section, changes in cases:
            with self.subTest(section=section, changes=changes):
                contract = copy.deepcopy(self.contract)
                if changes is None:contract[section] = None
                else:contract[section].update(changes)
                self.assertFalse(plan(self.c, contract)['contract_inputs_complete'])

    def test_foreground_and_private_bind_contract_rejects_detached_wrappers(self):
        for argv in (['/bin/bash', '-c', 'start'], ['/usr/bin/env', '/opt/app'], ['/usr/bin/nohup', '/opt/app'],
                     ['/usr/bin/systemd-run', '/opt/app'], ['/opt/app', '--daemon=yes'],
                     ['/opt/app', '--reload=true'], ['/opt/app', '--host', '0.0.0.0'],
                     ['/opt/app', '--deploy-mode=cluster']):
            contract = copy.deepcopy(self.contract);contract['web']['start_argv'] = argv + ['{CONTROL_PRIVATE_IP}']
            self.assertFalse(plan(self.c, contract)['contract_inputs_complete'])
        contract = copy.deepcopy(self.contract);contract['single_active']['supervised_argv'] = ['/opt/spark-submit', '/opt/app.py']
        self.assertFalse(plan(self.c, contract)['contract_inputs_complete'])

    def test_foreign_generation_query_and_encoded_traversal_are_rejected(self):
        uri = self.contract['single_active']['checkpoint_reference']
        for candidate in (uri.replace('g-unit-test', 'g-old'), uri.replace('weather-query/', 'other-query/'),
                          uri.replace('s3a://', 's3://'), uri + '../escape/', uri + '%2e%2e/escape/',
                          uri + '_infra-tests/', uri + '?reset=true', uri + '#fragment', uri + 'back\\slash'):
            contract = copy.deepcopy(self.contract);contract['single_active']['checkpoint_reference'] = candidate
            self.assertFalse(plan(self.c, contract)['contract_inputs_complete'], candidate)
        contract = copy.deepcopy(self.contract);contract['single_active']['query_key'] = '_infra-tests'
        self.assertFalse(plan(self.c, contract)['contract_inputs_complete'])

    def test_inline_credentials_never_enter_a_bundle_or_diagnostic(self):
        secret = 'fixture-private-value'
        for section, key, value in [('web', 'start_argv', ['/opt/app', '--password', secret]),
                                    ('elasticsearch', 'credential_reference', 'https://user:' + secret + '@host'),
                                    ('web', 'password', secret)]:
            contract = copy.deepcopy(self.contract);contract[section][key] = value
            report = plan(self.c, contract)
            self.assertTrue(report['unsafe_input_fields']);self.assertNotIn(secret, json.dumps(report))
            with tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / '.state/review'
                with self.assertRaises(ValueError) as error:prepare(self.c, contract, out, root=tmp)
                self.assertNotIn(secret, str(error.exception));self.assertFalse(out.exists())

    def test_root_runtime_and_database_credentials_cannot_be_es_app_inputs(self):
        for candidate in ('/etc/music-cluster/runtime.json', '/etc/music-cluster/control/fencing/runtime.json',
                          '/etc/music-cluster/control/database.env', '/etc/music-cluster/control/weather-database.env'):
            contract = copy.deepcopy(self.contract);contract['elasticsearch']['credential_reference'] = candidate
            self.assertFalse(plan(self.c, contract)['contract_inputs_complete'])

    def test_paths_and_unit_line_injection_are_rejected(self):
        for candidate in ('relative', '/opt/music-apps/control/../escape', '/tmp/app', '/opt/music-apps/control\nExecStart=/tmp/evil'):
            contract = copy.deepcopy(self.contract);contract['web']['working_directory'] = candidate
            self.assertFalse(plan(self.c, contract)['contract_inputs_complete'])
        contract = copy.deepcopy(self.contract);contract['web']['start_argv'].append('x\nUser=root')
        self.assertFalse(plan(self.c, contract)['contract_inputs_complete'])

    def test_systemd_formatting_preserves_literal_argument_characters(self):
        contract = copy.deepcopy(self.contract)
        contract['web']['start_argv'] += ['--label', '100% ${APP} "quoted" \\path']
        unit = previews(self.c, contract)['control-a/music-web.service']
        exec_line = next(line for line in unit.splitlines() if line.startswith('ExecStart='))
        self.assertIn('ExecStart=:', exec_line);self.assertIn('100%% ${APP} \\"quoted\\" \\\\path', exec_line)

    def test_output_must_be_new_private_state_directory_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);out = root / '.state/review'
            prepare(self.c, self.contract, out, root=root)
            before = (out / 'manifest.json').read_bytes()
            with self.assertRaises(ValueError):prepare(self.c, self.contract, out, root=root)
            self.assertEqual((out / 'manifest.json').read_bytes(), before)
            with self.assertRaises(ValueError):prepare(self.c, self.contract, root / 'public', root=root)
            (root / '.state/link').symlink_to(root / 'outside')
            with self.assertRaises(ValueError):prepare(self.c, self.contract, root / '.state/link/review', root=root)

    def test_sample_config_never_loads_actual_lifecycle_and_real_input_requires_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);config = root / 'project.json'
            c = load(ROOT / 'config/project.example.json');config.write_text(json.dumps(c))
            self.assertIsNone(configuration(config, root=root).get('generation'))
            c['example_only'] = False;config.write_text(json.dumps(c))
            resolved = root / 'resolved.json';c['generation'] = 'g-unit-test';resolved.write_text(json.dumps(c))
            state = root / '.state/lifecycle' / prefix(c) / 'current.json';state.parent.mkdir(parents=True)
            state.write_text(json.dumps({'state': 'ready', 'source_sha256': hashlib.sha256(config.read_bytes()).hexdigest(),
                                         'resolved_config': str(resolved)}))
            self.assertEqual(configuration(config, root=root)['generation'], 'g-unit-test')
            config.write_text(config.read_text() + '\n')
            with self.assertRaises(ValueError):configuration(config, root=root)


if __name__ == '__main__':unittest.main()
