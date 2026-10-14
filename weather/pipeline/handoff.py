"""저장소와 독립적인 음악 담당용 날씨 JSON. 음악 점수 계산 없음."""
import hashlib
import json
from datetime import datetime, timedelta
from weather.pipeline.common import KST
from weather.pipeline.sky import POLICY as SKY_POLICY
from weather.weather_features import guidance_features

TYPE_POLICY = 'weather_type_v1'


def recommendation_type(values, sky_result=None):
    pty = values.get('PTY', {})
    if pty.get('status') != 'valid':
        return dict(type=None, status='missing_pty', candidates=[])
    code = pty.get('value')
    if code == 0:
        if sky_result is not None:
            states = {'nearly_clear':'clear','few_clouds':'clear','clear':'clear',
                      'cloudy':'cloudy','overcast':'overcast','covered':'overcast'}
            name = states.get(sky_result.get('state'))
            return dict(type=name,status='valid' if name else 'missing_sky',candidates=[])
        sky = values.get('SKY', {})
        names = {1: 'clear', 3: 'cloudy', 4: 'overcast'}
        name = names.get(sky.get('value')) if sky.get('status') == 'valid' else None
        return dict(type=name, status='valid' if name else 'missing_sky', candidates=[])
    names = {1: 'rain', 2: 'rain_snow', 3: 'snow', 4: 'rain', 5: 'rain'}
    if code in names:
        return dict(type=names[code], status='valid', candidates=[])
    # 혼합 가중치는 음악 계약 미확정. 원래 현상을 유지하고 임의 확정하지 않음.
    candidates = {6: ['rain', 'snow_flurry'], 7: ['snow', 'cloudy']}.get(code, [])
    return dict(type=None, status='mapping_unresolved', candidates=candidates)


def music_weather(document, now=None, duration_minutes=180, config=None):
    now = now or datetime.now(KST)
    if now.tzinfo is None or not 0 < duration_minutes <= 184:
        raise ValueError('invalid_weather_window')
    now = now.astimezone(KST)
    config = config or {'observation_max_age_minutes':30, 'forecast_max_age_minutes':120,
                        'policy_status':'development_defaults'}
    end = now + timedelta(minutes=duration_minutes)
    # 서비스용 시간 구간 정의. RN1/SNO의 실제 누적 경계를 뜻하지 않음.
    target = now.replace(minute=0, second=0, microsecond=0)+timedelta(hours=1)
    required = []
    while target-timedelta(hours=1) < end:
        required.append(target.isoformat())
        target += timedelta(hours=1)
    by_target = {h['target_at']: h for h in document.get('forecast', [])}
    features = guidance_features(document, now, config)
    by_feature = {h['target_at']: h for h in features['forecast']}
    hours, missing, invalid, stale = [], [], [], []
    for target in required:
        hour = by_target.get(target)
        if hour is None:
            missing.append(target)
            continue
        feature = by_feature[target]
        weather_type = recommendation_type(hour.get('values', {}), feature['sky'])
        required_codes = ['PTY']
        if hour.get('values', {}).get('PTY', {}).get('value') == 0 and feature['sky']['sky_code'] is not None:
            required_codes.append('SKY')
        future_value = any(datetime.fromisoformat(hour['values'][c]['received_at']) > now
                           for c in required_codes if c in hour.get('values', {}) and hour['values'][c].get('received_at'))
        if weather_type['status'] != 'valid' or future_value:
            invalid.append(target)
        issued = datetime.fromisoformat(hour['issued_at'])
        if issued > now or now-issued > timedelta(minutes=config['forecast_max_age_minutes']):
            stale.append(target)
        hours.append(dict(hour, recommendation=weather_type, features=feature))
    observation = document.get('observation')
    observation_stale = True
    if observation:
        observed = datetime.fromisoformat(observation['target_at'])
        observation_stale = observed > now or now-observed > timedelta(minutes=config['observation_max_age_minutes'])
    identity = dict(nx=document['nx'], ny=document['ny'], observation=observation,
                    forecast=document.get('forecast', []), sky_context=document.get('sky_context', []),
                    type_policy=TYPE_POLICY, sky_policy=SKY_POLICY, settings=config)
    bundle = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return dict(schema_version=1, bundle_id=bundle, nx=document['nx'], ny=document['ny'],
                evaluated_at=now.isoformat(), requested_until=end.isoformat(),
                type_policy_version=TYPE_POLICY, settings_status=config['policy_status'],
                interval_policy='service_hour_ending_v1',
                observation=observation, observation_stale=observation_stale,
                current_features=features['current'], current_sky=features['current_sky'], sky_policy_version=SKY_POLICY,
                forecast=hours, required_targets=required,
                ready=not (missing or invalid or stale), missing_targets=missing,
                invalid_type_targets=invalid, stale_targets=stale,
                display_forecast=document.get('forecast', []))
