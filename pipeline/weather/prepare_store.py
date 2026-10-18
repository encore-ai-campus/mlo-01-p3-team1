"""Initialize missing region tables and the latest ES index; preserve existing data."""
import argparse
import json
from pathlib import Path
from pipeline.environment import load


def prepare_regions():
    from psycopg.types.json import Jsonb
    from pipeline.weather.mapping_postgres import connection
    from backend.weather.regions import bundled
    rows=bundled()
    with connection() as db:
        db.execute(Path(__file__).with_name('mapping_postgres.sql').read_text(encoding='utf8'))
        db.execute('SELECT pg_advisory_xact_lock(3141625)')
        count=db.execute('SELECT COUNT(*) AS n FROM weather_mapping.region').fetchone()['n']
        if count:
            metadata=db.execute("SELECT value FROM weather_mapping.metadata WHERE name='region_metadata'").fetchone()
            if not metadata:raise RuntimeError('existing_mapping_metadata_missing')
            return {'created':False,'region_count':count}
        for row in rows:
            db.execute('INSERT INTO weather_mapping.region(id,weather_region_code,name,address,nx,ny,payload) VALUES(%s,%s,%s,%s,%s,%s,%s)',
                       (row['id'],row['id'].split(':',1)[1],row['name'],row['address'],row['nx'],row['ny'],Jsonb(row)))
        metadata={'mapping_version':rows[0]['mapping_version'],'region_count':len(rows),'road_data_loaded':False}
        db.execute("INSERT INTO weather_mapping.metadata(name,value) VALUES('region_metadata',%s) ON CONFLICT(name) DO UPDATE SET value=EXCLUDED.value",(json.dumps(metadata),))
    return {'created':True,'region_count':len(rows),'road_data_loaded':False}


def main():
    load('weather')
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    if not args.apply:
        print(json.dumps({'applied':False,'steps':['missing_region_tables','region_mapping_if_empty','weather_topic','compatible_es_index']}));return
    try:
        regions=prepare_regions()
        from pipeline.prepare_kafka import ensure_topic
        ensure_topic('KAFKA_')
        from pipeline.weather.prepare_es import ensure_index
        ensure_index()
        print(json.dumps({'applied':True,'regions':regions,'weather_observations_loaded':False}))
    except Exception as error:
        print(json.dumps({'complete':False,'partial_preparation_possible':True,'error_type':type(error).__name__}));raise SystemExit(1) from None


if __name__=='__main__':main()
