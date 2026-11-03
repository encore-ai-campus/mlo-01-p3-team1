"""정제 이력 JSONL의 SQL 검사. 메모리 SELECT만 실행하며 운영 저장소에 접속하지 않음.

이 도구는 제공된 파일의 품질을 검사한다. 파일 수신 이전의 누락이나 운영의 장기
이력 보존을 입증하지 않는다. expected에는 검사할 범위의 업무 키를 명시한다.
"""
import argparse
import hashlib
import json
import math
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

KEY_FIELDS = ('source', 'kind', 'nx', 'ny', 'category', 'issued_at', 'target_at')
MEASUREMENT_STATUSES = frozenset((
    'valid', 'missing', 'invalid_value', 'encoding_required', 'invalid_code',
    'unsupported_source', 'out_of_range', 'unit_unverified',
))
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


class HistoryValidationError(ValueError):
    """Only a safe error code and record/line position may be exposed."""


def _timestamp(value, field):
    if not isinstance(value, str):
        raise HistoryValidationError('invalid_' + field)
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.utcoffset() is None:
            raise ValueError
        parsed = parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        raise HistoryValidationError('invalid_' + field) from None
    delta = parsed - EPOCH
    micros = (delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds
    return parsed.isoformat(timespec='microseconds'), micros


def _project(row, expected=False):
    if not isinstance(row, dict):
        raise HistoryValidationError('record_must_be_object')
    result = {}
    for field in KEY_FIELDS:
        if field not in row or row[field] is None:
            raise HistoryValidationError('missing_' + field)
    if row['source'] not in ('odam', 'vsrt', 'shrt', 'KIMG'):
        raise HistoryValidationError('invalid_source')
    if row['kind'] not in ('observation', 'forecast'):
        raise HistoryValidationError('invalid_kind')
    for field, upper in (('nx', 149), ('ny', 253)):
        if type(row[field]) is not int or not 1 <= row[field] <= upper:
            raise HistoryValidationError('invalid_' + field)
    category = row['category']
    if not isinstance(category, str) or not category.isascii() or not category.isalnum() or len(category) > 16:
        raise HistoryValidationError('invalid_category')
    for field in KEY_FIELDS[:5]:
        result[field] = row[field]
    for field in ('issued_at', 'target_at'):
        result[field], result[field + '_us'] = _timestamp(row[field], field)
    if expected:
        return result
    result['received_at'], result['received_at_us'] = _timestamp(row.get('received_at'), 'received_at')
    measurement = row.get('measurement')
    if not isinstance(measurement, dict):
        raise HistoryValidationError('missing_measurement')
    status = measurement.get('status')
    if not isinstance(status, str) or status not in MEASUREMENT_STATUSES:
        raise HistoryValidationError('invalid_measurement_status')
    value = measurement.get('value')
    if value is not None:
        try:
            finite_number = type(value) in (int, float) and math.isfinite(value)
        except OverflowError:
            finite_number = False
        if not finite_number:
            raise HistoryValidationError('invalid_measurement_value')
    result['status'] = status
    result['value_is_null'] = int(value is None)
    return result


def _prepare(rows, expected=False):
    prepared = []
    for number, row in enumerate(rows, 1):
        try:
            prepared.append(_project(row, expected=expected))
        except HistoryValidationError as error:
            raise HistoryValidationError(f'record_{number}:{error}') from None
    return prepared


# Parameterized JSON values contain only the fields projected above. There is no
# user-supplied SQL, identifier interpolation, CREATE TABLE, or disk database.
ROWS_CTE = """
WITH rows AS (
  SELECT json_extract(value, '$.source') AS source,
         json_extract(value, '$.kind') AS kind,
         json_extract(value, '$.nx') AS nx,
         json_extract(value, '$.ny') AS ny,
         json_extract(value, '$.category') AS category,
         json_extract(value, '$.issued_at') AS issued_at,
         json_extract(value, '$.target_at') AS target_at,
         json_extract(value, '$.received_at_us') AS received_us,
         json_extract(value, '$.issued_at_us') AS issued_us,
         json_extract(value, '$.target_at_us') AS target_us,
         json_extract(value, '$.status') AS status,
         json_extract(value, '$.value_is_null') AS value_is_null
  FROM json_each(:rows)
), grouped AS (
  SELECT source, kind, nx, ny, category, issued_at, target_at, COUNT(*) AS n
  FROM rows GROUP BY source, kind, nx, ny, category, issued_at, target_at
)
"""


def analyze_history(rows, expected=None, *, late_after_seconds=None):
    """Return aggregate checks for supplied rows, without selecting/saving winners.

    Duplicate counts concern the history business key, not source hashes or receipt
    attempts. Equal instants with different timezone offsets compare as one key.
    An omitted expected manifest means completeness is unknown, even for zero rows.
    A threshold applies only to receipt minus issuance, never forecast target time.
    """
    if late_after_seconds is not None:
        try:
            valid_threshold = (type(late_after_seconds) in (int, float)
                               and math.isfinite(late_after_seconds) and late_after_seconds >= 0)
        except OverflowError:
            valid_threshold = False
        if not valid_threshold:
            raise HistoryValidationError('invalid_late_after_seconds')
        # SQLite INTEGER bindings stop at signed 64-bit; timing SQL already uses
        # real-valued seconds, so normalize every accepted threshold to that type.
        late_after_seconds = float(late_after_seconds)
    prepared = _prepare(rows)
    expected_rows = None if expected is None else _prepare(expected, expected=True)
    parameters = {'rows': json.dumps(prepared, allow_nan=False), 'threshold': late_after_seconds}
    with closing(sqlite3.connect(':memory:')) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA query_only = ON')
        totals = dict(connection.execute(ROWS_CTE + """
            SELECT (SELECT COUNT(*) FROM rows) AS input_rows,
                   COUNT(*) AS unique_history_keys,
                   COALESCE(SUM(CASE WHEN n > 1 THEN 1 ELSE 0 END), 0) AS duplicate_keys,
                   COALESCE(SUM(n - 1), 0) AS duplicate_rows
            FROM grouped
        """, parameters).fetchone())
        statuses = dict(connection.execute(ROWS_CTE +
            'SELECT status, COUNT(*) FROM rows GROUP BY status ORDER BY status', parameters))
        checks = dict(connection.execute(ROWS_CTE + """
            SELECT COALESCE(SUM(value_is_null), 0) AS null_values,
                   COALESCE(SUM(CASE WHEN status = 'valid' AND value_is_null = 1 THEN 1
                                     WHEN status != 'valid' AND value_is_null = 0 THEN 1 ELSE 0 END), 0)
                        AS inconsistent_status_values,
                   COALESCE(SUM(CASE WHEN received_us < issued_us THEN 1 ELSE 0 END), 0)
                        AS received_before_issue,
                   CASE WHEN :threshold IS NULL THEN NULL ELSE
                     COALESCE(SUM(CASE WHEN (received_us - issued_us) / 1000000.0 > :threshold
                                       THEN 1 ELSE 0 END), 0) END AS late_rows
            FROM rows
        """, parameters).fetchone())
        timings = {}
        for name, expression in (
            ('receipt_minus_issue_seconds', '(received_us - issued_us) / 1000000.0'),
            ('receipt_minus_target_seconds', '(received_us - target_us) / 1000000.0'),
            ('target_minus_issue_seconds', '(target_us - issued_us) / 1000000.0'),
        ):
            # The expressions are fixed program constants, never caller input.
            query = ROWS_CTE + f'SELECT COUNT(*) AS count, MIN({expression}) AS min, AVG({expression}) AS mean, MAX({expression}) AS max FROM rows'
            timings[name] = dict(connection.execute(query, parameters).fetchone())
        completeness = {'status': 'not_assessed', 'scope': 'supplied_manifest_only',
                        'expected_keys': None, 'missing_keys': None, 'unexpected_keys': None}
        if expected_rows is not None:
            parameters['expected'] = json.dumps(expected_rows, allow_nan=False)
            query = ROWS_CTE + """, expected AS (
              SELECT DISTINCT json_extract(value, '$.source') AS source,
                 json_extract(value, '$.kind') AS kind, json_extract(value, '$.nx') AS nx,
                 json_extract(value, '$.ny') AS ny, json_extract(value, '$.category') AS category,
                 json_extract(value, '$.issued_at') AS issued_at, json_extract(value, '$.target_at') AS target_at
              FROM json_each(:expected)
            ), missing AS (
              SELECT * FROM expected EXCEPT
              SELECT source, kind, nx, ny, category, issued_at, target_at FROM grouped
            ), unexpected AS (
              SELECT source, kind, nx, ny, category, issued_at, target_at FROM grouped EXCEPT
              SELECT * FROM expected
            )
            SELECT (SELECT COUNT(*) FROM expected) AS expected_keys,
                   (SELECT COUNT(*) FROM missing) AS missing_keys,
                   (SELECT COUNT(*) FROM unexpected) AS unexpected_keys
            """
            completeness.update(dict(connection.execute(query, parameters).fetchone()))
            completeness['status'] = ('empty_scope' if completeness['expected_keys'] == 0 else
                                      'missing' if completeness['missing_keys'] else 'matched')
    return {
        'schema_version': 1, 'scope': 'provided_history_file',
        'business_key': list(KEY_FIELDS), 'counts': totals,
        'measurement_status_counts': statuses, 'checks': checks,
        'timing': timings, 'late_after_seconds': late_after_seconds,
        'completeness': completeness,
        'limits': ['No evidence of input completeness without a manifest.',
                   'Statistics count input rows, including duplicate receipts.',
                   'Negative receipt-minus-target values are normal for forecasts.',
                   'No operational history storage or database write is performed.'],
    }


def _reject_constant(_value):
    raise ValueError('nonfinite_json_number')


def _unique_object(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError('duplicate_json_field')
        result[name] = value
    return result


def read_jsonl(path):
    """Read strict UTF-8 JSONL and return rows plus SHA-256 of the exact bytes."""
    try:
        data = Path(path).read_bytes()
        lines = data.decode('utf-8-sig').splitlines()
    except (OSError, UnicodeError):
        raise HistoryValidationError('input_unreadable') from None
    rows = []
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line, parse_constant=_reject_constant, object_pairs_hook=_unique_object)
        except (ValueError, RecursionError):
            raise HistoryValidationError(f'line_{number}:invalid_json') from None
        if not isinstance(row, dict):
            raise HistoryValidationError(f'line_{number}:record_must_be_object')
        rows.append(row)
    return rows, hashlib.sha256(data).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, help='정제 행 JSONL 파일')
    parser.add_argument('--expected', help='검사 범위의 업무 키 JSONL. 생략 시 누락 미판정')
    parser.add_argument('--output', help='새 JSON 보고서 경로. 기존 파일 덮어쓰기 금지')
    parser.add_argument('--late-after-seconds', type=float, help='발표→수신 지연 초과 기준. 생략 시 미판정')
    args = parser.parse_args(argv)
    try:
        rows, input_hash = read_jsonl(args.input)
        expected, expected_hash = read_jsonl(args.expected) if args.expected else (None, None)
        report = analyze_history(rows, expected, late_after_seconds=args.late_after_seconds)
        report['input_sha256'] = input_hash
        report['expected_sha256'] = expected_hash
        output = json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2) + '\n'
        if args.output:
            with Path(args.output).open('x', encoding='utf-8') as stream:
                stream.write(output)
        else:
            print(output, end='')
    except HistoryValidationError as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=True), file=sys.stderr)
        return 2
    except OSError:
        print('{"error": "output_unwritable_or_exists"}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
