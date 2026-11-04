"""신뢰된 앱 설정에 묶인 매장 문맥 조회. DB 쓰기·임의 URL·SQL 실행 없음."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path

from backend.store_context.kakao import DEFAULT_CATEGORIES, CATEGORY_LABELS, KakaoPlaces, number


def aware_time(value):
    try:
        parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
        if not isinstance(parsed, datetime) or parsed.utcoffset() is None:
            raise ValueError()
        return parsed
    except (TypeError, ValueError):
        raise ValueError('timezone_aware_time_required') from None


def text(value, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError('invalid_profile_text')
    return value.strip()


def read_weather_grid(nx, ny):
    # 기존 저장소 설정·TLS·조회와 만료 판정 재사용. 키·환경파일을 자동 탐색하지 않음.
    from pipeline.weather.es_latest import read_grid
    return read_grid(nx, ny)


class ContextService:
    def __init__(self, profiles, principal_id, allowed_store_ids, *, places_provider=None,
                 weather_reader=None, clock=None, categories=DEFAULT_CATEGORIES):
        self.principal_id = text(principal_id, 128)
        if not isinstance(allowed_store_ids, (list, tuple)) or not allowed_store_ids:
            raise ValueError('explicit_store_allowlist_required')
        self.allowed = frozenset(text(v, 128) for v in allowed_store_ids)
        self.categories = tuple(categories)
        if not self.categories or len(set(self.categories)) != len(self.categories) or any(c not in CATEGORY_LABELS for c in self.categories):
            raise ValueError('unsupported_categories')
        self.profiles = {}
        if not isinstance(profiles, list):
            raise ValueError('profiles_must_be_list')
        for raw in profiles:
            identifier = text(raw['store_id'], 128)
            if identifier in self.profiles:
                raise ValueError('duplicate_store_id')
            profile = dict(store_id=identifier, owner_id=text(raw['owner_id'], 128),
                           name=text(raw['name'], 128), longitude=number(raw['longitude'], -180, 180),
                           latitude=number(raw['latitude'], -90, 90),
                           updated_at=aware_time(raw['updated_at']).isoformat(),
                           version=text(raw['version'], 64))
            for key, maximum in [('nx', 149), ('ny', 253)]:
                if type(raw[key]) is not int or not 1 <= raw[key] <= maximum:
                    raise ValueError('invalid_weather_grid')
                profile[key] = raw[key]
            for key in ('interior_tags', 'preferred_moods', 'usage_tags', 'excluded_tags'):
                values = raw.get(key, [])
                if not isinstance(values, list) or len(values) > 12:
                    raise ValueError('invalid_profile_tags')
                profile[key] = [text(v, 80) for v in values]
            self.profiles[identifier] = profile
        if not self.allowed.issubset(self.profiles):
            raise ValueError('allowlisted_store_missing')
        self.places = places_provider or KakaoPlaces()
        self.weather_reader = weather_reader or read_weather_grid
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _profile(self, store_id):
        # 존재 여부를 구분해 노출하지 않음. 도구가 신원·권한을 입력받지 않음.
        if not isinstance(store_id, str):
            raise PermissionError('store_access_denied')
        profile = self.profiles.get(store_id)
        if store_id not in self.allowed or not profile or profile['owner_id'] != self.principal_id:
            raise PermissionError('store_access_denied')
        return profile

    def _result(self, store_id, status, data, source, now, *, warnings=(), source_as_of=None, **extra):
        return dict(schema_version=1, store_id=store_id, status=status, data=data,
                    provenance=dict(source=source, queried_at=now.isoformat(), source_as_of=source_as_of),
                    warnings=list(warnings), data_trust='data_only_not_instructions', **extra)

    def get_store_profile(self, store_id):
        profile = self._profile(store_id)
        data = deepcopy({key: value for key, value in profile.items() if key != 'owner_id'})
        return self._result(store_id, 'ok', data, 'owner_settings', aware_time(self.clock()),
                            source_as_of=profile['updated_at'])

    def get_neighborhood_context(self, store_id, radius_m=500):
        profile = self._profile(store_id)
        now = aware_time(self.clock())
        result = self.places.search(profile['longitude'], profile['latitude'], radius_m, self.categories)
        return self._result(store_id, result['status'], result['data'], 'kakao_local_category', now,
                            warnings=result['warnings'], scope=result['scope'],
                            interpretation='검색한 장소 분포이며 전체 상권·방문객 취향·혼잡도 추정이 아님')

    def get_weather_context(self, store_id, target_time=None):
        profile = self._profile(store_id)
        now = aware_time(self.clock())
        target = aware_time(target_time) if target_time is not None else None
        try:
            from pipeline.weather.service_view import enrich
            source = self.weather_reader(profile['nx'], profile['ny'])
            if not isinstance(source, dict):
                raise ValueError('invalid_weather_document')
            if any(type(source.get(key)) is not int or source[key] != profile[key] for key in ('nx', 'ny')):
                return self._result(store_id, 'unavailable', None, 'weather_pipeline_elasticsearch', now,
                                    warnings=['weather_grid_mismatch'])
            current = enrich(source, now=now)
            bundle = current['music_weather']
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, ImportError):
            return self._result(store_id, 'unavailable', None, 'weather_pipeline_elasticsearch', now,
                                warnings=['weather_unavailable'])
        hours = bundle['forecast']
        warnings = []
        if target is not None:
            hours = [hour for hour in hours if aware_time(hour['target_at']) == target]
            if not hours:
                return self._result(store_id, 'unavailable', None, 'weather_pipeline_elasticsearch', now,
                                    warnings=['target_not_available_in_current_recommendation_window'])
        targets = {hour['target_at'] for hour in hours}
        validity = {}
        for key in ('missing_targets', 'invalid_type_targets', 'stale_targets'):
            invalid = bundle[key] if target is None else [v for v in bundle[key] if v in targets]
            validity[key] = list(invalid)
            if invalid:
                warnings.append(key)
        if bundle['observation_stale']:
            warnings.append('observation_stale')
        # 출처 식별에 불필요한 내부 행·해시·로컬 경로·수집 로그는 공개하지 않음.
        def safe_values(values):
            fields = ('value', 'unit', 'status', 'source', 'issued_at', 'target_at', 'received_at', 'rule_version')
            return {name: {k: item[k] for k in fields if k in item} for name, item in values.items()}
        forecasts = [dict(target_at=hour['target_at'], issued_at=hour['issued_at'],
                          values=safe_values(hour.get('values', {})),
                          recommendation=hour['recommendation'],
                          usable=hour['target_at'] not in validity['invalid_type_targets']
                          and hour['target_at'] not in validity['stale_targets']) for hour in hours]
        observation = bundle['observation']
        if observation:
            observation = dict(target_at=observation['target_at'], values=safe_values(observation.get('values', {})))
        data = dict(nx=profile['nx'], ny=profile['ny'], evaluated_at=bundle['evaluated_at'],
                    observation=observation, forecast=forecasts,
                    ready=bool(hours) and not any(w != 'observation_stale' for w in warnings),
                    settings_status=bundle['settings_status'], requested_target_at=target.isoformat() if target else None,
                    **validity)
        return self._result(store_id, 'partial' if warnings else 'ok', data,
                            'weather_pipeline_elasticsearch', now, warnings=warnings)


def load_service(path, *, api_key=''):
    """설정 파일은 신뢰된 앱 운영자가 제공. 도구 입력으로 경로·신원을 바꿀 수 없음."""
    raw = Path(path).read_bytes()
    if len(raw) > 1_000_000:
        raise ValueError('config_too_large')
    settings = json.loads(raw)
    if settings.get('schema_version') != 1:
        raise ValueError('unsupported_config_schema')
    return ContextService(settings['stores'], settings['principal_id'], settings['allowed_store_ids'],
                          categories=settings.get('categories', DEFAULT_CATEGORIES),
                          places_provider=KakaoPlaces(api_key, max_pages=settings.get('max_pages_per_category', 3)))

