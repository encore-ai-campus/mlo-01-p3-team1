"""격자 한 개를 문서 하나로 저장. MongoDB 쓰기는 Spark Driver에서 실행."""
import os
from datetime import datetime, timezone
from functools import lru_cache
from pymongo import MongoClient, ReadPreference
from pymongo.errors import DuplicateKeyError
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern
from weather.pipeline.common import digest
from weather.pipeline.latest_state import merge_rows
from weather.pipeline.projection import project_grid
from weather.pipeline.service_view import enrich


def setting(name):
    value = os.environ.get(name, '').strip()
    if not value:
        raise RuntimeError(name + '_missing')
    return value


@lru_cache(maxsize=4)
def client(uri, process_id):
    # 프로세스마다 별도 연결 풀. URI/인증 오류 본문을 로그로 출력하지 않음.
    return MongoClient(uri, appname='weather', connect=False,
                       serverSelectionTimeoutMS=5000, connectTimeoutMS=5000,
                       socketTimeoutMS=10000, maxPoolSize=20)


def database(role):
    names = {'read': 'WEATHER_MONGODB_READ_URI',
             'write': 'WEATHER_MONGODB_WRITE_URI',
             'publish': 'WEATHER_MONGODB_PUBLISH_URI'}
    name = setting('WEATHER_MONGODB_DATABASE')
    if name in ('admin', 'local', 'config') or name == os.environ.get('ADS_MONGODB_DATABASE'):
        raise ValueError('weather_database_must_be_separate')
    connection = client(setting(names[role]), os.getpid())
    return connection.get_database(name, read_preference=ReadPreference.PRIMARY,
        read_concern=ReadConcern('majority'),
        write_concern=WriteConcern(w='majority', j=True, wtimeout=10000))


def collection(role):
    db = database(role)
    name = setting('WEATHER_MONGODB_COLLECTION')
    # 컬렉션/validator는 인프라 또는 명시적인 prepare_mongo --apply로 준비.
    found = db.command('listCollections', filter={'name': name},
                       nameOnly=True, authorizedCollections=True)
    if not found['cursor']['firstBatch']:
        raise RuntimeError('weather_collection_not_prepared')
    return db[name]


def grid_id(nx, ny):
    if type(nx) is not int or type(ny) is not int or not (1 <= nx <= 149 and 1 <= ny <= 253):
        raise ValueError('invalid_grid')
    return f'{nx}_{ny}'


def validate_document(document):
    if document.get('schema_version') != 1:
        raise ValueError('weather_storage_schema')
    if type(document.get('revision')) is not int or document['revision'] < 1:
        raise ValueError('weather_storage_revision')


def write_grid(store, nx, ny, incoming):
    """한 격자의 정제 행을 병합해 저장. 변경하면 True, 같은 내용이면 False.

    incoming은 normalize_event의 행 목록. revision 조건으로 동시 덮어쓰기 방지.
    """
    identifier = grid_id(nx, ny)
    if any((r['nx'], r['ny']) != (nx, ny) for r in incoming):
        raise ValueError('mixed_weather_grids')
    # 다른 writer가 먼저 저장하면 다시 읽고 병합. 최대 8회 충돌 재시도.
    for _ in range(8):
        previous = store.find_one({'_id': identifier})
        if previous:
            validate_document(previous)
        previous_rows = previous['rows'] if previous else []
        rows = merge_rows(previous_rows, incoming)
        rows.sort(key=lambda r: (r['source'], r['issued_at'], r['target_at'], r['category']))
        state_hash = digest(rows)
        if previous and previous['state_hash'] == state_hash:
            return False
        if not rows:
            return False
        revision = previous['revision'] + 1 if previous else 1
        weather_view = project_grid(rows)
        service_view = enrich(weather_view)
        document = dict(
            _id=identifier,
            schema_version=1,
            revision=revision,
            state_hash=state_hash,
            rows=rows,
            view=service_view,
            stored_at=datetime.now(timezone.utc).isoformat(),
            admin_pending=True,
        )
        if previous:
            result = store.replace_one({'_id': identifier, 'revision': previous['revision']}, document)
            if not result.acknowledged:
                raise RuntimeError('weather_write_unacknowledged')
            if result.matched_count:
                return True
        else:
            try:
                result = store.insert_one(document)
                if not result.acknowledged:
                    raise RuntimeError('weather_write_unacknowledged')
                return True
            except DuplicateKeyError:
                pass  # 먼저 생성한 writer의 문서를 다시 읽어 병합.
    raise RuntimeError('weather_write_conflict')


def read_grid(nx, ny):
    """예: (58, 125) → observation/forecast 등이 담긴 사용자 조회용 dict."""
    document = collection('read').find_one({'_id': grid_id(nx, ny)}, {'rows': 0})
    if document is None:
        raise KeyError('weather_not_found')
    validate_document(document)
    return document['view']
