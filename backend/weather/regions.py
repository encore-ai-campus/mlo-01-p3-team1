"""지역 선택 계층. 실제 기상청 매핑과 시험 날씨를 혼동하지 않습니다."""
import json
from functools import lru_cache
from importlib.resources import files


def choice(row):
    address=row.get('address',row.get('name','')).strip()
    province,_,tail=address.partition(' ')
    locality=row['name'].strip()
    district=tail[:-len(locality)].strip() if tail.endswith(locality) else tail
    return {'region_id':row['id'],'name':address,'province':row.get('sido') or province,
            'district':row.get('sigungu') or district or province,'locality':locality,
            'nx':row['nx'],'ny':row['ny']}


@lru_cache(maxsize=1)
def bundled():
    data=json.loads(files('pipeline.weather').joinpath('mapping.json').read_text(encoding='utf8'))
    result=[]
    for row in data['regions']:
        province=row['sido'];district=row['sigungu'] or province;locality=row['name'].strip()
        address=' '.join([province,*([district] if district!=province else []),locality])
        result.append({'id':'region:'+row['region_code'],'name':locality,'address':address,
                       'sido':province,'sigungu':district,'nx':row['nx'],'ny':row['ny'],
                       'mapping_version':data['version'],'kind':locality[-1] if locality[-1] in '읍면동' else '지역'})
    return result


def demo_region(identifier):
    return next((row for row in bundled() if row['id']==identifier),None)
