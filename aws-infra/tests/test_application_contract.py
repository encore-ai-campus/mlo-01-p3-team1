"""Protect service boundaries and reject incomplete bulk acknowledgements."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
import application_contract
import project
spec = importlib.util.spec_from_file_location('es_bulk_probe', ROOT / 'installer/es_bulk_probe.py')
probe = importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)


class BulkSafety(unittest.TestCase):
    def setUp(self):
        self.index = 'cluster-smoke-rest-' + 'a' * 16
        self.docs = [('row-0', {'id': 0, 'score': 0}), ('row-1', {'id': 1, 'score': 10})]
        self.good = {'errors': False, 'items': [{'index': {'_index': self.index, '_id': name, 'status': 201}} for name, _ in self.docs]}

    def test_ndjson_final_newline_and_deterministic_ids(self):
        body = probe.bulk_body(self.index, self.docs)
        self.assertTrue(body.endswith(b'\n'))
        self.assertEqual(json.loads(body.splitlines()[0])['index']['_id'], 'row-0')
        self.assertEqual(body, probe.bulk_body(self.index, self.docs))

    def test_business_index_duplicate_ids_and_large_payload_rejected(self):
        for index, docs in [('weather-current', self.docs), (self.index, self.docs * 2),
                            (self.index, [('row-0', {'text': 'x' * 262144})])]:
            with self.assertRaises(ValueError):probe.bulk_body(index, docs)

    def test_http_200_partial_mapping_error_fails(self):
        bad = copy.deepcopy(self.good);bad['errors'] = True
        bad['items'][1]['index'].update(status=400, error={'type': 'mapper_parsing_exception'})
        with self.assertRaises(probe.BulkRejected):probe.check_bulk(bad, self.index, self.docs)

    def test_missing_reordered_cross_index_acknowledgements_fail(self):
        missing = copy.deepcopy(self.good);missing['items'].pop()
        reordered = copy.deepcopy(self.good);reordered['items'].reverse()
        other = copy.deepcopy(self.good);other['items'][0]['index']['_index'] = 'weather-other'
        for response in (missing, reordered, other):
            with self.assertRaises(probe.BulkRejected):probe.check_bulk(response, self.index, self.docs)
        self.assertEqual(probe.check_bulk(self.good, self.index, self.docs), 2)

    def test_hidden_failure_and_inconsistent_flag_fail(self):
        hidden = copy.deepcopy(self.good);hidden['items'][0]['index']['status'] = 429
        inconsistent = copy.deepcopy(self.good);inconsistent['errors'] = True
        for response in (hidden, inconsistent):
            with self.assertRaises(probe.BulkRejected):probe.check_bulk(response, self.index, self.docs)

    def test_private_https_only_and_redirect_rejection(self):
        cfg = {'test_id': 'a' * 16, 'project': 'example', 'environment': 'aws-dev', 'generation': 'g-test',
               'index': self.index, 'username': 'pipeline_writer', 'password': 'fixture',
               'ca': '/etc/music-cluster/control/tls/ca.crt', 'urls': ['https://10.80.16.11:9200', 'https://10.81.17.11:9200', 'https://10.82.18.11:9200']}
        self.assertIs(probe.settings(cfg), cfg)
        for url in ('http://10.80.16.11:9200', 'https://example.com:9200', 'https://user:pass@10.80.16.11:9200', 'https://10.80.16.11:9200/elsewhere'):
            bad = copy.deepcopy(cfg);bad['urls'][0] = url
            with self.assertRaises(ValueError):probe.settings(bad)
        with self.assertRaises(ValueError):probe.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://example.com')


class ApplicationRoutes(unittest.TestCase):
    def setUp(self):
        self.c = project.load(ROOT / 'config/project.example.json')
        self.contract = json.loads((ROOT / 'config/application-contract.example.json').read_text())
        self.before = copy.deepcopy(self.c)

    def test_control_weather_mongo_ingress_is_explicit_in_updated_design(self):
        r = application_contract.route(self.c, 'control-a', 'mongodb', 27017)
        self.assertTrue(r['direct_route_designed']);self.assertTrue(r['destination_ingress_designed'])
        self.assertTrue(r['design_path_available']);self.assertFalse(r['live_connectivity_verified'])

    def test_no_transitive_spark_route_only_advertising_allowed(self):
        for name in ('spark-01', 'spark-02', 'spark-03'):
            r = application_contract.route(self.c, name, 'mongodb', 27017)
            self.assertFalse(r['direct_route_designed']);self.assertFalse(r['destination_ingress_designed'])
        self.assertTrue(application_contract.route(self.c, 'advertising', 'mongodb', 27017)['design_path_available'])

    def test_all_existing_control_spark_es_routes_available_in_design(self):
        for source in ('control-a', 'control-b', 'spark-01', 'spark-02', 'spark-03'):
            for target in ('es-01', 'es-02', 'es-03'):
                self.assertTrue(application_contract.route(self.c, source, target, 9200)['design_path_available'])

    def test_offline_plan_keeps_app_contract_unselected(self):
        with patch('awscli.Aws') as aws:report = application_contract.plan(self.c, self.contract)
        aws.assert_not_called();self.assertEqual(self.c, self.before)
        self.assertFalse(report['contract_inputs_complete']);self.assertFalse(report['application_or_ha_verified'])
        self.assertIsNone(report['application_es_transport_selected'])
        self.assertFalse(report['business_application_source_required_for_infrastructure'])

    def test_unreachable_writer_and_advertising_credentials_blocked(self):
        self.contract['weather_mongodb'].update(writer_node='spark-01', database='advertising', username='advertising_app', auth_source='advertising')
        report = application_contract.plan(self.c, self.contract)
        self.assertEqual(len(report['blocked_choices']), 4);self.assertFalse(report['contract_inputs_complete'])


if __name__ == '__main__':unittest.main()
