"""API 응답 → 공통 이벤트 → 격자별 정제 행. DB 접속 없이 변환만 수행."""
import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from pipeline.weather.weather_normalize import normalize_value
from pipeline.weather.kim_area import parse_area, select_grids

KST = timezone(timedelta(hours=9))
UTC = timezone.utc
OBS = ['T1H', 'REH', 'RN1', 'WSD', 'UUU', 'VVV', 'VEC', 'PTY']
FORECAST = OBS + ['SKY', 'LGT', 'POP']


def encode(value):
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, separators=(',', ':')
    ).encode('utf-8')


def digest(value):
    return hashlib.sha256(encode(value)).hexdigest()


def stamp(value, zone):
    """API 시각 문자열을 한국 시각으로 변환. 예: 202610151200 → ISO 문자열."""
    time_format = '%Y%m%d%H%M' if len(value) == 12 else '%Y%m%d%H'
    source_time = datetime.strptime(value, time_format).replace(tzinfo=zone)
    return source_time.astimezone(KST).isoformat()


def parse_grid_response(job, body):
    params = job['params']
    text = body.decode('euc-kr').replace('\r', '').replace('\n', '')
    values = [value.strip() for value in text.split(',') if value.strip()]
    if len(values) != 37697:
        raise ValueError('grid_shape')
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError('grid_nonfinite')

    issued = stamp(params['tmfc'], KST)
    target = stamp(params.get('tmef', params['tmfc']), KST)
    # 온도 전 격자 0 응답은 잘못된 대상 시각 시험에서 관찰됨. 임의 보정 없이 거부.
    if job['category'] == 'T1H' and all(float(value) == 0 for value in values):
        raise ValueError('all_zero_temperature')

    readings = []
    for position, value in enumerate(values):
        nx = position % 149 + 1
        ny = position // 149 + 1
        readings.append(dict(nx=nx, ny=ny, raw=value))
    return [(issued, target, readings)]


def parse_kim_area_response(job, body):
    params = job['params']
    if job['category'] != 'TCDC' or params.get('vars') != 'tcld':
        raise ValueError('kim_metadata')
    issued = stamp(params['tmfc'], UTC)
    forecast_hours = int(params['hf'])
    if forecast_hours < 0 or forecast_hours > 135:
        raise ValueError('kim_target_range')
    target = (datetime.fromisoformat(issued) + timedelta(hours=forecast_hours)).isoformat()
    return [(issued, target, parse_area(body))]


def parse_kim_point_response(job, body):
    """기존 KIM 지점 응답도 같은 (발표 시각, 대상 시각, 값 목록)으로 변환."""
    params = job['params']
    lines = [line for line in body.decode('utf-8').splitlines() if line.startswith('|')]
    if len(lines) != 2:
        raise ValueError('kim_table')
    header = [value.strip() for value in lines[0].split('|')[1:-1]]
    cells = [value.strip() for value in lines[1].split('|')[1:-1]]
    if len(header) != len(cells) or cells[1] != 'TCDC' or cells[0] != params['tm'][:10]:
        raise ValueError('kim_metadata')
    if abs(float(cells[2]) - params['lon']) > 0.0001 or abs(float(cells[3]) - params['lat']) > 0.0001:
        raise ValueError('kim_location')
    if not header[4:]:
        raise ValueError('kim_no_targets')

    result = []
    for time_text, raw in zip(header[4:], cells[4:]):
        if not math.isfinite(float(raw)):
            raise ValueError('kim_nonfinite')
        target = stamp(time_text, UTC)
        if not stamp(params['tmef1'], UTC) <= target <= stamp(params['tmef2'], UTC):
            raise ValueError('kim_target_range')
        reading = dict(nx=job['nx'], ny=job['ny'], raw=raw)
        result.append((stamp(cells[0], UTC), target, [reading]))
    return result


def parse_response(job, body):
    """요청 정보와 응답 bytes → [(issued_at, target_at, readings), ...].

    일반 격자 reading 예: {'nx': 58, 'ny': 125, 'raw': '21.8'}.
    KIM 영역 응답은 모델 좌표를 유지하고 normalize_event에서 연결.
    """
    if job['source'] != 'KIMG':
        return parse_grid_response(job, body)
    if job.get('response_format') == 'kim_area_csv':
        return parse_kim_area_response(job, body)
    return parse_kim_point_response(job, body)


