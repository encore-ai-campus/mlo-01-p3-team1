"""Offline data-quality/replay contracts; no external services are used."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from pipeline.weather.quality_report import build_report, read_jsonl
from pipeline.weather.replay import compare_rows, replay_records

NOW = '2026-11-03T12:40:00+09:00'
GRIDS = {(60, 127): {'nx': 60, 'ny': 127, 'lat': 37.56, 'lon': 126.98}}


def event(issue='2026-11-03T11:30:00+09:00', received='2026-11-03T11:45:00+09:00', raw='21'):
    return {'schema_version': 1, 'source': 'vsrt', 'kind': 'forecast', 'category': 'T1H',
            'issued_at': issue, 'target_at': '2026-11-03T13:00:00+09:00',
            'received_at': received, 'source_hash': 'sample-' + raw, 'raw_path': None,
            'run_id': 'unit', 'mapping_version': '2026-07-01', 'spatial_basis': 'dfs_5km',
            'readings': [{'nx': 60, 'ny': 127, 'raw': raw}]}


def log(identifier, ok, attempt=1, requested='2026-11-03T12:01:00+09:00'):
    return {'request_id': identifier, 'ok': ok, 'attempt': attempt, 'requested_at': requested,
            'stage': 'collection', 'elapsed_seconds': 1, 'log_id': f'{identifier}:{attempt}'}


class QualityTests(unittest.TestCase):
    def test_retry_and_duplicate_logs_do_not_inflate_request_coverage(self):
        expected = [{'request_id': 'a', 'due_at': '2026-11-03T12:00:00+09:00'},
                    {'request_id': 'b', 'due_at': '2026-11-03T12:00:00+09:00'}]
        successful = log('a', True, 2)
        result = build_report(expected, [log('a', False), successful, successful],
                              now=NOW, input_complete=True)
        self.assertEqual(result['unique_attempts'], 2)
        self.assertEqual(result['attempt_success_rate'], .5)
        self.assertEqual(result['due_request_completion_rate'], .5)
        self.assertEqual(result['duplicate_log_records'], 1)
        self.assertEqual((result['completed'], result['missing']), (1, 1))
        self.assertEqual(result['status'], 'attention')

    def test_partial_logs_never_report_complete_success(self):
        expected = [{'request_id': 'a', 'due_at': '2026-11-03T12:00:00+09:00'}]
        result = build_report(expected, [log('a', True)], now=NOW)
        self.assertEqual(result['status'], 'incomplete')
        self.assertFalse(result['input_complete'])

    def test_no_expected_work_and_no_observations_have_no_fake_rates(self):
        result = build_report([], [], now=NOW, input_complete=True)
        self.assertEqual(result['status'], 'no_expected_requests')
        self.assertIsNone(result['attempt_success_rate'])
        self.assertIsNone(result['due_request_completion_rate'])

    def test_deadline_and_completion_lateness_use_elapsed_time(self):
        expected = [{'request_id': 'a', 'due_at': '2026-11-03T12:00:00+09:00'}]
        result = build_report(expected, [], now='2026-11-03T12:19:59+09:00', input_complete=True)
        self.assertEqual(result['waiting'], 1)
        result = build_report(expected, [], now='2026-11-03T12:20:00+09:00', input_complete=True)
        self.assertEqual(result['missing'], 1)
        result = build_report(expected, [log('a', True, requested='2026-11-03T12:20:00+09:00')],
                              now=NOW, input_complete=True)
        self.assertEqual(result['late_completed'], 1)

    def test_invalid_and_conflicting_logs_make_report_incomplete_without_leaking_fields(self):
        expected = [{'request_id': 'a', 'due_at': '2026-11-03T12:00:00+09:00'}]
        invalid = log('a', True)
        invalid['requested_at'] = 'invalid-secret-value'
        conflict = log('a', True)
        conflict['api_key'] = 'do-not-copy'
        result = build_report(expected, [invalid, log('a', False), conflict], now=NOW, input_complete=True)
        self.assertEqual(result['status'], 'incomplete')
        self.assertNotIn('do-not-copy', json.dumps(result))
        self.assertNotIn('invalid-secret-value', json.dumps(result))
        self.assertEqual(len(result['issues']), 2)

    def test_naive_clock_and_duplicate_plan_are_rejected(self):
        with self.assertRaises(ValueError):
            build_report([], [], now='2026-11-03T12:00:00')
        plan = {'request_id': 'a', 'due_at': NOW}
        with self.assertRaises(ValueError):
            build_report([plan, plan], [], now=NOW)

    def test_truncated_read_and_limit_are_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'logs.jsonl'
            path.write_bytes(b'{"ok":true}\n{"ok":')
            records, metadata = read_jsonl(path)
            self.assertEqual(len(records), 1)
            self.assertFalse(metadata['complete_read'])
            self.assertEqual(metadata['issues'][0]['code'], 'unterminated_line')
            records, metadata = read_jsonl(path, max_records=1)
            self.assertEqual(metadata['issues'][0]['code'], 'record_limit')


class ReplayTests(unittest.TestCase):
    def test_repeated_receipts_coalesce_but_different_issuances_remain(self):
        first = event()
        retry = event(received='2026-11-03T11:46:00+09:00')
        later_issue = event(issue='2026-11-03T12:30:00+09:00',
                            received='2026-11-03T12:45:00+09:00', raw='24')
        rows, report = replay_records([first, first, retry, later_issue], GRIDS)
        self.assertEqual(len(rows), 2)
        self.assertEqual(report['duplicate_rows'], 2)
        self.assertEqual(rows[0]['received_at'], '2026-11-03T02:46:00+00:00')
        self.assertEqual([row['measurement']['value'] for row in rows], [21, 24])
        self.assertEqual(len({row['history_id'] for row in rows}), 2)

    def test_same_issuance_correction_is_order_independent(self):
        original = event()
        correction = event(received='2026-11-03T11:46:00+09:00', raw='23')
        forward, report = replay_records([original, correction], GRIDS)
        reverse, reverse_report = replay_records([correction, original], GRIDS)
        self.assertEqual(forward, reverse)
        self.assertEqual(report['output_sha256'], reverse_report['output_sha256'])
        self.assertEqual(forward[0]['measurement']['value'], 23)
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            replay_records([original, event(raw='25')], GRIDS)

    def test_time_offsets_and_half_open_range(self):
        equivalent = event()
        equivalent['issued_at'] = '2026-11-03T02:30:00Z'
        equivalent['target_at'] = '2026-11-03T04:00:00Z'
        rows, _ = replay_records([event(), equivalent], GRIDS,
            start='2026-11-03T04:00:00Z', end='2026-11-03T04:01:00Z')
        self.assertEqual(len(rows), 1)
        rows, _ = replay_records([event()], GRIDS, end='2026-11-03T04:00:00Z')
        self.assertEqual(rows, [])

    def test_offset_provenance_and_mapping_changes_are_explicit(self):
        records = [{'topic': 'weather.v1', 'partition': 0, 'offset': offset, 'event': event()}
                   for offset in (2, 4)]
        _, report = replay_records(records, GRIDS, mapping_version='2026-07-01')
        self.assertEqual(report['offset_ranges'][0]['offset_gap_count'], 1)
        self.assertFalse(report['export_completeness_verified'])
        with self.assertRaisesRegex(ValueError, 'mapping_version_mismatch'):
            replay_records(records, GRIDS, mapping_version='other')
        _, report = replay_records(records, GRIDS, mapping_version='other', allow_mapping_change=True)
        self.assertTrue(report['mapping_change_allowed'])
        records[1]['offset'] = 2
        records[1]['event'] = event(raw='23')
        with self.assertRaisesRegex(ValueError, 'conflicting_offset_payload'):
            replay_records(records, GRIDS)

    def test_business_comparison_separates_metadata_from_values(self):
        original, _ = replay_records([event()], GRIDS)
        metadata = copy.deepcopy(original)
        metadata[0]['received_at'] = '2026-11-03T03:00:00+00:00'
        result = compare_rows(original, metadata)
        self.assertTrue(result['business_equal'])
        self.assertEqual(result['metadata_only_rows'], 1)
        changed = copy.deepcopy(metadata)
        changed[0]['measurement']['value'] = 99
        result = compare_rows(original, changed)
        self.assertFalse(result['business_equal'])
        self.assertEqual(result['changes'][0]['kind'], 'changed')
        with self.assertRaisesRegex(ValueError, 'duplicate_history_key'):
            compare_rows(original + original, changed)

    def test_replay_does_not_call_live_store(self):
        with patch('pipeline.weather.es_latest.write_grid', side_effect=AssertionError('live write')):
            result, _ = replay_records([event()], GRIDS)
        self.assertEqual(len(result), 1)

    def test_cli_writes_new_artifacts_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / 'events.jsonl'
            input_path.write_text(json.dumps(event()) + '\n', encoding='utf-8')
            mapping = root / 'mapping.json'
            mapping.write_text(json.dumps({'version': '2026-07-01', 'grids': list(GRIDS.values())}), encoding='utf-8')
            command = [sys.executable, '-m', 'pipeline.weather.replay', 'replay',
                       '--input', str(input_path), '--mapping', str(mapping),
                       '--output', str(root / 'rows.jsonl'), '--report', str(root / 'report.json')]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads((root / 'report.json').read_text(encoding='utf-8'))
            self.assertEqual(report['history_rows'], 1)
            self.assertEqual(len(report['input_sha256']), 64)
            before = (root / 'rows.jsonl').read_bytes()
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual((root / 'rows.jsonl').read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
