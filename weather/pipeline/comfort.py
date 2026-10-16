"""체감온도 추정과 한국 월별 서비스 표현. 공식 위험 등급 아님."""
import math

POLICY = 'comfort_v1'
# 추움 / 선선함 / 온화함 / 더움. 평년 관측 비교가 아닌 서비스 기준.
THRESHOLDS = {'봄':[10,18,26], '여름':[18,24,30], '가을':[10,18,26], '겨울':[5,10,20]}


def season_for(month):
    if month in (3,4,5): return '봄'
    if month in (6,7,8): return '여름'
    if month in (9,10,11): return '가을'
    return '겨울'


def wet_bulb(temperature, humidity):
    # Stull(2011). 따뜻한 영역만 적용해 저온·건조 조건 제외.
    return (temperature * math.atan(0.151977 * math.sqrt(humidity+8.313659))
            + math.atan(temperature+humidity) - math.atan(humidity-1.67633)
            + 0.00391838 * humidity**1.5 * math.atan(0.023101*humidity) - 4.686035)


def comfort(temperature, humidity, wind_mps, month, config=None):
    config = config or {}
    season = season_for(month)
    result = dict(rule_version=POLICY, season=season, month=month, feels_like_c=None,
                  method=None, status='missing_temperature', classification_basis=None,
                  temperature_level=None, humidity_level=None,
                  thresholds_c=config.get('seasonal_thresholds_c',THRESHOLDS)[season],
                  inputs={'temperature_c':temperature,'humidity_percent':humidity,'wind_mps':wind_mps})
    if humidity is not None:
        result['humidity_level']='건조' if humidity<40 else ('보통' if humidity<70 else '습함')
    if temperature is None: return result
    estimate = None
    status = 'outside_formula_conditions'
    if 5 <= month <= 9:
        if humidity is None:
            status = 'missing_humidity'
        elif 20 <= temperature <= 50 and 5 <= humidity <= 99:
            tw = wet_bulb(temperature,humidity)
            estimate=(-0.2442 + 0.55399*tw + 0.45535*temperature
                      - 0.0022*tw**2 + 0.00278*tw*temperature + 3.0)
            result['method']='kma_summer_stull_estimate'
            status='estimated'
    else:
        if wind_mps is None:
            status='missing_wind'
        elif temperature <= 10 and wind_mps >= 1.3:
            wind_kmh = wind_mps * 3.6
            estimate=13.12 + 0.6215*temperature - 11.37*wind_kmh**0.16 + 0.3965*wind_kmh**0.16*temperature
            result['method']='kma_winter_wsd_estimate'
            result['wind_basis']='source_wsd_averaging_unverified'
            status='estimated'
    score = estimate if estimate is not None else temperature
    labels=['추움','선선함','온화함','더움']
    level=labels[-1]
    for limit,label in zip(result['thresholds_c'],labels):
        if score<limit:
            level=label;break
    result.update(feels_like_c=round(estimate,1) if estimate is not None else None,
                  status=status,classification_basis='feels_like' if estimate is not None else 'temperature',
                  temperature_level=level)
    return result
