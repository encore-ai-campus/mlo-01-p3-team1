"""원래 측정값을 보존하고 시간·품질을 확인한 서비스 특징 생성."""
import json
import math
from datetime import datetime, timedelta
from pathlib import Path
from pipeline.weather.weather_normalize import KST
from pipeline.weather.sky import classify_sky, current_sky, usable
from pipeline.weather.comfort import comfort
from pipeline.weather.daylight import grid_daylight

RULE_VERSION = 'weather_features_v0.3'
PTY_NAMES = {0:'없음',1:'비',2:'비·눈',3:'눈',4:'소나기',5:'빗방울',6:'빗방울·눈날림',7:'눈날림'}
SKY_NAMES = {1:'맑음',3:'구름 많음',4:'흐림'}


def valid_number(measurements, category, unit):
    item=measurements.get(category,{})
    value=item.get('value')
    if item.get('status')=='valid' and item.get('unit')==unit and isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value):
        return value
    return None


def amount_level(value, thresholds, labels):
    if value is None: return None
    if value==0: return '0'
    for limit,label in zip(thresholds,labels):
        if value<limit: return label
    return labels[-1]


def matching_supplement(base, category, as_of):
    row=base.get('supplements',{}).get(category)
    if not row or base['kind']!='forecast' or row.get('kind')!='forecast': return None
    if (row.get('nx'),row.get('ny'),row.get('target_at'))!=(base['nx'],base['ny'],base['target_at']): return None
    if as_of and datetime.fromisoformat(row['issued_at'])>as_of: return None
    return row


def availability(items, reference):
    received=[]
    for item in items:
        try:
            at=datetime.fromisoformat(item.get('received_at',''))
            if at.tzinfo is not None and (reference is None or at<=reference): received.append(at)
        except (ValueError,TypeError): pass
    status='actual_collected' if items and len(received)==len(items) else ('partial_collection_time' if received else 'actual_collection_time_not_provided')
    return dict(available_at=max(received).isoformat() if received else None,availability_status=status)


def precipitation_group(code):
    if code==0: return 'none'
    if code in (1,4,5): return 'rain'
    if code in (3,7): return 'snow'
    if code in (2,6): return 'mixed'
    return None


def classify(base, as_of=None):
    reference=datetime.fromisoformat(as_of) if as_of else None
    if reference and reference.tzinfo is None: raise ValueError('as_of 시간대 필요')
    config=base.get('config') or {}
    raw_values=base['measurements']
    limit=config.get('observation_max_age_minutes',30) if base['kind']=='observation' else config.get('forecast_max_age_minutes',120)
    values={code:item for code,item in raw_values.items() if reference is None or usable(item,item.get('unit'),base['target_at'],reference,limit)}
    pty=valid_number(values,'PTY','code')
    if pty not in PTY_NAMES: pty=None
    rain=valid_number(values,'RN1','mm')
    wind=valid_number(values,'WSD','m/s')
    temp=valid_number(values,'T1H','degC')
    humidity=valid_number(values,'REH','%')
    lightning=valid_number(values,'LGT','kA')
    sno=matching_supplement(base,'SNO',reference)
    kim=matching_supplement(base,'TCDC',reference)
    snow=None
    if sno and (reference is None or usable(sno['measurement'],'cm',base['target_at'],reference,config.get('sno_max_age_minutes',300))):
        snow=valid_number({'SNO':sno['measurement']},'SNO','cm')
    sky=classify_sky(values.get('SKY'),kim['measurement'] if kim else None,base['target_at'],reference,config)
    wind_level=None if wind is None else ('약함' if wind<4 else ('다소 강함' if wind<9 else '강함'))
    notes=[]
    if len(values)!=len(raw_values) or any(m.get('status')!='valid' for m in raw_values.values()): notes.append('일부 기본 항목 결측·오류·만료')
    if pty in (1,2,4,5,6) and rain==0: notes.append('강수형태 있음·1시간 강수량 0: 두 값 유지')
    if pty==0 and rain is not None and rain>0: notes.append('강수형태 없음·1시간 강수량 양수: 누적 구간 확인')
    if rain is not None and values['RN1'].get('window_status')!='verified': notes.append('RN1 누적 경계 미확인')
    if snow is not None and sno['measurement'].get('window_status')!='verified': notes.append('SNO 누적 경계 미확인')
    if kim: notes.append('KIM 모델 격자와 기본 격자의 공간 차이 보존')
    weather_type=PTY_NAMES.get(pty) if pty not in (None,0) else (sky['label'] if pty==0 and sky['state'] else None)
    combination=PTY_NAMES[pty]+'+'+wind_level+' 바람' if pty not in (None,0) and wind_level else None
    refs={'base':dict(source=base.get('source'),issued_at=base['issued_at'],target_at=base['target_at'])}
    used=list(raw_values.values())
    refs['base'].update(received_at=availability(used,reference)['available_at'])
    for code,row,accepted in [('SNO',sno,snow is not None),('TCDC',kim,sky['cloud_percent'] is not None)]:
        if row:
            refs[code]=dict(source=row['source'],issued_at=row['issued_at'],target_at=row['target_at'],received_at=row['measurement'].get('received_at'),used=accepted)
            if accepted: used.append(row['measurement'])
    at=datetime.fromisoformat(base['target_at']).astimezone(KST)
    thermal=comfort(temp,humidity,wind,at.month,config)
    return dict(nx=base['nx'],ny=base['ny'],kind=base['kind'],target_at=base['target_at'],rule_version=RULE_VERSION,
        calendar_month=at.month,season=thermal['season'],weather_type=weather_type,
        precipitation_type=PTY_NAMES.get(pty),precipitation_code=pty,precipitation_group=precipitation_group(pty),
        rain_amount_mm=rain,wind_mps=wind,
        rain_amount_level=amount_level(rain,[3,15,30],['약함','보통','강함','매우 강함']),
        snow_amount_cm=snow,snow_amount_level=amount_level(snow,config.get('snow_intensity_thresholds_cm',[0.5,1.0]),['약함','보통','강함']),
        wind_level=wind_level,sky_state=sky['label'] if sky['state'] else None,sky=sky,
        cloud_percent_supplement=sky['cloud_percent'],lightning_forecast=None if lightning is None else lightning>0,
        precipitation_probability=valid_number(values,'POP','%'),temperature_c=temp,humidity_percent=humidity,
        temperature_level=thermal['temperature_level'],humidity_level=thermal['humidity_level'],feels_like_c=thermal['feels_like_c'],
        comfort=thermal,thermal_policy_status='service_thresholds_v1',daylight=grid_daylight(base['nx'],base['ny'],at),
        combination=combination,quality_notes=notes,input_refs=refs,**availability(used,reference))


