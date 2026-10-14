"""항목별 단위·결측·유효 범위를 정규화. 실제 0과 결측 구분."""
import math
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
UTC = timezone.utc
UNITS = {'T1H': 'degC', 'REH': '%', 'RN1': 'mm', 'WSD': 'm/s',
         'UUU': 'm/s', 'VVV': 'm/s', 'VEC': 'degree', 'PTY': 'code',
         'SKY': 'code', 'POP': '%', 'TCDC': '%', 'SNO': 'cm', 'LGT': 'kA'}
LIMITS = {'REH': (0, 100), 'POP': (0, 100), 'VEC': (0, 360), 'TCDC': (0, 100), 'LGT': (0, 100)}


def korea_time(stamp, source_zone):
    fmt = '%Y%m%d%H%M' if len(stamp) == 12 else '%Y%m%d%H'
    parsed = datetime.strptime(stamp, fmt).replace(tzinfo=source_zone)
    return parsed.astimezone(KST).isoformat()


def normalize_value(category, raw, source, kind, sno_encoding=None):
    result = {'raw': raw, 'value': None, 'unit': None, 'status': 'invalid_value'}
    try:
        number = float(raw)
    except (TypeError, ValueError):
        return result
    if not math.isfinite(number):
        return result
    if source in ('odam', 'vsrt', 'shrt') and (number == -99 or number <= -900 or number >= 900):
        result['status'] = 'missing'
        return result
    # SNO는 가까운 예보와 연장기간의 숫자 의미가 다릅니다.
    if category == 'SNO':
        if source != 'shrt' or kind != 'forecast' or sno_encoding not in ('amount_cm', 'extended_code'):
            result['status'] = 'encoding_required'
            return result
        result['encoding'] = sno_encoding
        if sno_encoding == 'extended_code':
            result['unit'] = 'code'
            if number not in (0, 1, 2):
                result['status'] = 'invalid_code'
                return result
            result.update(value=int(number), status='valid')
            return result
    if category == 'TCDC':
        if source != 'KIMG' or kind != 'forecast':
            result['status'] = 'unsupported_source'
            return result
        result.update(unit='%', raw_unit='fraction')
        if not 0 <= number <= 1:
            result['status'] = 'out_of_range'
            return result
        result.update(value=round(number * 100, 8), status='valid')
        return result
    if category not in UNITS:
        result['status'] = 'unit_unverified'
        return result
    result['unit'] = UNITS[category]
    if category in LIMITS:
        low, high = LIMITS[category]
        if not low <= number <= high:
            result['status'] = 'out_of_range'
            return result
    if category in ('RN1', 'WSD', 'SNO') and number < 0:
        result['status'] = 'out_of_range'
        return result
    if category in ('PTY', 'SKY'):
        if category == 'SKY':
            allowed = {1, 3, 4}
        elif source == 'vsrt' and kind == 'forecast':
            # 기상청 260928 활용가이드: 초단기 PTY=4는 소나기.
            allowed = {0, 1, 2, 3, 4, 5, 6, 7}
        elif source == 'shrt' and kind == 'forecast':
            allowed = {0, 1, 2, 3, 4}
        elif source == 'odam' and kind == 'observation':
            allowed = {0, 1, 2, 3, 5, 6, 7}
        else:
            result['status'] = 'unsupported_source'
            return result
        if number not in allowed:
            result['status'] = 'invalid_code'
            return result
        number = int(number)
    if category == 'LGT':
        if source != 'vsrt' or kind != 'forecast':
            result['status'] = 'unsupported_source'
            return result
        result['unit_note'] = 'Guide table: kA; density description: kA/km2. No density conversion applied.'
    result['value'] = number
    result['status'] = 'valid'
    if category in ('RN1', 'SNO'):
        result['accumulation_hours'] = 1
        result['window_status'] = 'boundary_unverified'
    return result
