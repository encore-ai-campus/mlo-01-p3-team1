"""Offline re-normalization and comparison of exported weather Kafka events.

This module never connects to Kafka, a database, or Elasticsearch. Input JSONL
may contain events directly or {topic, partition, offset, event} envelopes.
Only new, explicitly named output files are written by the CLI.
"""
import argparse
import hashlib
import inspect
import json
from collections import Counter
from pathlib import Path

from pipeline.weather.common import normalize_event
from pipeline.weather.quality_report import read_jsonl, timestamp
from pipeline.weather import common, weather_normalize, kim_area

KEY_FIELDS = ('source', 'kind', 'nx', 'ny', 'category', 'issued_at', 'target_at')
TIME_FIELDS = ('issued_at', 'target_at', 'received_at')


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(',', ':')).encode('utf-8')


def history_key(row):
    return tuple(row[name] for name in KEY_FIELDS)


def business_value(row):
    """Ignore arrival/retry metadata when comparing business values."""
    return {'measurement': row['measurement'],
            'spatial_basis': row.get('spatial_basis'),
            'source_ix': row.get('source_ix'), 'source_iy': row.get('source_iy')}


def implementation_hash():
    digest = hashlib.sha256()
    for module in (common, weather_normalize, kim_area):
        digest.update(module.__name__.encode('utf-8'))
        digest.update(inspect.getsource(module).encode('utf-8'))
    return digest.hexdigest()


def replay_records(records, grid_keys, *, time_field='target_at', start=None,
                   end=None, grids=None, mapping_version=None, allow_mapping_change=False):
    """Preserve different issuances; coalesce re-received data within one issuance.

    Date range is [start, end). Conflicting values with the same receipt time
    are rejected instead of selecting an arbitrary hash as the newer truth.
    Offset ranges describe supplied records, not proof of complete Kafka export.
    """
    if time_field not in TIME_FIELDS:
        raise ValueError('invalid_time_field')
    lower = timestamp(start) if start is not None else None
    upper = timestamp(end) if end is not None else None
    if lower is not None and upper is not None and lower >= upper:
        raise ValueError('invalid_time_range')
    selected_grids = set(grids) if grids is not None else None
    if selected_grids is not None and (not selected_grids or not selected_grids <= set(grid_keys)):
        raise ValueError('unknown_or_empty_grid_selection')
    rows, offsets, input_versions, rule_versions = {}, {}, set(), set()
    input_count = selected_count = duplicate_rows = replaced_rows = 0
    for item in records:
        input_count += 1
        event = item.get('event', item)
        if not isinstance(event, dict) or event.get('schema_version') != 1:
            raise ValueError('invalid_event_schema')
        times = {name: timestamp(event[name]) for name in TIME_FIELDS}
        if 'event' in item:
            topic, partition, offset = item.get('topic'), item.get('partition'), item.get('offset')
            if (not isinstance(topic, str) or not topic or type(partition) is not int
                    or partition < 0 or type(offset) is not int or offset < 0):
                raise ValueError('invalid_offset_provenance')
            coordinate = (topic, partition, offset)
            digest = hashlib.sha256(canonical(event)).hexdigest()
            if coordinate in offsets and offsets[coordinate] != digest:
                raise ValueError('conflicting_offset_payload')
            offsets[coordinate] = digest
        moment = times[time_field]
        if lower is not None and moment < lower or upper is not None and moment >= upper:
            continue
        version = event.get('mapping_version')
        if not isinstance(version, str) or not version:
            raise ValueError('mapping_version_required')
        if mapping_version is not None and version != mapping_version and not allow_mapping_change:
            raise ValueError('mapping_version_mismatch')
        input_versions.add(version)
        selected_count += 1
        for normalized in normalize_event(event, grid_keys):
            if selected_grids is not None and (normalized['nx'], normalized['ny']) not in selected_grids:
                continue
            # Canonical UTC instants ensure equivalent offsets identify the same fact.
            row = dict(normalized)
            for name in TIME_FIELDS:
                row[name] = times[name].isoformat()
            key = history_key(row)
            row['history_id'] = hashlib.sha256(canonical(key)).hexdigest()
            rule_versions.add(row['rule_version'])
            previous = rows.get(key)
            if previous is not None:
                duplicate_rows += 1
                previous_received = timestamp(previous['received_at'])
                if times['received_at'] == previous_received:
                    if business_value(previous) != business_value(row):
                        raise ValueError('ambiguous_same_time_correction')
                    # Stable metadata choice makes replay independent of input ordering.
                    if canonical(row) > canonical(previous):
                        rows[key] = row
                elif times['received_at'] > previous_received:
                    rows[key] = row
                    replaced_rows += 1
            else:
                rows[key] = row
    output = [rows[key] for key in sorted(rows)]
    ranges = []
    for topic, partition in sorted({(topic, partition) for topic, partition, _ in offsets}):
        values = sorted(offset for t, p, offset in offsets if (t, p) == (topic, partition))
        ranges.append({'topic': topic, 'partition': partition, 'first_offset': values[0],
                       'last_offset': values[-1], 'records': len(values),
                       'offset_gap_count': values[-1] - values[0] + 1 - len(values)})
    report = {'schema_version': 1, 'scope': 'supplied_export_only',
              'export_completeness_verified': False, 'time_field': time_field,
              'start_inclusive': lower.isoformat() if lower else None,
              'end_exclusive': upper.isoformat() if upper else None,
              'input_records': input_count, 'selected_events': selected_count,
              'history_rows': len(output), 'duplicate_rows': duplicate_rows,
              'replaced_rows': replaced_rows, 'offset_ranges': ranges,
              'offset_provenance_records': len(offsets),
              'input_mapping_versions': sorted(input_versions), 'mapping_version': mapping_version,
              'mapping_change_allowed': allow_mapping_change,
              'rule_versions': sorted(rule_versions), 'implementation_sha256': implementation_hash(),
              'measurement_statuses': dict(Counter(row['measurement']['status'] for row in output)),
              'output_sha256': hashlib.sha256(b''.join(canonical(row) + b'\n' for row in output)).hexdigest()}
    return output, report


