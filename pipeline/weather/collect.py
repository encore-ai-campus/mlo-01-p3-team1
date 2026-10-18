"""API 응답을 메모리에서 JSON으로 변환하고 Kafka에 전달."""
import hashlib
import os
from pathlib import Path
import re
import time
from datetime import datetime
from pipeline.weather.common import KST, make_events

ENV_PATH = Path(__file__).with_name('.env')

def configured_key():
    # Service environment wins, including an explicitly empty value.
    if 'KMA_API_KEY' in os.environ:
        return os.environ['KMA_API_KEY'].strip()
    if not ENV_PATH.is_file():
        return ''
    for line in ENV_PATH.read_text(encoding='utf-8-sig').splitlines():
        assignment = line.strip()
        if assignment.startswith('export '):
            assignment = assignment[7:].lstrip()
        name, separator, value = assignment.partition('=')
        if not separator or name.strip() != 'KMA_API_KEY':
            continue
        value = value.strip()
        if not value or value.startswith('#'):
            return ''
        match = re.fullmatch(r'''(?:'([^']*)'|"([^"]*)"|([^\s#'"]+))(?:\s+\#.*)?''', value)
        if not match:
            raise RuntimeError('invalid_KMA_API_KEY_assignment')
        return next(part for part in match.groups() if part is not None).strip()
    return ''

def stream_request(job, key, session, deliver):
    """응답→JSON→Kafka. 원천 바이트/이벤트 파일 저장 없음."""
    status = None
    size = 0
    received = None
    started = time.monotonic()
    record = dict(job=job, requested_at=datetime.now(KST).isoformat(), ok=False,
                  api_received=False, parsed=False, kafka_published=False)
    try:
        with session.get('https://apihub.kma.go.kr' + job['endpoint'],
                         params=dict(job['params'], authKey=key),
                         timeout=(10, 30), stream=True) as response:
            status = response.status_code
            response.raise_for_status()
            buffer = bytearray()
            for chunk in response.iter_content(chunk_size=65536):
                buffer.extend(chunk)
                size += len(chunk)
                if size > 2_000_000:
                    raise ValueError('response_too_large')
        body = bytes(buffer)
        if key.encode() in body:
            raise ValueError('credential_in_response')
        received = datetime.now(KST).isoformat()
        record['api_received'] = True
        events = list(make_events(job, body, received, None, 'stream'))
        record['parsed'] = True
        deliver(events)
        record['kafka_published'] = True
        record.update(ok=True, events=len(events), source_hash=hashlib.sha256(body).hexdigest())
    except Exception as error:
        # 예외 문자열/URL/원천은 기록하지 않음. 실패 요청만 재수집.
        record['error_type'] = type(error).__name__
    record.update(http_status=status, bytes=size, received_at=received,
                  elapsed_seconds=round(time.monotonic()-started, 3))
    return record