def classify_slot(document, slot, kind, now=None, config=None):
    values=slot.get('values',{})
    issued=slot.get('issued_at') or max((m['issued_at'] for m in values.values() if m.get('issued_at')),default=slot['target_at'])
    base=dict(nx=document['nx'],ny=document['ny'],kind=kind,target_at=slot['target_at'],issued_at=issued,
              source='odam' if kind=='observation' else 'vsrt',measurements=values,supplements={},config=config)
    for code,item in slot.get('supplements',{}).get('values',{}).items():
        base['supplements'][code]=dict(nx=document['nx'],ny=document['ny'],kind='forecast',target_at=item.get('target_at'),issued_at=item['issued_at'],source=item['source'],measurement=item)
    return classify(base,now.isoformat() if now else None)


def guidance_features(document, now=None, config=None):
    now=now or datetime.now(KST)
    config=config or {}
    observation=document.get('observation')
    current=classify_slot(document,observation,'observation',now,config) if observation else None
    sky=current_sky(document,now,config)
    sun=grid_daylight(document['nx'],document['ny'],now)
    if current:
        target=datetime.fromisoformat(observation['target_at'])
        fresh=target<=now and now-target<=timedelta(minutes=config.get('observation_max_age_minutes',30))
        current['observation_status']='fresh' if fresh else ('future' if target>now else 'stale')
        if not fresh:
            for key in ['precipitation_type','precipitation_code','precipitation_group','temperature_c','humidity_percent','wind_mps','wind_level','rain_amount_mm','rain_amount_level','temperature_level','humidity_level','feels_like_c']:
                current[key]=None
            current['comfort']=comfort(None,None,None,now.astimezone(KST).month,config)
        current.update(sky=sky,sky_state=sky['label'] if sky['state'] else None,cloud_percent_supplement=sky['cloud_percent'],daylight=sun)
        pty=current['precipitation_type']
        current['weather_type']=sky['label'] if pty=='없음' and sky['state'] else pty
        if pty is None: current['weather_type']=sky['label']+' · 강수 확인 필요' if sky['state'] else '현재 날씨 확인 불가'
        if pty=='없음' and not sky['state']: current['weather_type']='강수 없음 · 하늘 판단 불가'
        if pty in ('비','소나기'):
            prefix={'약함':'약한 ','보통':'','강함':'강한 ','매우 강함':'매우 강한 '}.get(current['rain_amount_level'],'')
            current['weather_type']=prefix+pty+('와 강한 바람' if current['wind_level']=='강함' else '')
        used=list(observation.get('values',{}).values())
        for code,field in [('SKY','sky_code'),('TCDC','cloud_percent')]:
            if sky[field] is not None and sky['inputs'][code]: used.append(sky['inputs'][code])
        current.update(availability(used,now))
    return dict(current=current,current_sky=sky,daylight=sun,observation_max_age_minutes=config.get('observation_max_age_minutes',30),alert_max_gap_minutes=config.get('alert_max_gap_minutes',20),
                forecast=[classify_slot(document,hour,'forecast',now,config) for hour in document.get('forecast',[])])
