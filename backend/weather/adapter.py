"""A의 최신 묶음 → C의 UTC 구간 계약. 관측/예보 원값·출처는 보존합니다."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from backend.recommendation.errors import DomainError, require


def iso(at):
    return at.astimezone(timezone.utc).isoformat().replace('+00:00','Z')


def stamp(value):
    at = datetime.fromisoformat(value.replace('Z','+00:00'))
    if at.tzinfo is None:
        raise ValueError('naive_weather_time')
    return at


def build(region, document, now, config):
    observation = document.get('observation') or {}
    observed = stamp(observation['target_at']) if observation.get('target_at') else None
    obs_limit = timedelta(minutes=config['observation_max_age_minutes'])
    fc_limit = timedelta(minutes=config['forecast_max_age_minutes'])

    def value(item, code):
        valid = (item.get('status')=='valid' and item.get('unit')==('code' if code in ('PTY','SKY') else 'degC')
                 and stamp(item['issued_at'])<=now and stamp(item['received_at'])<=now)
        return item.get('value') if valid else None

    current = {'status':'missing', 'pty':None, 'sky':None}
    expires=[]
    if observed:
        measurements=observation.get('values',{})
        pty=value(measurements.get('PTY',{}),'PTY')
        temp=value(measurements.get('T1H',{}),'T1H')
        current={'status':'valid' if observed<=now<observed+obs_limit and type(pty) is int else 'stale',
                 'pty':pty,'sky':None,'observed_at':iso(observed),'source_values':measurements}
        if temp is not None:
            current['temperature']=temp
        expires.append(observed+obs_limit)
    segments=[]
    for hour in document.get('forecast',[]):
        end=stamp(hour['target_at']); start=end-timedelta(hours=1)
        values=hour.get('values',{}); pty=value(values.get('PTY',{}),'PTY'); sky=value(values.get('SKY',{}),'SKY')
        required=[values[c] for c in ['PTY','SKY'] if c in values and (c=='PTY' or pty==0)]
        issued=max((stamp(v['issued_at']) for v in required),default=stamp(hour['issued_at']))
        received=max((stamp(v['received_at']) for v in required),default=now)
        valid=(type(pty) is int and pty in (0,1,2,3,4,5,6,7) and
               (pty!=0 or type(sky) is int and sky in (1,3,4)) and issued<=now<issued+fc_limit)
        segments.append({'start_at':iso(start),'end_at':iso(end),'issued_at':iso(issued),
                         'received_at':iso(received),'pty':pty,'sky':sky,'status':'valid' if valid else 'missing',
                         'source_values':values,'source_target_at':hour['target_at'],
                         'temperature':value(values.get('T1H',{}),'T1H')})
        if start < now+timedelta(minutes=184) and end>now:
            expires.append(issued+fc_limit)
    from pipeline.weather.sky import current_sky
    sky_state=current_sky(document,now,config)
    current['sky']=sky_state['sky_code']
    current['sky_state']=sky_state
    current['sky_valid_from']=iso(stamp(sky_state['target_at']))
    current['sky_valid_until']=iso(stamp(sky_state['display_until']))
    identity=hashlib.sha256(json.dumps({k:document.get(k) for k in
        ('nx','ny','observation','forecast','sky_context')},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return {'region_id':region['id'],'region_name':region.get('address',region['name']),
            'nx':region['nx'],'ny':region['ny'],'as_of':iso(now),
            'valid_until':iso(min(expires)) if expires else iso(now),
            'is_test':False,'current':current,'segments':segments,
            'bundle_version':identity,'interval_policy':'service_hour_ending_v1',
            'mapping_version':region.get('mapping_version'), 'source_document':document}


def display(region_id, now):
    try:
        from .queries import lookup_region
        from pipeline.weather.es_latest import read_grid
        from pipeline.weather.service_view import config
        region=lookup_region(region_id)
        require(region is not None, 'REGION_NOT_FOUND', '지역을 찾을 수 없습니다.',404)
        require(region.get('mapping_status','mapped')=='mapped','REGION_MAPPING_UNRESOLVED','지역 격자를 확인해 주세요.',422)
        document=read_grid(region['nx'],region['ny'])
        require(bool(document),'FORECAST_UNAVAILABLE','저장된 날씨가 없습니다.',503)
        bundle=build(region,document,now,config())
        from backend.recommendation.weather import validate,current_profile
        try:
            bundle['weather_code']=current_profile(bundle,validate(bundle,now),now)
            bundle['recommendation_ready']=True
        except DomainError as error:
            bundle['recommendation_ready']=False;bundle['recommendation_error']=error.code
        return bundle
    except DomainError:
        raise
    except Exception:
        raise DomainError('FORECAST_UNAVAILABLE','날씨 저장소 또는 입력 형식을 확인해 주세요.',503) from None


def obtain(region_id, now):
    bundle=display(region_id,now)
    require(bundle['recommendation_ready'],'FORECAST_UNAVAILABLE','선곡에 필요한 관측·예보가 누락되거나 만료됐습니다.',503)
    return bundle
