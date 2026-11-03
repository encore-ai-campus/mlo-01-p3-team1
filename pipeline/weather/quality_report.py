"""Read-only collection quality report; never treats a partial log as a full audit.

Expected JSONL rows: {"request_id": "...", "due_at": "...+09:00"}.
Use an independently prepared request plan, not IDs copied from successful logs.
Existing collection logs are accepted without copying request URLs or credentials.
"""
import argparse
import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('timestamp_required')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.utcoffset() is None:
        raise ValueError('timezone_required')
    return parsed.astimezone(timezone.utc)


def read_jsonl(path, max_records=100000):
    """Read a bounded snapshot, returning safe diagnostics instead of source lines."""
    records, issues = [], []
    digest = hashlib.sha256()
    path = Path(path)
    with path.open('rb') as stream:
        before = path.stat()
        for number, line in enumerate(stream, 1):
            if number > max_records:
                issues.append({'code': 'record_limit', 'line': number})
                break
            digest.update(line)
            if not line.endswith(b'\n'):
                issues.append({'code': 'unterminated_line', 'line': number})
                continue
            try:
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise ValueError('object_required')
                records.append(record)
            except (ValueError, UnicodeError):
                issues.append({'code': 'invalid_json_object', 'line': number})
        after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        issues.append({'code': 'file_changed_during_read'})
    return records, {'complete_read': not issues, 'issues': issues,
                     'read_bytes_sha256': digest.hexdigest(), 'records': len(records)}


def build_report(expected_requests, attempts, *, now, grace_seconds=1200,
                 input_complete=False):
    """Count attempts separately from unique requests; time window is the supplied plan.

    input_complete is the caller's explicit coverage assertion, not inferred from
    the presence of successful records. A missing plan cannot establish coverage.
    """
    now = timestamp(now) if isinstance(now, str) else now
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError('timezone_required')
    if isinstance(grace_seconds, bool) or not math.isfinite(grace_seconds) or grace_seconds < 0:
        raise ValueError('invalid_grace_seconds')
    expected = {}
    for item in expected_requests:
        identifier = item.get('request_id')
        if not isinstance(identifier, str) or not identifier.strip():
            raise ValueError('request_id_required')
        due = timestamp(item.get('due_at'))
        if identifier in expected:
            raise ValueError('duplicate_expected_request')
        expected[identifier] = due
    grouped = {identifier: [] for identifier in expected}
    issues, seen = [], {}
    duplicate_logs = unrelated = valid_attempts = successful_attempts = 0
    for number, item in enumerate(attempts, 1):
        if item.get('stage', 'collection') != 'collection':
            continue
        identifier = item.get('request_id')
        if identifier not in expected:
            unrelated += 1
            continue
        try:
            requested = timestamp(item.get('requested_at'))
            elapsed = item.get('elapsed_seconds', 0)
            if (type(item.get('ok')) is not bool or type(elapsed) not in (float, int)
                    or not math.isfinite(elapsed) or elapsed < 0):
                raise ValueError('invalid_attempt')
            completed = requested + timedelta(seconds=elapsed)
            if requested > now or completed > now:
                raise ValueError('future_attempt')
            if item.get('received_at') is not None:
                timestamp(item['received_at'])
            identity = item.get('log_id') or (identifier, item.get('attempt'), requested.isoformat())
            if not isinstance(identity, (str, tuple)):
                raise ValueError('invalid_log_id')
            # Only fields needed for this report contribute to duplicate detection.
            signature = (identifier, requested, completed, item['ok'])
            if identity in seen:
                if seen[identity] != signature:
                    issues.append({'code': 'conflicting_log_identity', 'record': number})
                else:
                    duplicate_logs += 1
                continue
            seen[identity] = signature
            grouped[identifier].append((requested, completed, item['ok']))
            valid_attempts += 1
            successful_attempts += int(item['ok'])
        except (ValueError, TypeError, OverflowError):
            issues.append({'code': 'invalid_attempt', 'record': number})
    counts = {name: 0 for name in ('completed', 'failed', 'missing', 'not_due', 'waiting')}
    late = 0
    requests = []
    for identifier, due in sorted(expected.items()):
        records = grouped[identifier]
        successes = [end for _, end, ok in records if ok]
        deadline = due + timedelta(seconds=grace_seconds)
        completion = min(successes) if successes else None
        if completion is not None:
            state = 'completed'
        elif now < due:
            state = 'not_due'
        elif now < deadline:
            state = 'waiting'
        elif records:
            state = 'failed'
        else:
            state = 'missing'
        is_late = completion is not None and completion > deadline
        late += int(is_late)
        counts[state] += 1
        requests.append({'request_id': identifier, 'due_at': due.isoformat(),
                         'status': state, 'attempts': len(records), 'late': is_late,
                         'completed_at': completion.isoformat() if completion else None})
    due_count = sum(due <= now for due in expected.values())
    due_completed = sum(r['status'] == 'completed' and expected[r['request_id']] <= now
                        for r in requests)
    complete = bool(input_complete) and not issues
    state = ('incomplete' if not complete else 'no_expected_requests' if not expected
             else 'attention' if counts['missing'] or counts['failed'] or late else 'ok')
    return {'schema_version': 1, 'scope': 'supplied_expected_requests',
            'evaluated_at': now.isoformat(), 'coverage_asserted': bool(input_complete),
            'input_complete': complete, 'status': state, 'grace_seconds': grace_seconds,
            'expected_requests': len(expected), 'due_requests': due_count, **counts,
            'late_completed': late, 'unique_attempts': valid_attempts,
            'successful_attempts': successful_attempts, 'duplicate_log_records': duplicate_logs,
            'unrelated_log_records': unrelated,
            'attempt_success_rate': successful_attempts / valid_attempts if valid_attempts else None,
            'due_request_completion_rate': due_completed / due_count if due_count else None,
            'requests': requests, 'issues': issues}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected', required=True)
    parser.add_argument('--logs', required=True)
    parser.add_argument('--now', required=True, help='Timezone-aware evaluation timestamp')
    parser.add_argument('--grace-seconds', type=float, default=1200)
    parser.add_argument('--complete-window', action='store_true',
                        help='Assert supplied plan and logs cover the complete intended window')
    parser.add_argument('--output', help='New report file; existing files are never overwritten')
    args = parser.parse_args()
    try:
        expected, expected_read = read_jsonl(args.expected)
        logs, logs_read = read_jsonl(args.logs)
        report = build_report(expected, logs, now=args.now, grace_seconds=args.grace_seconds,
                              input_complete=args.complete_window and expected_read['complete_read']
                              and logs_read['complete_read'])
        report['inputs'] = {'expected': expected_read, 'logs': logs_read}
        payload = json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2)
        if args.output:
            with Path(args.output).open('x', encoding='utf-8') as stream:
                stream.write(payload + '\n')
        else:
            print(payload)
        return 0 if report['status'] in ('ok', 'no_expected_requests') else 2
    except (OSError, ValueError, TypeError):
        print(json.dumps({'ok': False, 'error': 'quality_report_input_or_output_invalid'}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