def make_events(job, body, received_at, raw_path, run_id):
    """응답 bytes → Kafka 이벤트를 차례로 반환. readings에 원래 값과 좌표 포함.

    이벤트의 source/category/issued_at/target_at은 readings 전체에 공통.
    일반 격자는 2,048개씩 나누며, 스트림 수집의 raw_path는 None.
    """
    source_hash = hashlib.sha256(body).hexdigest()
    for issued, target, readings in parse_response(job, body):
        is_kim_area = job.get('response_format') == 'kim_area_csv'
        chunk_size = len(readings) if is_kim_area else 2048
        for start in range(0, len(readings), chunk_size):
            event = dict(
                schema_version=1,
                source=job['source'],
                kind='observation' if job['source'] == 'odam' else 'forecast',
                category=job['category'],
                issued_at=issued,
                target_at=target,
                received_at=received_at,
                source_hash=source_hash,
                raw_path=raw_path,
                run_id=run_id,
                part=start // chunk_size,
                readings=readings[start:start + chunk_size],
                mapping_version=job.get('mapping_version', '2026-07-01'),
            )
            if job.get('request_id'):
                event['request_id'] = job['request_id']
            if is_kim_area:
                event.update(source_format='kim_area_csv', spatial_basis='nearest_kim_grid_v1')
            elif job['source'] == 'KIMG':
                event.update(
                    query_lat=job['params']['lat'],
                    query_lon=job['params']['lon'],
                    spatial_basis=job.get('point_policy', 'selected_region_point_sample'),
                )
            else:
                event['spatial_basis'] = 'dfs_5km'

            identity = [job['source'], job['category'], issued, target, source_hash,
                        event['part'], job.get('nx'), job.get('ny')]
            event['event_id'] = digest(identity)
            if is_kim_area:
                event['event_id'] = digest([
                    event['event_id'], event['spatial_basis'], event['mapping_version']
                ])
            if len(encode(event)) > 900000:
                raise ValueError('message_too_large')
            yield event


def normalize_event(event, grid_keys):
    """공통 이벤트 + 대상 격자 매핑 → 격자·항목별 정제 행을 차례로 반환.

    행 예: nx=58, ny=125, category='T1H',
    measurement={'raw': '21.8', 'value': 21.8, 'unit': 'degC', 'status': 'valid'}.
    """
    if event['schema_version'] != 1:
        raise ValueError('schema_version')
    is_kim_area = event.get('source_format') == 'kim_area_csv'
    if is_kim_area and not isinstance(grid_keys, dict):
        raise ValueError('kim_mapping_required')
    if is_kim_area:
        readings = select_grids(event['readings'], grid_keys)
    else:
        readings = event['readings']

    metadata_fields = (
        'source', 'kind', 'category', 'issued_at', 'target_at', 'received_at',
        'source_hash', 'raw_path', 'run_id', 'mapping_version', 'spatial_basis',
    )
    for reading in readings:
        nx, ny = reading['nx'], reading['ny']
        if (nx, ny) not in grid_keys:
            continue
        row = {name: event[name] for name in metadata_fields}
        if event.get('request_id'):
            row['request_id'] = event['request_id']
        row.update(
            nx=nx,
            ny=ny,
            rule_version='normalize_v3' if event['category'] == 'TCDC' else 'normalize_v2',
            data_mode=event.get('data_mode', 'live'),
        )
        row['measurement'] = normalize_value(
            event['category'], reading['raw'], event['source'], event['kind'],
            sno_encoding='amount_cm' if event['category'] == 'SNO' else None,
        )
        identity = [event['source'], event['kind'], event['issued_at'], event['target_at'],
                    nx, ny, event['category'], event['source_hash'], row['rule_version']]
        if event['category'] == 'TCDC':
            identity += [event['spatial_basis'], event['mapping_version']]
        row['_id'] = digest(identity)
        row['slot_id'] = digest([
            event['source'], event['kind'], event['target_at'], nx, ny, event['category']
        ])
        if is_kim_area:
            spatial_fields = ('query_lat', 'query_lon', 'source_ix', 'source_iy',
                              'source_lat', 'source_lon', 'spatial_distance_km')
            row.update({name: reading[name] for name in spatial_fields})
            row['source_format'] = 'kim_area_csv'
        elif event['source'] == 'KIMG':
            row.update(query_lat=event['query_lat'], query_lon=event['query_lon'])
        yield row
