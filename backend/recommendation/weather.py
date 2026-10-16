from datetime import datetime, timedelta
from fractions import Fraction
from django.conf import settings
from django.utils.module_loading import import_string
from .errors import require
from .policy import TARGET, profile


def instant(value):
    require(type(value) is str, 'FORECAST_UNAVAILABLE', '예보 시각 형식을 확인할 수 없어요.', 503)
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(dt.tzinfo is not None, 'FORECAST_UNAVAILABLE', '예보 시각에 시간대가 없어요.', 503)
    return dt


def validate(bundle, now, duration=TARGET):
    try:
        start = instant(bundle['as_of'])
        require(instant(bundle['valid_until']) > now, 'FORECAST_UNAVAILABLE', '예보가 만료됐어요.', 503)
        end = start + timedelta(milliseconds=duration)
        cursor, segments = start, []
        for row in sorted(bundle['segments'], key=lambda x: instant(x['start_at'])):
            left, right = max(start, instant(row['start_at'])), min(end, instant(row['end_at']))
            if right <= left: continue
            require(left == cursor and row['status'] == 'valid', 'FORECAST_UNAVAILABLE', '예보 구간이 누락되거나 겹쳤어요.', 503)
            require(instant(row['issued_at']) <= start and instant(row['received_at']) <= start,
                    'FORECAST_UNAVAILABLE', '요청 이후에 도착한 예보예요.', 503)
            require(type(row['pty']) is int and row['pty'] in (0,1,2,3,4,5,6,7),
                    'FORECAST_UNAVAILABLE','강수 예보를 확인할 수 없어요.',503)
            if row['pty'] == 0:
                require(type(row['sky']) is int and row['sky'] in (1,3,4),
                        'FORECAST_UNAVAILABLE','하늘 예보를 확인할 수 없어요.',503)
            delta = right-left
            microseconds = (delta.days*86400 + delta.seconds)*1_000_000 + delta.microseconds
            segments.append({**row, 'overlap_ms': Fraction(microseconds, 1000)})
            cursor = right
        require(cursor == end, 'FORECAST_UNAVAILABLE', '선곡 구간의 예보가 부족해요.', 503)
        return segments
    except (KeyError, ValueError, TypeError, OverflowError):
        require(False, 'FORECAST_UNAVAILABLE', '예보 형식을 확인할 수 없어요.', 503)


def current_profile(bundle, segments, now):
    try:
        current = bundle.get('current') or {}
        require(current.get('status','valid') == 'valid', 'FORECAST_UNAVAILABLE', '현재 날씨를 확인할 수 없어요.', 503)
        as_of=instant(bundle['as_of'])
        require(as_of <= now,'FORECAST_UNAVAILABLE','미래 시점의 날씨 자료예요.',503)
        observed = instant(current['observed_at'])
        require(observed <= now and observed >= as_of-timedelta(hours=1),
                'FORECAST_UNAVAILABLE','현재 관측이 유효하지 않아요.',503)
        if 'sky_state' in current:
            # A's current-hour SKY context is separate from hour-ending future segments.
            sky=current.get('sky') if instant(current['sky_valid_from'])<=now<instant(current['sky_valid_until']) else None
        else:
            sky = next((row['sky'] for row in segments if instant(row['start_at']) <= now < instant(row['end_at'])),None)
        return profile(current['pty'], sky)
    except (KeyError,ValueError,TypeError,OverflowError):
        require(False,'FORECAST_UNAVAILABLE','현재 날씨 형식을 확인할 수 없어요.',503)


def obtain(region_id, now):
    if settings.WEATHER_PROVIDER:
        bundle = import_string(settings.WEATHER_PROVIDER)(region_id, now)
    else:
        from backend.weather.regions import demo_region
        selected=demo_region(region_id) if settings.LOCAL_DEMO and region_id!='demo-region' else None
        require(settings.LOCAL_DEMO and (region_id == 'demo-region' or selected is not None), 'FORECAST_UNAVAILABLE', '날씨 서비스 연결을 기다리고 있어요.', 503)
        def iso(dt): return dt.isoformat().replace('+00:00','Z')
        bundle = {'region_id': region_id, 'region_name': selected['address'] if selected else '성수동 · 고정 검증 자료',
                  'nx':selected['nx'] if selected else 61,'ny':selected['ny'] if selected else 126,
                  'as_of': iso(now), 'valid_until': iso(now+timedelta(minutes=5)), 'is_test': True,
                  'current': {'pty':0,'sky':None,'temperature':22,'observed_at':iso(now)},
                  'bundle_version': 'demo-weather-v1', 'segments': [
                      {'start_at':iso(now), 'end_at':iso(now+timedelta(hours=6)),
                       'issued_at':iso(now-timedelta(minutes=10)), 'received_at':iso(now-timedelta(minutes=5)),
                       'pty':0, 'sky':1, 'status':'valid', 'temperature':22}]}
    require(bundle['region_id'] == region_id, 'FORECAST_UNAVAILABLE', '예보 지역이 다릅니다.', 503)
    validate(bundle, now)
    return bundle
