"""관리자 ES 발행. 사용자 조회·Spark checkpoint와 독립적으로 실행."""
import json
from urllib.request import Request, urlopen
from weather.pipeline.common import encode
from weather.pipeline.latest_state import newer, trim_rows, merge_rows


def request(base, method, path, body=None, raw=False):
    data = body if raw else encode(body) if body is not None else None
    req = Request(base.rstrip('/') + path, data=data, method=method,
                  headers={'Content-Type': 'application/x-ndjson' if raw else 'application/json'})
    with urlopen(req, timeout=15) as response:
        return json.load(response)


def ensure_index(base, index):
    request(base, 'GET', '/' + index)


def publish_pending(store, base, index, limit=50):
    """성공한 버전만 완료 처리. 실패/응답 유실은 같은 ID·버전으로 재전송."""
    ensure_index(base, index)
    documents = list(store.find({'admin_pending': True}).sort('_id', 1).limit(limit))
    if not documents:
        return 0
    commands = []
    for document in documents:
        commands.extend([encode({'index': {'_index': index, '_id': document['_id'],
                           'version': document['revision'], 'version_type': 'external_gte'}}),
                         encode(document['view'])])
    result = request(base, 'POST', '/_bulk', b'\n'.join(commands) + b'\n', raw=True)
    items = result.get('items', [])
    if len(items) != len(documents):
        raise RuntimeError('admin_bulk_response_invalid')
    failures = 0
    for document, item in zip(documents, items):
        status = item.get('index', {}).get('status', 0)
        if 200 <= status < 300:
            # 발행 중 다음 회차가 도착하면 새 회차의 pending은 해제하지 않음.
            store.update_one({'_id': document['_id'], 'revision': document['revision']},
                             {'$set': {'admin_pending': False}})
        else:
            failures += 1
    if failures:
        raise RuntimeError('admin_bulk_partial_failure')
    return len(documents)
