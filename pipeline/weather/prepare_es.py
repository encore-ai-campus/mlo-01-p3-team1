"""명시 --apply 때만 전용 최신 인덱스 생성. 기존 인덱스 변경/덮어쓰기 없음."""
import argparse
import json
from urllib.error import HTTPError
from pipeline.weather.es_latest import configuration
from pipeline.weather.es_current import request

MAPPING={'mappings':{'dynamic':'strict','properties':{
    'schema_version':{'type':'integer'},'revision':{'type':'long'},
    'state_hash':{'type':'keyword'},'stored_at':{'type':'date'},
    # Read by grid ID. The full normalized rows and shared feature payload remain in _source.
    'rows':{'type':'object','enabled':False},'view':{'type':'object','enabled':False}}}}


def ensure_index():
    base,index=configuration()
    try:
        existing=request(base,'GET','/'+index)
    except HTTPError as error:
        if error.code!=404:raise
        result=request(base,'PUT','/'+index,MAPPING)
        if result.get('acknowledged') is not True:raise RuntimeError('weather_index_not_acknowledged')
        print('weather_index_created');return
    expected=MAPPING['mappings']
    actual=existing.get(index,{}).get('mappings',{})
    if actual.get('dynamic')!=expected['dynamic'] or any(actual.get('properties',{}).get(k)!=v for k,v in expected['properties'].items()):
        raise RuntimeError('weather_index_incompatible_no_changes_applied')
    print('weather_index_compatible')


def main():
    from pipeline.environment import load
    load('weather')
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    if not args.apply:
        print(json.dumps(MAPPING,ensure_ascii=False,indent=2));return
    ensure_index()


if __name__=='__main__':main()
