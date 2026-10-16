"""로컬 실행용 실제 기상청 전국 격자 수집기. HTTP 조회와 분리해 실행합니다."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import time

from .collect import configured_key
from .common import KST, parse_grid_response

DEFAULT_PATH = Path(__file__).resolve().parents[2] / '.local/weather-live/latest.json'


def identity(job):
    return ':'.join((job['source'], job['category'], job['params']['tmfc'],
                     job['params'].get('tmef', '')))


def plan(now):
    now = now.astimezone(KST)
    observed = now - timedelta(minutes=10)
    observed = observed.replace(minute=observed.minute // 10 * 10, second=0, microsecond=0)
    safe = now - timedelta(minutes=15)
    issued = safe.replace(minute=30, second=0, microsecond=0)
    if issued > safe:
        issued -= timedelta(hours=1)
    jobs = []

    def add(source, category, base, target=None):
        params = {'tmfc': base.strftime('%Y%m%d%H%M'), 'vars': category}
        if target:
            params['tmef'] = target.strftime('%Y%m%d%H')
        job = {'source': source, 'category': category, 'params': params}
        if identity(job) not in {identity(item) for item in jobs}:
            jobs.append(job)

    for category in ('PTY', 'T1H'):
        add('odam', category, observed)
    for hour in range(1, 7):
        target = issued.replace(minute=0) + timedelta(hours=hour)
        for category in ('PTY', 'SKY', 'T1H'):
            add('vsrt', category, issued, target)
    # 현재 정시 SKY는 다음 시간 예보로 대체하지 않습니다.
    current = now.replace(minute=0, second=0, microsecond=0)
    add('vsrt', 'SKY', current - timedelta(minutes=30), current)
    return jobs


def fetch(job, key):
    import requests
    record = {'job': identity(job), 'ok': False}
    try:
        response = requests.get(
            'https://apihub.kma.go.kr/api/typ01/cgi-bin/url/nph-dfs_' + job['source'] + '_grd',
            params={**job['params'], 'authKey': key}, timeout=(8, 20))
        record['http_status'] = response.status_code
        if response.status_code != 200:
            return record
        body = response.content
        if len(body) > 2_000_000 or key.encode() in body:
            raise ValueError('invalid_response')
        issued, target, readings = parse_grid_response(job, body)[0]
        slot = {'source': job['source'], 'category': job['category'],
                'issued_at': issued, 'target_at': target,
                'received_at': datetime.now(KST).isoformat(),
                'source_hash': hashlib.sha256(body).hexdigest(),
                'values': [reading['raw'] for reading in readings]}
        record.update(ok=True, slot=slot)
    except Exception as error:
        # 인증 URL/키/원문/예외 문자열은 출력하거나 저장하지 않습니다.
        record['error_type'] = type(error).__name__
    return record


def read(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if data.get('schema_version') != 1 or not isinstance(data.get('slots'), dict):
        raise ValueError('invalid_live_weather_cache')
    return data


def refresh(path, now=None):
    now = now or datetime.now(KST)
    path = Path(path)
    key = configured_key()
    if not key:
        raise RuntimeError('KMA_API_KEY_missing')
    data = read(path) if path.is_file() else {'schema_version': 1, 'slots': {}}
    slots = data['slots']
    pending = [job for job in plan(now) if identity(job) not in slots]
    errors = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for result in pool.map(lambda job: fetch(job, key), pending):
            if result['ok']:
                slots[result['job']] = result['slot']
            else:
                errors.append(result)
    # 통신 실패 시 유효한 이전 회차만 재사용하며, 새 회차의 NULL은 그대로 보존합니다.
    cutoff = now - timedelta(hours=2)
    data['slots'] = {key: slot for key, slot in slots.items()
                     if datetime.fromisoformat(slot['issued_at']) >= cutoff}
    received = [slot['received_at'] for slot in data['slots'].values()]
    data.update(updated_at=max(received) if received else None,
                last_checked_at=datetime.now(KST).isoformat(), errors=errors,
                source='KMA_API_HUB', is_test=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    os.replace(temporary, path)
    return {'ok': not errors, 'fetched': len(pending) - len(errors),
            'failed': len(errors), 'cached_slots': len(data['slots']),
            'updated_at': data['updated_at'],
            'rate_limited': any(error.get('http_status') in (401, 403, 429) for error in errors)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--path', default=os.environ.get('KMA_LOCAL_CACHE_PATH') or str(DEFAULT_PATH))
    args = parser.parse_args()
    while True:
        result = {}
        try:
            result = refresh(args.path)
            print(json.dumps(result, ensure_ascii=False), flush=True)
        except Exception as error:
            print(json.dumps({'ok': False, 'error_type': type(error).__name__}), flush=True)
            if args.once:
                raise SystemExit(1) from None
        if args.once:
            return
        time.sleep(600 if result.get('rate_limited') else 60)


if __name__ == '__main__':
    main()
