"""NOAA 간이 일출·일몰 계산. 격자 대표점 기준, 추가 API 없음."""
import calendar
import json
import math
from datetime import datetime, timedelta, timezone
from importlib.resources import files
from pipeline.weather.weather_normalize import KST

POLICY = 'daylight_noaa_v1'
_mapping = json.loads(files('pipeline.weather').joinpath('mapping.json').read_text(encoding='utf-8'))
POINTS = {(g['nx'],g['ny']):(g['lat'],g['lon']) for g in _mapping['grids']+_mapping.get('admin_grids',[])}


def daylight_at(at, latitude, longitude):
    local = at.astimezone(KST)
    result = dict(rule_version=POLICY,state='unknown',is_day=None,sunrise_at=None,sunset_at=None,
                  date=local.date().isoformat(),point_basis='weather_grid_representative',estimated=True)
    if latitude is None or longitude is None: return result
    if not (math.isfinite(latitude) and math.isfinite(longitude) and -89.99<latitude<89.99 and -180<=longitude<=180):
        return result
    days=366 if calendar.isleap(local.year) else 365
    gamma=2*math.pi/days*(local.timetuple().tm_yday-1)
    eqtime=229.18*(0.000075+0.001868*math.cos(gamma)-0.032077*math.sin(gamma)
                   -0.014615*math.cos(2*gamma)-0.040849*math.sin(2*gamma))
    decl=(0.006918-0.399912*math.cos(gamma)+0.070257*math.sin(gamma)
          -0.006758*math.cos(2*gamma)+0.000907*math.sin(2*gamma)
          -0.002697*math.cos(3*gamma)+0.00148*math.sin(3*gamma))
    lat=math.radians(latitude)
    angle=math.cos(math.radians(90.833))/(math.cos(lat)*math.cos(decl))-math.tan(lat)*math.tan(decl)
    if abs(angle)>1:
        result.update(state='day' if angle<0 else 'night',is_day=angle<0)
        return result
    hour_angle=math.degrees(math.acos(angle))
    base=datetime(local.year,local.month,local.day,tzinfo=timezone.utc)
    sunrise=(base+timedelta(minutes=720-4*(longitude+hour_angle)-eqtime)).astimezone(KST)
    sunset=(base+timedelta(minutes=720-4*(longitude-hour_angle)-eqtime)).astimezone(KST)
    is_day=sunrise<=local<sunset
    result.update(state='day' if is_day else 'night',is_day=is_day,
                  sunrise_at=sunrise.isoformat(),sunset_at=sunset.isoformat())
    return result


def grid_daylight(nx,ny,at):
    lat,lon=POINTS.get((nx,ny),(None,None))
    return daylight_at(at,lat,lon)
