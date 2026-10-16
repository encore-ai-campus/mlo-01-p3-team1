"""공식 엑셀에서 읍면동과 고유 격자 목록 생성. 외부 호출 없음."""
import argparse, io, json, zipfile, math
from pathlib import Path
from xml.etree import ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--version',required=True)
    args=parser.parse_args()
    source=args.source
    with zipfile.ZipFile(source) as outer:
        name=next(n for n in outer.namelist() if n.endswith('.xlsx'))
        with zipfile.ZipFile(io.BytesIO(outer.read(name))) as book:
            ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
            strings=[''.join(t.text or '' for t in s.findall('.//m:t',ns)) for s in ET.fromstring(book.read('xl/sharedStrings.xml')).findall('m:si',ns)]
            regions=[]; admin_regions=[]
            for row in ET.fromstring(book.read('xl/worksheets/sheet1.xml')).findall('.//m:row',ns):
                cells={}
                for cell in row.findall('m:c',ns):
                    v=cell.find('m:v',ns)
                    if v is not None:
                        cells[''.join(c for c in cell.get('r') if c.isalpha())]=strings[int(v.text)] if cell.get('t')=='s' else v.text
                if cells.get('A')=='kor' and cells.get('C') and not cells.get('E'):
                    province=cells['C']; district=cells.get('D','')
                    name=district or province
                    # 이어도는 행정 시·군·구가 아닌 특수 격자 표기.
                    if province!='이어도' and name.endswith(('시','도','군','구')):
                        level=1 if not district else (3 if district.endswith('구') and '시' in district else 2)
                        admin_regions.append(dict(region_code=cells['B'],sido=province,
                            sigungu=district or province,name=name,nx=int(cells['F']),ny=int(cells['G']),
                            lon=float(cells['N']),lat=float(cells['O']),level=level,
                            kind='시·도' if level==1 else name[-1]))
                if cells.get('A')=='kor' and cells.get('E'):
                    regions.append(dict(region_code=cells['B'],sido=cells.get('C'),sigungu=cells.get('D'),name=cells['E'],nx=int(cells['F']),ny=int(cells['G']),lon=float(cells['N']),lat=float(cells['O'])))
    groups={}
    for r in regions: groups.setdefault((r['nx'],r['ny']),[]).append(r)
    grids=[]
    for (nx,ny),rows in sorted(groups.items()):
        # 공식 읍면동 대표점 중 평균 위치에 가장 가까운 점. 재현 가능한 시험 정책.
        lat=sum(r['lat'] for r in rows)/len(rows); lon=sum(r['lon'] for r in rows)/len(rows)
        point=min(rows,key=lambda r:((r['lat']-lat)**2+((r['lon']-lon)*math.cos(math.radians(lat)))**2,r['region_code']))
        grids.append(dict(nx=nx,ny=ny,lat=point['lat'],lon=point['lon'],representative_region_code=point['region_code'],point_policy='nearest_member_to_mean_v1'))
    if not regions or not grids: raise ValueError('empty_mapping')
    admin_grids=[]
    known={(g['nx'],g['ny']) for g in grids}
    for r in admin_regions:
        pair=(r['nx'],r['ny'])
        if pair not in known:
            admin_grids.append(dict(nx=r['nx'],ny=r['ny'],lat=r['lat'],lon=r['lon'],
                representative_region_code=r['region_code'],point_policy='kma_admin_representative_v1'))
            known.add(pair)
    out=args.output
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(dict(version=args.version,source=name,regions=regions,grids=grids,admin_regions=admin_regions,admin_grids=admin_grids),ensure_ascii=False),encoding='utf-8')
    print(json.dumps(dict(regions=len(regions),grids=len(grids),admin_regions=len(admin_regions),admin_extra_grids=len(admin_grids),file=str(out))))
if __name__=='__main__': main()
