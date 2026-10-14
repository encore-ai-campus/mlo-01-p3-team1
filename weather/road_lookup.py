"""공식 도로명주소 검색. 주소의 행정동 → 기존 기상청 격자만 사용."""
from contextlib import closing
import re

from weather.pipeline.mapping_postgres import RoadConnection

def connect():
    return RoadConnection()


def region(row):
    road_number=str(row['main_no'])+('-'+str(row['sub_no']) if row['sub_no'] else '')
    underground='지하 ' if row['underground']=='1' else ''
    name=row['name']+' '+underground+road_number
    full=' '.join(p for p in [row['sido'],row['sigungu'],row['eup_myeon'],name] if p)
    return dict(id='road:'+row['address_code'],name=name,address=full,kind='도로명주소',level=6,
                weather_region_code=row['weather_region_code'],
                weather_address=row.get('weather_address') or row['admin_names'],
                nx=row['nx'],ny=row['ny'],mapping_status=row['mapping_status'],
                mapping_basis='official_road_admin_code',address_version=row.get('address_version'))


COLUMNS="a.*,r.sido,r.sigungu,r.eup_myeon,r.name,(SELECT value FROM metadata WHERE name='version') AS address_version,(SELECT payload->>'weather_address' FROM region WHERE id='region:' || a.weather_region_code) AS weather_address"


def lookup(identifier):
    if not re.fullmatch(r'road:\d{26}',identifier):return None
    with closing(connect()) as db:
        row=db.execute('SELECT '+COLUMNS+' FROM road_address a JOIN road r ON r.id=a.road_id WHERE a.address_code=?',
                       (identifier[5:],)).fetchone()
    return region(row) if row else None


def should_search(query,local_matches):
    if len(query.replace(' ',''))<3:return False
    return not local_matches or bool(re.search(r'(?:로|길)(?:\s|\d|$)|(?:^|\s)\d+(?:-\d+)?$',query))


def search(query,limit=30):
    # 도로명 내부 숫자는 유지하고 마지막 건물번호만 분리. 구일로4길22 → 구일로4길 22.
    query=re.sub(r'((?:로|길))\s*(\d{1,5}(?:-\d{1,5})?)\s*$',r'\1 \2',query)
    words=re.findall(r'[가-힣A-Za-z0-9-]+',query)
    number=re.fullmatch(r'(\d{1,5})(?:-(\d{1,5}))?',words[-1]) if words else None
    if number:words=words[:-1]
    if not words or len(''.join(words))<3:return dict(items=[],total=0)
    # 주소의 단어 순서와 무관하게 검색. 건물번호는 숫자 컬럼으로 정확히 비교.
    conditions=' AND '.join('search_text LIKE ?' for _ in words)
    exact_road=next((word for word in reversed(words) if word.endswith(('로','길'))),'')
    with closing(connect()) as db:
        roads=db.execute('SELECT id FROM road WHERE '+conditions+' ORDER BY CASE WHEN name=? THEN 0 ELSE 1 END,sido,sigungu,eup_myeon,name',
                         ['%'+word+'%' for word in words]+[exact_road]).fetchall()
        if not roads:return dict(items=[],total=0)
        all_rows=[]
        total=0
        for chunk_start in range(0,len(roads),400):
            ids=[r['id'] for r in roads[chunk_start:chunk_start+400]]
            where='a.road_id IN ('+','.join('?' for _ in ids)+')'
            values=list(ids)
            if number:
                where+=' AND a.main_no=? AND a.sub_no=?'
                values.extend([int(number[1]),int(number[2] or 0)])
            count_row=db.execute('SELECT COUNT(*) AS total FROM road_address a WHERE '+where,values).fetchone()
            total+=count_row['total']
            if len(all_rows)<limit:
                rows=db.execute('SELECT '+COLUMNS+' FROM road_address a JOIN road r ON r.id=a.road_id WHERE '+where+
                                ' ORDER BY CASE WHEN r.name=? THEN 0 ELSE 1 END,r.sido,r.sigungu,r.eup_myeon,r.name,a.main_no,a.sub_no,a.underground LIMIT ?',
                                values+[exact_road,limit-len(all_rows)]).fetchall()
                all_rows.extend(rows)
    return dict(items=[region(row) for row in all_rows],total=total)
