"""SQL 결과와 CLI 실패 경계를 검사. 운영 DB·API·Kafka 미사용."""
import contextlib
import copy
import hashlib
import io
import json
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from pipeline.weather.history_validation import (
    HistoryValidationError, KEY_FIELDS, analyze_history, main, read_jsonl,
)


@contextlib.contextmanager
def working_directory():
    # Inherit workspace ACLs on Windows. tempfile's explicit 0700 directory
    # creation may exclude the separate sandbox identity used by the test runner.
    test_root = Path(__file__).resolve().parent
    folder = test_root / ('tmp-history-' + uuid.uuid4().hex)
    folder.mkdir()
    try:
        yield folder
    finally:
        if folder.resolve().parent != test_root:
            raise RuntimeError('invalid_test_cleanup_path')
        for path in folder.iterdir():
            if not path.is_file() or path.is_symlink():
                raise RuntimeError('unexpected_test_output')
            path.unlink()
        folder.rmdir()


def row(**changes):
    result = dict(source='vsrt', kind='forecast', nx=60, ny=127, category='T1H',
                  issued_at='2026-11-03T12:30:00+09:00', target_at='2026-11-03T15:00:00+09:00',
                  received_at='2026-11-03T12:40:00+09:00',
                  measurement={'status': 'valid', 'value': 22.0, 'unit': 'degC'},
                  source_hash='original', rule_version='normalize_v2')
    result.update(changes)
    return result


