"""공식 도로명주소 한글 전체분 → PostgreSQL 이관용 중간 주소 DB. 기상청 행정동 코드 연결."""
import argparse
import io
import json
import re
import sqlite3
import zipfile
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parent


def parse_codes(text):
    return sorted(set(code+'00' if len(code)==8 else code
                      for code in re.findall(r'(?<!\d)(?:\d{10}|\d{8})(?!\d)',text)))


def build(source, database, mapping_path, version):
    database.parent.mkdir(parents=True,exist_ok=True)
    if database.exists():
        raise SystemExit('road_database_already_exists')
    mapping=json.loads((mapping_path).read_text(encoding='utf-8'))
    by_code={r['region_code']:r for r in mapping['regions']}
    # 같은 공식 코드 자료에서 검증된 구지면→구지읍 개편 연결.
    by_code['2771026800']=by_code['2771038000']
    roads={}
    counts=Counter()
    unmapped=Counter()
    with sqlite3.connect(database) as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA synchronous=NORMAL')
        db.execute('CREATE TABLE road (id INTEGER PRIMARY KEY, road_code TEXT NOT NULL, sido TEXT NOT NULL, sigungu TEXT NOT NULL, eup_myeon TEXT NOT NULL, name TEXT NOT NULL, search_text TEXT NOT NULL)')
        db.execute('CREATE TABLE road_address (id INTEGER PRIMARY KEY, address_code TEXT NOT NULL, road_id INTEGER NOT NULL REFERENCES road(id), main_no INTEGER NOT NULL, sub_no INTEGER NOT NULL, underground TEXT NOT NULL, admin_codes TEXT NOT NULL, admin_names TEXT NOT NULL, weather_region_code TEXT, nx INTEGER, ny INTEGER, mapping_status TEXT NOT NULL)')
        db.execute('CREATE TABLE metadata (name TEXT PRIMARY KEY, value TEXT NOT NULL)')
        batch=[]
        with zipfile.ZipFile(source) as archive:
            for name in archive.namelist():
                if not name.startswith('rnaddrkor_') or not name.endswith('.txt'):
                    continue
                member_count=0
                with archive.open(name) as raw:
                    for line in io.TextIOWrapper(raw,encoding='cp949'):
                        fields=line.rstrip('\r\n').split('|')
                        if len(fields)!=24:raise ValueError('road_schema_mismatch')
                        counts['source_rows']+=1
                        if fields[20]=='63':
                            counts['abolished_rows']+=1
                            continue
                        eup=fields[4] if fields[4].endswith(('읍','면')) else ''
                        key=(fields[9],fields[2],fields[3],eup,fields[10])
                        road_id=roads.get(key)
                        if road_id is None:
                            road_id=len(roads)+1
                            roads[key]=road_id
                            text=''.join([fields[2],fields[3],eup,fields[10]]).replace(' ','')
                            db.execute('INSERT INTO road VALUES (?,?,?,?,?,?,?)',
                                       (road_id,fields[9],fields[2],fields[3],eup,fields[10],text))
                        codes=parse_codes(fields[14])
                        candidates=[by_code[code] for code in codes if code in by_code]
                        grids={(r['nx'],r['ny']) for r in candidates}
                        # 여러 행정동이 함께 제공되면 격자가 같을 때만 하나로 확정.
                        complete=bool(codes) and len(candidates)==len(codes)
                        mapped=complete and len(grids)==1
                        region=candidates[0] if mapped else None
                        state='mapped' if mapped else 'ambiguous' if len(grids)>1 else 'unmapped'
                        counts[state]+=1
                        if not mapped:unmapped[fields[14]+' / '+fields[15]]+=1
                        batch.append((fields[0],road_id,int(fields[12]),int(fields[13]),fields[11],
                                      fields[14],fields[15],region['region_code'] if region else None,
                                      region['nx'] if region else None,region['ny'] if region else None,state))
                        member_count+=1
                        if len(batch)>=10000:
                            db.executemany('INSERT INTO road_address (address_code,road_id,main_no,sub_no,underground,admin_codes,admin_names,weather_region_code,nx,ny,mapping_status) VALUES (?,?,?,?,?,?,?,?,?,?,?)',batch)
                            batch=[]
                    db.commit()
                print(json.dumps({'member':name,'rows':member_count,'total':counts['source_rows']},ensure_ascii=False),flush=True)
        if batch:
            db.executemany('INSERT INTO road_address (address_code,road_id,main_no,sub_no,underground,admin_codes,admin_names,weather_region_code,nx,ny,mapping_status) VALUES (?,?,?,?,?,?,?,?,?,?,?)',batch)
        db.execute('CREATE INDEX address_road_number ON road_address(road_id,main_no,sub_no)')
        db.execute('CREATE UNIQUE INDEX address_official_code ON road_address(address_code)')
        db.executemany('INSERT INTO metadata VALUES (?,?)',[
            ('source','https://business.juso.go.kr/jst/jstAddressDownload'),
            ('version',version),('mapping_version',mapping['version']),
            ('counts',json.dumps(dict(counts),ensure_ascii=False))])
        db.commit()
        db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    report=dict(counts,road_groups=len(roads),bytes=database.stat().st_size,
                unmatched_examples=unmapped.most_common(30))
    print(json.dumps(report,ensure_ascii=False),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--version',required=True)
    parser.add_argument('--mapping',type=Path,default=ROOT/'mapping.json')
    args=parser.parse_args()
    build(args.source,args.output,args.mapping,args.version)