def compare_rows(before, after):
    def index(values):
        result = {}
        for row in values:
            item = dict(row)
            for field in ('issued_at', 'target_at'):
                item[field] = timestamp(item[field]).isoformat()
            key = history_key(item)
            if key in result:
                raise ValueError('duplicate_history_key')
            result[key] = item
        return result
    left, right = index(before), index(after)
    changes = []
    metadata_only = 0
    for key in sorted(left.keys() | right.keys()):
        if key not in left:
            kind = 'added'
        elif key not in right:
            kind = 'removed'
        elif business_value(left[key]) != business_value(right[key]):
            kind = 'changed'
        else:
            metadata_only += int(left[key] != right[key])
            continue
        # Output only safe, explicit business fields, not arbitrary input metadata.
        changes.append({'key': dict(zip(KEY_FIELDS, key)), 'kind': kind,
                        'before': business_value(left[key]) if key in left else None,
                        'after': business_value(right[key]) if key in right else None})
    return {'schema_version': 1, 'before_rows': len(left), 'after_rows': len(right),
            'business_equal': not changes, 'metadata_only_rows': metadata_only,
            'changes': changes}


def strict_jsonl(path):
    records, metadata = read_jsonl(path)
    if not metadata['complete_read']:
        raise ValueError('incomplete_export')
    return records, metadata


def write_new(path, value, jsonl=False):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        if jsonl:
            for row in value:
                stream.write(canonical(row).decode('utf-8') + '\n')
        else:
            stream.write(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    replay = commands.add_parser('replay')
    replay.add_argument('--input', required=True)
    replay.add_argument('--mapping', required=True)
    replay.add_argument('--output', required=True)
    replay.add_argument('--report', required=True)
    replay.add_argument('--time-field', choices=TIME_FIELDS, default='target_at')
    replay.add_argument('--start')
    replay.add_argument('--end')
    replay.add_argument('--grid', action='append', help='Selected grid nx,ny; repeatable')
    replay.add_argument('--allow-mapping-change', action='store_true')
    compare = commands.add_parser('compare')
    compare.add_argument('--before', required=True)
    compare.add_argument('--after', required=True)
    compare.add_argument('--report', required=True)
    args = parser.parse_args()
    try:
        outputs = [Path(args.report).resolve()]
        inputs = []
        if args.command == 'replay':
            outputs.append(Path(args.output).resolve())
            inputs = [Path(args.input).resolve(), Path(args.mapping).resolve()]
        else:
            inputs = [Path(args.before).resolve(), Path(args.after).resolve()]
        if len(set(outputs)) != len(outputs) or any(path.exists() or path in inputs for path in outputs):
            raise ValueError('output_must_be_new_and_separate')
        if args.command == 'replay':
            events, input_metadata = strict_jsonl(args.input)
            mapping_bytes = Path(args.mapping).read_bytes()
            mapping = json.loads(mapping_bytes)
            grid_keys = {(g['nx'], g['ny']): g for g in mapping['grids'] + mapping.get('admin_grids', [])}
            grids = [tuple(int(part) for part in value.split(',')) for value in args.grid] if args.grid else None
            if grids and any(len(grid) != 2 for grid in grids):
                raise ValueError('invalid_grid')
            rows, report = replay_records(events, grid_keys, time_field=args.time_field,
                start=args.start, end=args.end, grids=grids, mapping_version=mapping['version'],
                allow_mapping_change=args.allow_mapping_change)
            report['input_sha256'] = input_metadata['read_bytes_sha256']
            report['mapping_sha256'] = hashlib.sha256(mapping_bytes).hexdigest()
            write_new(args.output, rows, jsonl=True)
            write_new(args.report, report)
        else:
            before, before_meta = strict_jsonl(args.before)
            after, after_meta = strict_jsonl(args.after)
            report = compare_rows(before, after)
            report['input_sha256'] = {'before': before_meta['read_bytes_sha256'],
                                      'after': after_meta['read_bytes_sha256']}
            write_new(args.report, report)
        print(json.dumps({'ok': True, 'command': args.command}))
        return 0
    except (OSError, ValueError, TypeError, KeyError):
        print(json.dumps({'ok': False, 'error': 'replay_input_or_output_invalid'}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
