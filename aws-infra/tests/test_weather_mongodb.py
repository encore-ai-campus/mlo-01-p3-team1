"""Weather namespace, immutable credentials and exact ingress security boundaries."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
import project, templates, application_contract
spec = importlib.util.spec_from_file_location('weather_mongodb', ROOT / 'installer/weather_mongodb.py')
weather = importlib.util.module_from_spec(spec);spec.loader.exec_module(weather)


class WeatherBoundaries(unittest.TestCase):
    def setUp(self):
        self.payload = {'aws': {'project': 'example', 'environment': 'aws-dev', 'generation': 'g-test'},
                        'node': 'control-a', 'database': {'host': '10.84.16.20', 'port': 27017,
                        'database': 'weather', 'username': 'weather_app', 'auth_source': 'weather'}, 'password': 'x' * 64}
        self.runtime = {'aws': copy.deepcopy(self.payload['aws']), 'node': {'name': 'control-a', 'role': 'control'}, 'env': {'ENVIRONMENT': 'aws'}}

    def test_advertising_credentials_and_wrong_namespace_rejected(self):
        weather.validate(self.payload, self.runtime)
        for key, value in [('database', 'advertising'), ('username', 'advertising_app'), ('auth_source', 'admin'), ('host', '8.8.8.8')]:
            c = copy.deepcopy(self.payload);c['database'][key] = value
            with self.assertRaises(ValueError):weather.validate(c, self.runtime)
        c = copy.deepcopy(self.payload);c['aws']['generation'] = 'old'
        with self.assertRaises(ValueError):weather.validate(c, self.runtime)

    def test_executor_or_other_host_cannot_receive_weather_payload(self):
        for role in ('spark', 'advertising', 'postgresql'):
            r = copy.deepcopy(self.runtime);r['node']['role'] = role
            with self.assertRaises(ValueError):weather.validate(self.payload, r)
        r = copy.deepcopy(self.runtime);r['node']['name'] = 'control-b'
        with self.assertRaises(ValueError):weather.validate(self.payload, r)

    def test_environment_has_separate_names_and_verified_tls(self):
        values = dict(line.split('=', 1) for line in weather.environment(self.payload).splitlines())
        self.assertTrue(all(k.startswith('WEATHER_MONGO_') for k in values))
        self.assertEqual(values['WEATHER_MONGO_AUTH_SOURCE'], 'weather')
        self.assertEqual(values['WEATHER_MONGO_TLS'], 'true')
        self.assertNotIn('MONGO_ADMIN_PASSWORD', values)

    def test_idempotent_publish_preserves_secret_bytes_and_permissions(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'weather.env'
            kwargs = {'uid': os.getuid(), 'gid': os.getgid(), 'mode': 0o640}
            self.assertTrue(weather.write_once(path, 'private fixture\n', **kwargs))
            inode = path.stat().st_ino
            self.assertFalse(weather.write_once(path, 'private fixture\n', **kwargs))
            self.assertEqual(path.stat().st_ino, inode);self.assertEqual(path.stat().st_mode & 0o777, 0o640)
            with self.assertRaises(ValueError):weather.write_once(path, 'rotated fixture\n', **kwargs)
            self.assertEqual(path.read_text(), 'private fixture\n')

    def test_symlink_and_drift_are_not_repaired_by_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder);real = root / 'real';real.write_text('preserved');link = root / 'weather.env';link.symlink_to(real)
            with self.assertRaises(ValueError):weather.write_once(link, 'different')
            self.assertEqual(real.read_text(), 'preserved')

    def test_shell_reads_multiline_private_environment_without_password_in_script(self):
        script = weather.probe_script('a' * 16, 'first')
        self.assertIn('.split("\\n")', script)
        self.assertNotIn('.split("\\\\n")', script)
        self.assertNotIn(self.payload['password'], script)
        for test_id, phase in [('../business', 'first'), ('a' * 16, 'reset')]:
            with self.assertRaises(ValueError):weather.probe_script(test_id, phase)

    def test_network_adds_only_exact_control_sources_and_keeps_advertising(self):
        c = project.load(ROOT / 'config/project.example.json');nodes = [n for a in c['accounts'] for n in a['nodes']]
        mongo = next(n for n in nodes if n['role'] == 'mongodb');rules = templates.ingress_sources(c, mongo)
        expected = {n['private_ip'] + '/32' for n in nodes if n['role'] in ('control', 'advertising')}
        self.assertEqual({r['CidrIp'] for r in rules}, expected);self.assertEqual(len(rules), 3)
        self.assertTrue(all(r['FromPort'] == r['ToPort'] == 27017 and r['IpProtocol'] == 'tcp' for r in rules))
        self.assertEqual(len(c['peering_pairs']), 7)

    def test_active_control_design_checks_both_candidates(self):
        c = project.load(ROOT / 'config/project.example.json');contract = json.loads((ROOT / 'config/application-contract.example.json').read_text())
        result = application_contract.plan(c, contract)
        self.assertFalse(result['blocked_choices']);self.assertFalse(result['application_or_ha_verified'])
        self.assertFalse(result['contract_inputs_complete'])


if __name__ == '__main__':unittest.main()
