"""기존 JSON/SQLite 매핑을 PostgreSQL에 원자적으로 이관. --apply 명시 필요."""
import argparse
import json
import os
import sqlite3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def connection():
    import psycopg
    from psycopg.rows import dict_row
    dsn=os.environ.get('WEATHER_MAPPING_DSN', '')
    if not dsn and not os.environ.get('PGHOST'):
        raise RuntimeError('WEATHER_MAPPING_DSN_or_PGHOST_missing')
    return psycopg.connect(dsn, row_factory=dict_row, connect_timeout=5,
                           options='-c search_path=weather_mapping,public -c statement_timeout=600000')

def import_mapping(region_path,road_path,apply=False):
    if not apply: raise ValueError('explicit_apply_required')
    from psycopg.types.json import Jsonb
    data=json.loads(Path(region_path).read_text(encoding='utf-8'))
    if not data.get('entries'): raise ValueError('empty_regions')
    source=sqlite3.connect(Path(road_path).resolve().as_uri()+'?mode=ro',uri=True)
    try:
        with connection() as db:
            # 한 트랜잭션: 검증 실패·접속 중단 시 기존 자료 유지.
            db.execute(Path(__file__).with_name('mapping_postgres.sql').read_text(encoding='utf-8'))
            db.execute('SELECT pg_advisory_xact_lock(3141625)')
            db.execute('TRUNCATE weather_mapping.road_address, weather_mapping.road, weather_mapping.region, weather_mapping.metadata')
            with db.cursor().copy('COPY weather_mapping.region FROM STDIN') as copy:
                for r in data['entries']:
                    copy.write_row((r['id'],r.get('weather_region_code'),r['name'],r['address'],r['nx'],r['ny'],Jsonb(r)))
            counts={'region':len(data['entries'])}
            for name in ('road','road_address','metadata'):
                expected=source.execute('SELECT COUNT(*) FROM '+name).fetchone()[0]
                with db.cursor().copy('COPY weather_mapping.'+name+' FROM STDIN') as copy:
                    for row in source.execute('SELECT * FROM '+name):
                        copy.write_row(row)
                actual=db.execute('SELECT COUNT(*) AS n FROM weather_mapping.'+name).fetchone()['n']
                if actual!=expected: raise ValueError('mapping_count_mismatch')
                counts[name]=actual
            db.execute("INSERT INTO weather_mapping.metadata VALUES(%s,%s) ON CONFLICT(name) DO UPDATE SET value=excluded.value",
                       ('region_metadata',json.dumps({k:v for k,v in data.items() if k!='entries'},ensure_ascii=False)))
            return counts
    finally: source.close()

def load_regions():
    with connection() as db:
        data=json.loads(db.execute("SELECT value FROM weather_mapping.metadata WHERE name='region_metadata'").fetchone()['value'])
        data['entries']=[r['payload'] for r in db.execute('SELECT payload FROM weather_mapping.region')]
        return data

class RoadConnection:
    def __init__(self):
        import psycopg
        try: self.db=connection()
        except psycopg.Error: raise RuntimeError('mapping_unavailable') from None
    def execute(self,sql,params=()):
        import psycopg
        try: return self.db.execute(sql.replace('?','%s'),params)
        except psycopg.Error: raise RuntimeError('mapping_query_failed') from None
    def close(self): self.db.close()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--regions',type=Path,required=True)
    parser.add_argument('--roads',type=Path,required=True)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    try:
        print(json.dumps(import_mapping(args.regions,args.roads,args.apply)))
    except Exception as error:
        # DSN·접속 문자열은 출력하지 않음.
        print(json.dumps({'ok':False,'error_type':type(error).__name__}))
        raise SystemExit(1)
if __name__=='__main__': main()
