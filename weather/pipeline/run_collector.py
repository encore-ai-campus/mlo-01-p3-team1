"""주기 수집 실행. 한 서버에서 한 프로세스만 실행하며 상태·로그 유지."""
import argparse
import hashlib
import json
import os
if os.name == "nt":
    import msvcrt
else:
    import fcntl
import time
from datetime import datetime, timedelta
from pathlib import Path

from weather.pipeline.collect import configured_key, stream_request
import requests
from kafka import KafkaProducer
from weather.pipeline.common import KST, UTC
from weather.pipeline.make_jobs import make_jobs
from weather.pipeline.publish import send_events
from weather.pipeline.collection_logs import append as append_log, flush_if_configured

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ('odam', 'vsrt', 'shrt', 'KIMG')


def save_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    # Windows에서 대시보드가 파일을 읽는 순간 교체가 잠시 거부될 수 있음.
    for attempt in range(20):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.05)


def job_id(job):
    request = {name: job.get(name) for name in ('source', 'endpoint', 'params', 'response_format')}
    encoded = json.dumps(request, sort_keys=True).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def scheduled_jobs(now, grids):
    jobs = make_jobs(now, grids, len(grids), observation_delay_minutes=0,
                     forecast_delay_minutes=15)
    targets = {j['params']['tmef'] for j in jobs if j['source'] == 'vsrt'}
    targets.add(now.astimezone(KST).strftime('%Y%m%d%H'))
    selected = []
    for job in jobs:
        if job['source'] == 'KIMG':
            issued = datetime.strptime(job['params']['tmfc'], '%Y%m%d%H').replace(tzinfo=UTC)
            target = (issued + timedelta(hours=job['params']['hf'])).astimezone(KST)
            if target.strftime('%Y%m%d%H') not in targets:
                continue
        selected.append(job)
    return selected




def status(directory, phase, **details):
    save_json(directory / 'status.json', dict(phase=phase, pid=os.getpid(),
              updated_at=datetime.now(KST).isoformat(), **details))




def register_jobs(state, jobs, now):
    for job in jobs:
        identity = job_id(job)
        if identity not in state['completed'] and identity not in state['failed']:
            state['queue'].setdefault(identity, dict(job=job, first_seen_at=now.isoformat(), attempts=0))


def choose_job(state, latest_jobs, now, config):
    latest_ids = {job_id(j) for j in latest_jobs}
    candidates = []
    for identity, entry in list(state['queue'].items()):
        age = now - datetime.fromisoformat(entry['first_seen_at'])
        if age >= timedelta(hours=config['backfill_hours']) or entry['attempts'] >= config['max_attempts']:
            state['failed'][identity] = dict(job=entry['job'], reason='retry_limit', at=now.isoformat())
            del state['queue'][identity]
            continue
        if entry.get('retry_at') and datetime.fromisoformat(entry['retry_at']) > now:
            continue
        candidates.append((identity not in latest_ids, SOURCES.index(entry['job']['source']),
                           entry['first_seen_at'], identity, entry))
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: item[:4])[0][3:]


def finish_job(state, identity, record, now):
    entry = state['queue'][identity]
    entry['attempts'] += 1
    if record['ok']:
        state['completed'][identity] = now.isoformat()
        state['last_published_at'] = now.isoformat()
        del state['queue'][identity]
    else:
        seconds = 60 if entry['job']['source'] == 'odam' else 300
        entry['retry_at'] = (now + timedelta(seconds=seconds)).isoformat()


