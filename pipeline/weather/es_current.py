"""관리자 ES 발행. 사용자 조회·Spark checkpoint와 독립적으로 실행."""
import json
import os
import base64
import ssl
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler, HTTPSHandler
from pipeline.weather.common import encode
from pipeline.weather.latest_state import newer, trim_rows, merge_rows


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        return None


def request(base, method, path, body=None, raw=False):
    parsed=urlsplit(base)
    if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('invalid_es_url')
    data = body if raw else encode(body) if body is not None else None
    headers={'Content-Type': 'application/x-ndjson' if raw else 'application/json'}
    username=os.environ.get('ES_USERNAME','');password=os.environ.get('ES_PASSWORD','')
    if username or password:
        if not username or not password or parsed.scheme!='https':raise ValueError('es_credentials_require_https')
        headers['Authorization']='Basic '+base64.b64encode((username+':'+password).encode()).decode()
    req = Request(base.rstrip('/') + path, data=data, method=method,
                  headers=headers)
    context=ssl.create_default_context(cafile=os.environ.get('ES_CA_CERT') or None) if parsed.scheme=='https' else None
    handlers=[NoRedirect]
    if context:handlers.append(HTTPSHandler(context=context))
    with build_opener(*handlers).open(req,timeout=15) as response:
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
