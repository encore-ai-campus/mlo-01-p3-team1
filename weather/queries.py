"""공통 API에서 호출할 지역 검색·최신 날씨 조회. 화면·HTTP 서버 없음."""
import json
import os
from datetime import datetime
from urllib.request import urlopen
from weather.pipeline.common import KST
from weather.pipeline.mapping_postgres import load_regions, connection
from weather import road_lookup

def includes_in_order(letters, text):
    position = 0
    for letter in text.casefold():
        if letter == letters[position]:
            position += 1
            if position == len(letters):
                return True
    return False

def search_regions(query):
    REGIONS=load_regions()["entries"]
    # 글자 순서를 유지하고 중간 글자는 생략 가능. 구로동 → 구로제1동.
    letters = [letter for letter in query.casefold() if letter.isalnum()]
    if not letters:
        return []
    words = query.casefold().split()
    provinces = {r['address'].split()[0] for r in REGIONS}
    # 서울처럼 시·도 앞부분을 입력하면 해당 시·도 안에서만 검색.
    selected_provinces = {name for name in provinces
                          if len(words[0]) >= 2 and name.casefold().startswith(words[0])}
    matches = []
    for region in REGIONS:
        if selected_provinces and region['address'].split()[0] not in selected_provinces:
            continue
        if includes_in_order(letters, region['address']):
            matches.append(region)
    # 행정 계층을 가장 먼저 적용: 읍·면·동 → 리.
    def priority(region):
        name = region['name'].casefold()
        return (region.get('level',5 if region['kind']=='리' else 4),
                name not in words,
                not includes_in_order(letters, name),
                region['address'])
    return sorted(matches, key=priority)

def read_weather(region):
    ES_URL=os.environ['ES_URL'].rstrip('/')
    INDEX=os.environ.get('WEATHER_INDEX','weather-current-v1')
    if not (isinstance(region.get('nx'),int) and isinstance(region.get('ny'),int)):
        raise ValueError('invalid_grid')
    url = f"{ES_URL}/{INDEX}/_doc/{region['nx']}_{region['ny']}"
    with urlopen(url, timeout=8) as response:
        data = json.load(response)
    if not data.get('found'):
        raise KeyError('weather_not_found')
    data['_source'].pop('stream_state', None)
    now = datetime.now(KST)
    from weather.pipeline.service_view import enrich
    current = enrich(data['_source'], now)
    return dict(region=region, weather=current, guidance=current['guidance'],
                music_weather=current['music_weather'],
                viewed_at=now.isoformat(), source='Elasticsearch 저장 자료')

def lookup_region(identifier):
    if identifier.startswith('road:'):
        return road_lookup.lookup(identifier)
    with connection() as db:
        row=db.execute('SELECT payload FROM weather_mapping.region WHERE id=%s',(identifier,)).fetchone()
    return row['payload'] if row else None

def weather_for_region(identifier):
    region=lookup_region(identifier)
    if region is None:
        raise KeyError('region_not_found')
    if region.get('mapping_status','mapped')!='mapped':
        raise ValueError('region_mapping_unresolved')
    return read_weather(region)
