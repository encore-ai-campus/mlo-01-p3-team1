"""공식 법정리 → 기상청 읍면동 매핑. 기존 날씨 격자 목록은 유지."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'https://www.code.go.kr/stdcode/regCodeL.do'
PAJU = 'https://dong.paju.go.kr/dong/dong_01/dong_sub17/dong_sub17_01/dong_sub17_01_01.jsp'


def address(region):
    parts = [region['sido']]
    if region['sigungu'] != region['sido']:
        district = region['sigungu']
        if district.endswith('구') and '시' in district:
            district = district.replace('시', '시 ', 1)
        parts.append(district)
    if region.get('level',4)>=4:
        parts.append(region['name'].strip())
    return ' '.join(parts)


def build(legal_path, output_path, mapping_path):
    mapping = json.loads((mapping_path).read_text(encoding='utf-8'))
    regions = mapping['regions']
    by_code = {r['region_code']: r for r in regions}
    by_name = {address(r).replace(' ', ''): r for r in regions}
    legal_rows = [line.split('\t') for line in legal_path.read_text(encoding='utf-8').splitlines()[1:]]
    active = {r[0]: r[1].strip() for r in legal_rows if len(r)==3 and r[2]=='존재'}
    # 공식 전체자료에서 구지면 폐지·구지읍 존재 및 하위 리 이름 일치 확인.
    old = {r[1].split()[-1] for r in legal_rows if r[0].startswith('27710380') and r[0][-2:]!='00'}
    new = {r[1].split()[-1] for r in legal_rows if r[0].startswith('27710268') and r[0][-2:]!='00'}
    if not old or old != new:
        raise ValueError('구지읍 코드 변경 근거 재확인 필요')
    overrides = {'2771026800': ('2771038000', 'official_code_change', SOURCE),
                 '4148038000': ('4148039000', 'official_admin_jurisdiction', PAJU),
                 '4148040000': ('4148039000', 'official_admin_jurisdiction', PAJU),
                 '4148041000': ('4148039000', 'official_admin_jurisdiction', PAJU)}
    entries = []
    for r in regions:
        entries.append(dict(id='region:'+r['region_code'], name=r['name'].strip(), address=address(r),
                            kind=r['name'].strip()[-1] if r['name'].strip()[-1] in '읍면동' else '지역', weather_region_code=r['region_code'],
                            weather_address=address(r), nx=r['nx'], ny=r['ny'], mapping_basis='kma_region'))
    for r in mapping.get('admin_regions', []):
        label=r['name'].strip()
        if label.endswith('구') and '시' in label:
            label=label.replace('시','시 ',1)
        entries.append(dict(id='region:'+r['region_code'],name=label,address=address(r),
                            kind=r['kind'],level=r['level'],weather_region_code=r['region_code'],
                            weather_address=address(r),nx=r['nx'],ny=r['ny'],mapping_basis='kma_admin_region'))
    for code, name in active.items():
        if not name.endswith('리') or code[-2:]=='00':
            continue
        parent_code = code[:8]+'00'
        parent = active.get(parent_code, '')
        if not parent.endswith(('읍', '면')):
            raise ValueError('리 상위 읍면 확인 필요: '+code)
        r = by_code.get(parent_code) or by_name.get(parent.replace(' ', ''))
        basis, evidence = 'official_parent', SOURCE
        if r is None and parent_code in overrides:
            target, basis, evidence = overrides[parent_code]
            r = by_code[target]
        if r is None:
            raise ValueError('날씨 매핑 없음: '+name)
        entries.append(dict(id='ri:'+code, name=name.split()[-1], address=name, kind='리',
                            legal_code=code, legal_parent_code=parent_code, parent_address=parent,
                            weather_region_code=r['region_code'], weather_address=address(r),
                            nx=r['nx'], ny=r['ny'], mapping_basis=basis, mapping_evidence=evidence))
    entries.sort(key=lambda r: (r['name'], r['address']))
    output = dict(mapping_version=mapping['version'], legal_source=SOURCE,
                  region_count=len(regions), admin_count=len(mapping.get('admin_regions',[])),
                  ri_count=sum(r['kind']=='리' for r in entries), entries=entries)
    output_path.parent.mkdir(parents=True,exist_ok=True)
    output_path.write_text(json.dumps(output,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print(json.dumps({k:v for k,v in output.items() if k!='entries'},ensure_ascii=False))


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--legal',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--mapping',type=Path,default=ROOT/'pipeline/mapping.json')
    args=parser.parse_args()
    build(args.legal,args.output,args.mapping)