def run(directory, bootstrap, topic):
    key = configured_key()
    if not key:
        raise RuntimeError('KMA_API_KEY_missing')
    mapping = json.loads((ROOT/'pipeline/mapping.json').read_text(encoding='utf-8'))
    config = json.loads((ROOT/'pipeline/runtime_config.json').read_text(encoding='utf-8'))
    state_path = directory/'state.json'
    state = json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {
        'completed': {}, 'failed': {}, 'queue': {}, 'last_published_at': None,
        'last_planned_at': None, 'usage': {}}
    if 'queue' not in state:
        raise RuntimeError('use_separate_stream_runtime_directory')
    # 접속 실패 시에도 요청 계획은 남음. 원천 데이터는 메모리에서만 처리.
    with requests.Session() as session:
        producer = KafkaProducer(bootstrap_servers=bootstrap, acks='all', retries=3,
                                 compression_type='gzip', max_request_size=1000000)
        try:
            while not (directory/'stop.flag').exists():
                now = datetime.now(KST)
                flush_if_configured(directory/'requests.jsonl')
                latest = scheduled_jobs(now, mapping['grids'])
                for job in latest:
                    job['mapping_version'] = mapping['version']
                previous = state.get('last_planned_at')
                if previous:
                    cursor = max(datetime.fromisoformat(previous), now-timedelta(hours=config['backfill_hours']))
                    cursor = cursor.replace(minute=cursor.minute//10*10, second=0, microsecond=0)
                    while cursor < now:
                        missed = scheduled_jobs(cursor, mapping['grids'])
                        for job in missed:
                            job['mapping_version'] = mapping['version']
                        register_jobs(state, missed, cursor)
                        cursor += timedelta(minutes=10)
                register_jobs(state, latest, now)
                state['last_planned_at'] = now.isoformat()
                selected = choose_job(state, latest, now, config)
                day = now.date().isoformat()
                usage = state['usage'].setdefault(day, dict(requests=0, bytes=0))
                save_json(state_path, state)
                if usage['requests'] >= config['daily_request_budget'] or usage['bytes'] >= config['daily_byte_budget']:
                    status(directory, 'budget_wait', reason='daily_budget')
                    time.sleep(30)
                    continue
                if selected is None:
                    status(directory, 'waiting', last_published_at=state['last_published_at'],
                           completed_requests=len(state['completed']), queued_requests=len(state['queue']),
                           failed_requests=len(state['failed']))
                    time.sleep(5)
                    continue
                identity, entry = selected
                job = dict(entry['job'], request_id=identity)
                attempt_number = entry['attempts']+1
                status(directory, 'collecting', source=job['source'],
                       queued_requests=len(state['queue']), last_published_at=state['last_published_at'])
                # 호출 전에 사용량 기록: 재시작으로 요청 예산이 리셋되지 않음.
                usage['requests'] += 1
                save_json(state_path, state)
                record = stream_request(job, key, session, lambda events: send_events(producer, events, topic))
                record.update(request_id=identity, attempt=attempt_number, stage='collection')
                append_log(directory/'requests.jsonl', record)
                flush_if_configured(directory/'requests.jsonl')
                usage['bytes'] += record['bytes']
                finish_job(state, identity, record, datetime.now(KST))
                save_json(state_path, state)
                if record['http_status'] in (401, 403, 429):
                    status(directory, 'stopped', reason='auth_or_quota_stop')
                    return
                time.sleep(1)
        finally:
            producer.close(timeout=10)
    status(directory, 'stopped', reason='stop_flag')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', default=os.environ.get('WEATHER_STATE_DIR') or str(ROOT/'runtime/collector'))
    parser.add_argument('--bootstrap', default=os.environ.get('KAFKA_BOOTSTRAP'))
    parser.add_argument('--topic', default=os.environ.get('KAFKA_TOPIC','weather.v1'))
    args = parser.parse_args()
    if not args.bootstrap:
        parser.error("KAFKA_BOOTSTRAP or --bootstrap is required")
    directory = Path(args.directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / 'collector.lock').open('a+b') as lock:
        lock.seek(0)
        try:
            if os.name == 'nt':
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise SystemExit('collector_already_running')
        if os.fstat(lock.fileno()).st_size == 0:
            lock.write(b'0')
            lock.flush()
        (directory / 'collector.pid').write_text(str(os.getpid()), encoding='utf-8')
        run(directory, args.bootstrap, args.topic)


if __name__ == '__main__':
    main()
