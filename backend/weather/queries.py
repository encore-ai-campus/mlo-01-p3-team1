"""공통 API에서 호출할 지역 검색·최신 날씨 조회. 화면·HTTP 서버 없음."""
from datetime import datetime
from pipeline.weather.es_latest import read_grid
from pipeline.weather.common import KST
from pipeline.weather.mapping_postgres import load_regions, connection
from backend.weather import road_lookup

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
    """nx/ny가 있는 지역 dict → region/weather/guidance/music_weather 응답.

    DB에서 읽은 자료의 유효성을 현재 조회 시각으로 다시 판단.
    """
    document = read_grid(region.get('nx'), region.get('ny'))
    now = datetime.now(KST)
    from pipeline.weather.service_view import enrich
    current = enrich(document, now)
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
