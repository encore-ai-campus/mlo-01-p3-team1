"""4종 공통 JSON 변환. 수치의 의미 변경과 격자 필터는 Spark 단계."""
import hashlib,json,math
from datetime import datetime,timedelta,timezone
from weather.weather_normalize import normalize_value
from weather.pipeline.kim_area import parse_area, select_grids
KST=timezone(timedelta(hours=9)); UTC=timezone.utc
OBS=['T1H','REH','RN1','WSD','UUU','VVV','VEC','PTY']
FORECAST=OBS+['SKY','LGT','POP']

def encode(value): return json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf-8')
def digest(value): return hashlib.sha256(encode(value)).hexdigest()
def stamp(value,zone):
    fmt='%Y%m%d%H%M' if len(value)==12 else '%Y%m%d%H'
    return datetime.strptime(value,fmt).replace(tzinfo=zone).astimezone(KST).isoformat()

def parse_response(job,body):
    params=job['params']; source=job['source']
    if source!='KIMG':
        values=[v.strip() for v in body.decode('euc-kr').replace('\r','').replace('\n','').split(',') if v.strip()]
        if len(values)!=37697: raise ValueError('grid_shape')
        if not all(math.isfinite(float(v)) for v in values): raise ValueError('grid_nonfinite')
        issued=stamp(params['tmfc'],KST)
        target=stamp(params.get('tmef',params['tmfc']),KST)
        # 온도 전 격자 0 응답은 이전 시험에서 잘못된 대상시간에 관찰됨. 단정 정제 대신 거부.
        if job['category']=='T1H' and all(float(v)==0 for v in values): raise ValueError('all_zero_temperature')
        return [(issued,target,[dict(nx=i%149+1,ny=i//149+1,raw=v) for i,v in enumerate(values)])]
    if job.get('response_format') == 'kim_area_csv':
        if job['category'] != 'TCDC' or params.get('vars') != 'tcld':
            raise ValueError('kim_metadata')
        issued = stamp(params['tmfc'], UTC)
        hf = int(params['hf'])
        if hf < 0 or hf > 135:
            raise ValueError('kim_target_range')
        target = (datetime.fromisoformat(issued) + timedelta(hours=hf)).isoformat()
        return [(issued, target, parse_area(body))]
    lines=[l for l in body.decode('utf-8').splitlines() if l.startswith('|')]
    if len(lines)!=2: raise ValueError('kim_table')
    head=[v.strip() for v in lines[0].split('|')[1:-1]]
    cells=[v.strip() for v in lines[1].split('|')[1:-1]]
    if len(head)!=len(cells) or cells[1]!='TCDC' or cells[0]!=params['tm'][:10]: raise ValueError('kim_metadata')
    if abs(float(cells[2])-params['lon'])>0.0001 or abs(float(cells[3])-params['lat'])>0.0001: raise ValueError('kim_location')
    if not head[4:]: raise ValueError('kim_no_targets')
    result=[]
    for time,raw in zip(head[4:],cells[4:]):
        if not math.isfinite(float(raw)): raise ValueError('kim_nonfinite')
        target=stamp(time,UTC)
        if not stamp(params['tmef1'],UTC)<=target<=stamp(params['tmef2'],UTC): raise ValueError('kim_target_range')
        result.append((stamp(cells[0],UTC),target,[dict(nx=job['nx'],ny=job['ny'],raw=raw)]))
    return result

def make_events(job,body,received_at,raw_path,run_id):
    sha=hashlib.sha256(body).hexdigest()
    for issued,target,readings in parse_response(job,body):
        area = job.get('response_format') == 'kim_area_csv'
        chunk_size = len(readings) if area else 2048
        for start in range(0,len(readings),chunk_size):
            event=dict(schema_version=1,source=job['source'],kind='observation' if job['source']=='odam' else 'forecast',category=job['category'],issued_at=issued,target_at=target,received_at=received_at,source_hash=sha,raw_path=raw_path,run_id=run_id,part=start//chunk_size,readings=readings[start:start+chunk_size],mapping_version=job.get('mapping_version', '2026-07-01'))
            if job.get('request_id'):
                event['request_id']=job['request_id']
            if area:
                event.update(source_format='kim_area_csv', spatial_basis='nearest_kim_grid_v1')
            elif job['source']=='KIMG':
                event.update(query_lat=job['params']['lat'],query_lon=job['params']['lon'],spatial_basis=job.get('point_policy','selected_region_point_sample'))
            else: event['spatial_basis']='dfs_5km'
            event['event_id']=digest([job['source'],job['category'],issued,target,sha,event['part'],job.get('nx'),job.get('ny')])
            if area:
                event['event_id'] = digest([event['event_id'], event['spatial_basis'], event['mapping_version']])
            if len(encode(event))>900000: raise ValueError('message_too_large')
            yield event

def normalize_event(event,grid_keys):
    if event['schema_version']!=1: raise ValueError('schema_version')
    area = event.get('source_format') == 'kim_area_csv'
    if area and not isinstance(grid_keys, dict):
        raise ValueError('kim_mapping_required')
    readings = select_grids(event['readings'], grid_keys) if area else event['readings']
    for reading in readings:
        nx,ny=reading['nx'],reading['ny']
        if (nx,ny) not in grid_keys: continue
        row={k:event[k] for k in ('source','kind','category','issued_at','target_at','received_at','source_hash','raw_path','run_id','mapping_version','spatial_basis')}
        if event.get('request_id'): row['request_id']=event['request_id']
        row.update(nx=nx,ny=ny,rule_version='normalize_v3' if event['category']=='TCDC' else 'normalize_v2',data_mode=event.get('data_mode','live'))
        row['measurement']=normalize_value(event['category'],reading['raw'],event['source'],event['kind'],sno_encoding='amount_cm' if event['category']=='SNO' else None)
        identity = [event['source'],event['kind'],event['issued_at'],event['target_at'],nx,ny,event['category'],event['source_hash'],row['rule_version']]
        if event['category'] == 'TCDC':
            identity += [event['spatial_basis'], event['mapping_version']]
        row['_id'] = digest(identity)
        row['slot_id']=digest([event['source'],event['kind'],event['target_at'],nx,ny,event['category']])
        if area:
            row.update({k:reading[k] for k in ('query_lat','query_lon','source_ix','source_iy','source_lat','source_lon','spatial_distance_km')})
            row['source_format'] = 'kim_area_csv'
        elif event['source']=='KIMG':
            row.update(query_lat=event['query_lat'],query_lon=event['query_lon'])
        yield row
