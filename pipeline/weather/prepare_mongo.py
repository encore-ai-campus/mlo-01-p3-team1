"""날씨 전용 컬렉션 준비. 검토 후 python -m pipeline.weather.prepare_mongo --apply."""
import argparse
import json
from pipeline.weather.mongo_current import database, setting

VALIDATOR = {'$jsonSchema': {
    'bsonType': 'object',
    'required': ['_id', 'schema_version', 'revision', 'state_hash', 'rows', 'view', 'stored_at', 'admin_pending'],
    'properties': {
        '_id': {'bsonType': 'string'},
        'schema_version': {'enum': [1]},
        'revision': {'bsonType': ['int', 'long'], 'minimum': 1},
        'state_hash': {'bsonType': 'string'},
        'rows': {'bsonType': 'array'},
        'view': {'bsonType': 'object'},
        'stored_at': {'bsonType': 'string'},
        'admin_pending': {'bsonType': 'bool'}
    }
}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if not args.apply:
        print(json.dumps(VALIDATOR, ensure_ascii=False, indent=2))
        return
    db = database('write')
    name = setting('WEATHER_MONGODB_COLLECTION')
    existing = list(db.list_collections(filter={'name': name}))
    if existing:
        if existing[0].get('options', {}).get('validator') != VALIDATOR:
            raise RuntimeError('existing_validator_differs_review_required')
    else:
        db.create_collection(name, validator=VALIDATOR)
    # _id의 고유 인덱스로 nx_ny 조회·중복 차단. 기존 컬렉션 삭제/변경 없음.
    print('weather_collection_ready')


if __name__ == '__main__':
    main()
