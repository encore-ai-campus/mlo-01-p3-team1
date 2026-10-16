"""격자별 최신 회차와 공통 특징. ES의 seq_no/primary_term으로 동시 갱신 보호."""
import os
import re
from datetime import datetime, timezone
from urllib.error import HTTPError
from pipeline.weather.common import digest
from pipeline.weather.es_current import request
from pipeline.weather.latest_state import merge_rows
from pipeline.weather.projection import project_grid
from pipeline.weather.service_view import enrich


def configuration():
    base = os.environ.get('ES_URL', '').strip()
    index = os.environ.get('WEATHER_INDEX', '').strip()
    if not base or not re.fullmatch(r'[a-z0-9][a-z0-9_.-]*', index):
        raise RuntimeError('weather_es_configuration_required')
    return base, index


def grid_id(nx, ny):
    if type(nx) is not int or type(ny) is not int or not (1 <= nx <= 149 and 1 <= ny <= 253):
        raise ValueError('invalid_grid')
    return f'{nx}_{ny}'


def load(base, index, identifier):
    try:
        return request(base, 'GET', f'/{index}/_doc/{identifier}')
    except HTTPError as error:
        if error.code != 404:
            raise
        # Missing index is an infrastructure error; never create it implicitly.
        request(base, 'GET', f'/{index}')
        return None


def write_grid(nx, ny, incoming):
    base, index = configuration()
    identifier = grid_id(nx, ny)
    if any((row['nx'], row['ny']) != (nx, ny) for row in incoming):
        raise ValueError('mixed_weather_grids')
    for _ in range(8):
        previous = load(base, index, identifier)
        source = previous['_source'] if previous else None
        if source and source.get('schema_version') != 1:
            raise ValueError('weather_storage_schema')
        rows = merge_rows(source['rows'] if source else [], incoming)
        rows.sort(key=lambda row: (row['source'], row['issued_at'], row['target_at'], row['category']))
        state_hash = digest(rows)
        if not rows or source and source['state_hash'] == state_hash:
            return False
        document = dict(schema_version=1, revision=source['revision'] + 1 if source else 1,
                        state_hash=state_hash, rows=rows, view=enrich(project_grid(rows)),
                        stored_at=datetime.now(timezone.utc).isoformat())
        condition = (f"if_seq_no={previous['_seq_no']}&if_primary_term={previous['_primary_term']}"
                     if previous else 'op_type=create')
        try:
            response = request(base, 'PUT', f'/{index}/_doc/{identifier}?{condition}', document)
            if response.get('result') not in ('created', 'updated'):
                raise RuntimeError('weather_es_write_unacknowledged')
            shards = response.get('_shards', {})
            if shards.get('failed', 0):
                raise RuntimeError('weather_es_shard_failure')
            return True
        except HTTPError as error:
            if error.code != 409:
                raise
    raise RuntimeError('weather_write_conflict')


def read_grid(nx, ny):
    base, index = configuration()
    document = load(base, index, grid_id(nx, ny))
    if not document:
        raise KeyError('weather_not_found')
    source = document['_source']
    if source.get('schema_version') != 1:
        raise ValueError('weather_storage_schema')
    # Stored features are shared; expiry is always re-evaluated for this query.
    return enrich(source['view'])
