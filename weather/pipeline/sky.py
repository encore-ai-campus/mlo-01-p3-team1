"""같은 격자·대상 시각의 SKY와 KIM을 결합. 관측 구름값 생성 아님."""
import math
from datetime import datetime, timedelta
from weather.weather_normalize import KST

POLICY = 'sky_state_v1'
BASE = {1: ('clear', '맑음'), 3: ('cloudy', '구름 많음'), 4: ('overcast', '흐림')}


def usable(item, unit, target_at, now, max_age_minutes):
    if not item or item.get('status') != 'valid' or item.get('unit') != unit:
        return False
    value = item.get('value')
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return False
    if item.get('target_at') != target_at:
        return False
    if now:
        try:
            for key in ('issued_at', 'received_at'):
                stamp = datetime.fromisoformat(item.get(key, ''))
                if stamp.tzinfo is None or stamp > now:
                    return False
            if now - datetime.fromisoformat(item['issued_at']) > timedelta(minutes=max_age_minutes):
                return False
        except (ValueError, TypeError):
            return False
    return True


def cloud_state(percent):
    if percent <= 10:
        return 'nearly_clear', '구름 거의 없음'
    if percent <= 50:
        return 'few_clouds', '구름 조금'
    if percent < 85:
        return 'cloudy', '구름 많음'
    if percent < 95:
        return 'overcast', '흐림'
    return 'covered', '구름으로 거의 덮임'


def classify_sky(sky, cloud, target_at, now=None, config=None):
    config = config or {}
    sky_ok = usable(sky, 'code', target_at, now, config.get('forecast_max_age_minutes', 120))
    sky_ok = sky_ok and sky['value'] in BASE
    cloud_ok = usable(cloud, '%', target_at, now, config.get('kim_max_age_minutes', 720))
    cloud_ok = cloud_ok and 0 <= cloud['value'] <= 100
    state, label, status = None, '판단 불가', 'unavailable'
    if sky_ok:
        state, label = BASE[sky['value']]
        status = 'sky_only'
        if cloud_ok:
            percent = cloud['value']
            compatible = ((sky['value'] == 1 and percent <= 50)
                          or (sky['value'] == 3 and 50 < percent < 85)
                          or (sky['value'] == 4 and percent >= 85))
            if compatible:
                state, label = cloud_state(percent)
                status = 'agree'
            else:
                status = 'conflict'
    elif cloud_ok:
        state, label = cloud_state(cloud['value'])
        status = 'kim_only'
    return dict(rule_version=POLICY, state=state, label=label, status=status,
                basis='forecast_estimate', target_at=target_at,
                sky_code=sky['value'] if sky_ok else None,
                cloud_percent=cloud['value'] if cloud_ok else None,
                inputs={'SKY': sky or None, 'TCDC': cloud or None})


def current_sky(document, now=None, config=None):
    now = (now or datetime.now(KST)).astimezone(KST)
    target = now.replace(minute=0, second=0, microsecond=0).isoformat()
    # 현재 시간의 슬롯만 사용. 가까운 다른 시각을 몰래 대체하지 않음.
    candidates = list(document.get('forecast', [])) + list(document.get('sky_context', []))
    matching = [h for h in candidates if h['target_at'] == target]
    sky = cloud = None
    for hour in matching:
        item = hour.get('values', {}).get('SKY')
        if item and (sky is None or item.get('issued_at', '') > sky.get('issued_at', '')):
            sky = item
        item = hour.get('supplements', {}).get('values', {}).get('TCDC')
        if item and (cloud is None or item.get('issued_at', '') > cloud.get('issued_at', '')):
            cloud = item
    result = classify_sky(sky, cloud, target, now, config)
    result['evaluated_at'] = now.isoformat()
    result['display_until'] = (now.replace(minute=0,second=0,microsecond=0)+timedelta(hours=1)).isoformat()
    return result