class HistoryValidationTests(unittest.TestCase):
    def test_duplicate_receipt_and_different_issuance_are_distinct(self):
        rows = [row(), row(received_at='2026-11-03T12:41:00+09:00'),
                row(issued_at='2026-11-03T13:30:00+09:00', received_at='2026-11-03T13:40:00+09:00')]
        original = copy.deepcopy(rows)
        report = analyze_history(rows)
        self.assertEqual(report['counts'], dict(input_rows=3, unique_history_keys=2,
                                               duplicate_keys=1, duplicate_rows=1))
        self.assertEqual(rows, original)
        self.assertIsNone(report['completeness']['missing_keys'])

    def test_equal_instants_in_different_timezones_share_one_key(self):
        report = analyze_history([row(), row(issued_at='2026-11-03T03:30:00Z',
                                             target_at='2026-11-03T06:00:00+00:00')])
        self.assertEqual(report['counts']['unique_history_keys'], 1)

    def test_expected_scope_missing_unexpected_and_duplicate_manifest(self):
        first, missing, extra = row(), row(category='REH'), row(category='PTY')
        expected = [{key: record[key] for key in KEY_FIELDS} for record in (first, missing, missing)]
        result = analyze_history([first, first, extra], expected)['completeness']
        self.assertEqual(result, dict(status='missing', scope='supplied_manifest_only',
                                      expected_keys=2, missing_keys=1, unexpected_keys=1))

    def test_zero_and_unknown_scope_are_distinct(self):
        unknown = analyze_history([])
        empty = analyze_history([], [])
        self.assertEqual(unknown['counts']['input_rows'], 0)
        self.assertEqual(unknown['completeness']['status'], 'not_assessed')
        self.assertEqual(empty['completeness']['status'], 'empty_scope')
        self.assertIsNone(unknown['timing']['receipt_minus_issue_seconds']['mean'])

    def test_null_zero_invalid_and_inconsistent_status(self):
        report = analyze_history([
            row(measurement={'status': 'valid', 'value': 0}),
            row(measurement={'status': 'missing', 'value': None}),
            row(measurement={'status': 'out_of_range', 'value': None}),
            row(measurement={'status': 'valid', 'value': None}),
        ])
        self.assertEqual(report['checks']['null_values'], 3)
        self.assertEqual(report['checks']['inconsistent_status_values'], 1)
        self.assertEqual(report['measurement_status_counts'], {'valid': 2, 'missing': 1, 'out_of_range': 1})

    def test_delay_boundary_forecast_lead_and_microseconds(self):
        report = analyze_history([row(), row(received_at='2026-11-03T12:40:00.000001+09:00')],
                                 late_after_seconds=600)
        self.assertEqual(report['checks']['late_rows'], 1)
        self.assertEqual(report['checks']['received_before_issue'], 0)
        self.assertEqual(report['timing']['target_minus_issue_seconds']['mean'], 9000)
        self.assertLess(report['timing']['receipt_minus_target_seconds']['max'], 0)
        self.assertAlmostEqual(report['timing']['receipt_minus_issue_seconds']['max'], 600.000001, places=6)

    def test_future_issue_is_reported_without_hiding_negative_delay(self):
        report = analyze_history([row(received_at='2026-11-03T12:29:59+09:00')])
        self.assertEqual(report['checks']['received_before_issue'], 1)
        self.assertEqual(report['timing']['receipt_minus_issue_seconds']['min'], -1)

    def test_large_finite_delay_threshold_does_not_overflow_sqlite_binding(self):
        thresholds = (2 ** 63 - 1, 2 ** 63, 10 ** 30, 10 ** 308,
                      float.fromhex('0x1.fffffffffffffp+1023'))
        for threshold in thresholds:
            for records in ([], [row()]):
                with self.subTest(threshold=threshold, input_rows=len(records)):
                    report = analyze_history(records, late_after_seconds=threshold)
                    self.assertEqual(report['checks']['late_rows'], 0)
                    self.assertEqual(report['late_after_seconds'], float(threshold))
                    json.dumps(report, allow_nan=False)

    def test_invalid_key_clock_measurement_and_threshold_fail(self):
        bad_rows = [row(source=None), row(nx=True), row(ny=254), row(category=None),
                    row(target_at='2026-11-03T15:00:00'), row(received_at='not-a-time'),
                    row(measurement={'status': 'valid', 'value': float('nan')}),
                    row(measurement={'status': 'valid', 'value': 10 ** 400}),
                    row(measurement={'status': 'valid', 'value': True}),
                    row(measurement={'status': 'secret-token', 'value': None})]
        for record in bad_rows:
            with self.subTest(record=record), self.assertRaises(HistoryValidationError):
                analyze_history([record])
        for threshold in (-1, float('inf'), float('nan'), True, 10 ** 309, 10 ** 400):
            with self.subTest(threshold=threshold), self.assertRaises(HistoryValidationError):
                analyze_history([], late_after_seconds=threshold)

    def test_sql_injection_is_not_executed(self):
        with self.assertRaises(HistoryValidationError):
            analyze_history([row(category="T1H'); DROP TABLE rows;--")])
        self.assertEqual(analyze_history([row()])['counts']['input_rows'], 1)

    def test_strict_jsonl_and_exact_input_hash(self):
        with working_directory() as folder:
            path = Path(folder) / 'input.jsonl'
            payload = ('\n' + json.dumps(row()) + '\n').encode()
            path.write_bytes(payload)
            records, digest = read_jsonl(path)
            self.assertEqual(len(records), 1)
            self.assertEqual(digest, hashlib.sha256(payload).hexdigest())
            for text in ('{"source":', '{"x": 1, "x": 2}', '{"x": NaN}', '[]'):
                path.write_text(text, encoding='utf-8')
                with self.subTest(text=text), self.assertRaises(HistoryValidationError):
                    read_jsonl(path)

    def test_cli_writes_only_new_report_and_preserves_input(self):
        with working_directory() as folder:
            source, output = Path(folder) / 'input.jsonl', Path(folder) / 'report.json'
            source.write_text(json.dumps(row()) + '\n', encoding='utf-8')
            before = source.read_bytes()
            self.assertEqual(main(['--input', str(source), '--output', str(output)]), 0)
            report = json.loads(output.read_text(encoding='utf-8'))
            self.assertEqual(report['counts']['input_rows'], 1)
            saved = output.read_bytes()
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(['--input', str(source), '--output', str(output)]), 2)
                self.assertEqual(main(['--input', str(source), '--output', str(source)]), 2)
            self.assertEqual(output.read_bytes(), saved)
            self.assertEqual(source.read_bytes(), before)

    def test_report_does_not_include_raw_or_credentials(self):
        secret = 'DO_NOT_EXPOSE_API_KEY'
        record = row(raw_path=secret, url=secret, measurement={'status': 'valid', 'value': 22, 'raw': secret})
        output = json.dumps(analyze_history([record]))
        self.assertNotIn(secret, output)
        with working_directory() as folder:
            source = Path(folder) / 'input.jsonl'
            source.write_text(json.dumps(row(received_at=secret)), encoding='utf-8')
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                self.assertEqual(main(['--input', str(source)]), 2)
            self.assertNotIn(secret, stderr.getvalue())
            self.assertIn('invalid_received_at', stderr.getvalue())

    def test_only_in_memory_read_only_sql_is_used(self):
        import sqlite3
        real_connect = sqlite3.connect
        paths = []
        statements = []
        def tracked_connect(path):
            paths.append(path)
            connection = real_connect(path)
            connection.set_trace_callback(statements.append)
            return connection
        with patch('pipeline.weather.history_validation.sqlite3.connect', side_effect=tracked_connect):
            analyze_history([row()], [row()])
        self.assertEqual(paths, [':memory:'])
        for statement in statements:
            self.assertNotIn('CREATE TABLE', statement)
            self.assertNotIn('INSERT INTO', statement)
        self.assertEqual(statements[0], 'PRAGMA query_only = ON')


if __name__ == '__main__':
    unittest.main()
