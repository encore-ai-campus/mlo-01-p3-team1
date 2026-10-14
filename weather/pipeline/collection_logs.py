"""수집 로그의 로컬 기록과 ES 재전송. 원천·인증값은 포함하지 않음."""
import hashlib
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from weather.pipeline.common import encode

FIELDS = ('log_id','request_id','attempt','stage','ok','source','category',
          'requested_at','received_at','http_status','bytes','elapsed_seconds',
          'error_type','events','source_hash','batch_id','grids','normalized_rows',
          'api_received','parsed','kafka_published','request_ids')
def safe_log(record):
    result = {k:record[k] for k in FIELDS if k in record}
    job = record.get('job', {})
    if job:
        result.update(source=job.get('source'), category=job.get('category'))
        params = job.get('params', {})
        result['request_times'] = {k:params[k] for k in ('tmfc','tmef','hf') if k in params}
    result.setdefault('stage', 'collection')
    result.setdefault('log_id', hashlib.sha256(encode(result)).hexdigest())
    result['@timestamp'] = result.get('requested_at') or result.get('received_at')
    return result

def append(path, record):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('ab') as handle:
        handle.write(encode(safe_log(record))+b'\n')
        handle.flush()
        os.fsync(handle.fileno())

def flush(path, base, index):
    """파일 offset은 ES 전체 성공 후 전진. 장애 시 다음 호출에서 동일 ID 재전송."""
    if not base or not index or not Path(path).exists():
        return 0
    from weather.pipeline.es_current import request
    path = Path(path)
    cursor = path.with_suffix('.cursor.json')
    sink = base+'|'+index
    saved = json.loads(cursor.read_text()) if cursor.exists() else {}
    offset = saved.get('offset',0) if saved.get('sink')==sink else 0
    if offset > path.stat().st_size:
        raise ValueError('log_file_truncated')
    entries = []
    with path.open('rb') as handle:
        handle.seek(offset)
        for _ in range(100):
            line = handle.readline()
            if not line: break
            if not line.endswith(b'\n'): break
            entries.append(safe_log(json.loads(line)))
            offset = handle.tell()
    if not entries: return 0
    request(base,'GET','/'+index)
    lines=[]
    for event in entries:
        lines.extend([encode({'index':{'_index':index,'_id':event['log_id']}}),encode(event)])
    result=request(base,'POST','/_bulk',b'\n'.join(lines)+b'\n',raw=True)
    if result.get('errors'): raise RuntimeError('log_bulk_failed')
    temporary=cursor.with_suffix('.tmp')
    temporary.write_text(json.dumps({'sink':sink,'offset':offset}),encoding='utf-8')
    temporary.replace(cursor)
    return len(entries)

def flush_if_configured(path):
    try:
        return flush(path, os.environ.get('WEATHER_LOG_ES_URL',''), os.environ.get('WEATHER_LOG_INDEX',''))
    except Exception as error:
        # 전달 실패를 숨기지 않되, 날씨 수집을 중단하지 않음. URL/예외 본문 출력 없음.
        print(json.dumps({'stage':'log_delivery','ok':False,'error_type':type(error).__name__}),flush=True)
        return 0
