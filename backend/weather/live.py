"""실제 전국 격자 캐시 → 지역별 표시/추천. HTTP 경로에서 외부 호출 없음."""
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from backend.recommendation.errors import DomainError, require
from backend.recommendation.weather import validate, current_profile
from pipeline.weather.live_cache import read
from pipeline.weather.service_view import config
from pipeline.weather.weather_normalize import normalize_value
from .adapter import build
from .regions import demo_region


@lru_cache(maxsize=2)
def cached(path, modified, size):
    return read(path)


def document(data, nx, ny):
    require(type(nx) is int and type(ny) is int and 1 <= nx <= 149 and 1 <= ny <= 253,
            'FORECAST_UNAVAILABLE', '날씨 격자를 확인할 수 없습니다.', 503)
    position = (ny - 1) * 149 + nx - 1
    slots = list(data['slots'].values())

    def values(selected):
        result = {}
        for slot in selected:
            if len(slot['values']) != 37697:
                raise ValueError('invalid_grid_shape')
            code = slot['category']
            result[code] = {**normalize_value(code, slot['values'][position], slot['source'],
                'observation' if slot['source'] == 'odam' else 'forecast'),
                **{key: slot[key] for key in ('issued_at', 'target_at', 'received_at', 'source_hash', 'source')}}
        return result

    observations = [slot for slot in slots if slot['source'] == 'odam']
    rounds = sorted({slot['target_at'] for slot in observations}, reverse=True)
    observation = None
    for target in rounds:
        selected = [slot for slot in observations if slot['target_at'] == target]
        if {'PTY', 'T1H'} <= {slot['category'] for slot in selected}:
            observation = {'target_at': target, 'values': values(selected)}
            break
    forecasts = [slot for slot in slots if slot['source'] == 'vsrt']
    issues = sorted({slot['issued_at'] for slot in forecasts}, reverse=True)
    forecast = []
    for issued in issues:
        selected = [slot for slot in forecasts if slot['issued_at'] == issued]
        targets = sorted({slot['target_at'] for slot in selected})
        complete = [target for target in targets if {'PTY', 'SKY', 'T1H'} <=
                    {slot['category'] for slot in selected if slot['target_at'] == target}]
        if len(complete) == 6:
            forecast = [{'issued_at': issued, 'target_at': target,
                         'values': values([slot for slot in selected if slot['target_at'] == target])}
                        for target in complete]
            break
    context = []
    for target in sorted({slot['target_at'] for slot in forecasts if slot['category'] == 'SKY'}):
        sky = max((slot for slot in forecasts if slot['category'] == 'SKY' and slot['target_at'] == target),
                  key=lambda slot: slot['issued_at'])
        context.append({'target_at': target, 'values': values([sky])})
    return {'nx': nx, 'ny': ny, 'observation': observation, 'forecast': forecast,
            'sky_context': context, 'source': 'KMA_API_HUB', 'is_test': False,
            'available_categories': ['PTY', 'SKY', 'T1H'], 'supplements_pending': True}


def display(region_id, now):
    require(settings.LOCAL_DEMO, 'FORECAST_UNAVAILABLE', '운영 날씨 저장소를 설정해 주세요.', 503)
    region = demo_region(region_id)
    require(region is not None, 'REGION_NOT_FOUND', '지역을 찾을 수 없습니다.', 404)
    try:
        path = Path(settings.KMA_LOCAL_CACHE_PATH)
        stat = path.stat()
        data = cached(str(path), stat.st_mtime_ns, stat.st_size)
        source = document(data, region['nx'], region['ny'])
        require(source['observation'] is not None,
                'FORECAST_UNAVAILABLE', '기상청 실황을 수집 중입니다.', 503)
        bundle = build(region, source, now, config())
        bundle.update(source='KMA_API_HUB', collected_at=data['updated_at'],
                      forecast_issued_at=source['forecast'][0]['issued_at'] if source['forecast'] else None)
        try:
            bundle['weather_code'] = current_profile(bundle, validate(bundle, now), now)
            bundle['recommendation_ready'] = True
        except DomainError as error:
            bundle['recommendation_ready'] = False
            bundle['recommendation_error'] = error.code
        return bundle
    except DomainError:
        raise
    except Exception:
        raise DomainError('FORECAST_UNAVAILABLE', '실제 날씨 수집 상태를 확인해 주세요.', 503) from None


def obtain(region_id, now):
    bundle = display(region_id, now)
    require(bundle['recommendation_ready'], 'FORECAST_UNAVAILABLE',
            '기상청 관측·예보가 누락되거나 만료됐습니다.', 503)
    return bundle
