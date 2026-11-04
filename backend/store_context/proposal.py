"""기존 추천 선택 코드에 맞춘 조건 제안 규격. 곡 선정·자동 적용은 수행하지 않음."""
from copy import deepcopy
import json

from backend.recommendation.errors import DomainError
from backend.recommendation.inputs import options as normalize_options
from backend.recommendation.policy import GENRES, THEMES, OPTIONS

CONDITION_FIELDS = {'vocal_option', 'tempo_preference', 'selected_theme_codes', 'selected_genre_codes'}
PROPOSAL_FIELDS = {'schema_version', 'store_id', 'option_version', 'conditions', 'rationale', 'source_refs'}


def available_sources(bundle):
    """조회된 자료 중 제안 근거로 참조 가능한 출처. 설명의 사실성까지 증명하지 않음."""
    sources = []
    for name, result in bundle['contexts'].items():
        data = result.get('data')
        if result.get('status') == 'unavailable' or not isinstance(data, dict):
            continue
        if name == 'get_store_profile' and result['status'] == 'ok':
            sources.append(name)
        elif name == 'get_neighborhood_context' and isinstance(data.get('categories'), list) and any(
                isinstance(category, dict) and type(category.get('observed_count')) is int
                and category['observed_count'] >= 0 for category in data.get('categories', [])):
            sources.append(name)
        elif name == 'get_weather_context' and (
                data.get('observation_usable') is True or (isinstance(data.get('forecast'), list) and any(
                    isinstance(hour, dict) and hour.get('usable') is True
                    for hour in data['forecast']))):
            sources.append(name)
    return sorted(sources)


def response_schema(bundle):
    """LLM 담당자가 구조화 출력 설정에 사용할 JSON Schema."""
    return {
        'type': 'object', 'additionalProperties': False,
        'required': sorted(PROPOSAL_FIELDS),
        'properties': {
            'schema_version': {'type': 'integer', 'enum': [1]},
            'store_id': {'type': 'string', 'enum': [bundle['store_id']]},
            'option_version': {'type': 'string', 'enum': [OPTIONS]},
            'conditions': {
                'type': 'object', 'additionalProperties': False,
                'properties': {
                    'vocal_option': {'type': 'string', 'enum': ['any', 'instrumental_only']},
                    'tempo_preference': {'type': 'string', 'enum': ['auto', 'slow', 'fast']},
                    'selected_theme_codes': {
                        'type': 'array', 'items': {'type': 'string', 'enum': sorted(THEMES)},
                        'uniqueItems': True, 'maxItems': len(THEMES)},
                    'selected_genre_codes': {
                        'type': 'array', 'items': {'type': 'string', 'enum': sorted(GENRES)},
                        'uniqueItems': True, 'maxItems': len(GENRES)},
                },
            },
            'rationale': {'type': 'string', 'minLength': 1, 'maxLength': 2000},
            'source_refs': {
                'type': 'array', 'items': {'type': 'string', 'enum': available_sources(bundle)},
                'uniqueItems': True, 'minItems': 1, 'maxItems': 3},
        },
    }


def validate_proposal(proposal, bundle):
    """형식·매장·기존 선택 코드·조회 출처를 검사해 정규화한 조건 제안 반환."""
    def require(condition):
        if not condition:
            raise ValueError('condition_proposal_invalid')

    require(type(proposal) is dict and set(proposal) == PROPOSAL_FIELDS)
    require(type(proposal['schema_version']) is int and proposal['schema_version'] == 1)
    require(proposal['store_id'] == bundle['store_id'] and proposal['option_version'] == OPTIONS)
    conditions = proposal['conditions']
    require(type(conditions) is dict and set(conditions) <= CONDITION_FIELDS)
    for key, maximum in [('selected_theme_codes', len(THEMES)), ('selected_genre_codes', len(GENRES))]:
        if key in conditions:
            values = conditions[key]
            require(type(values) is list and len(values) <= maximum
                    and all(type(value) is str for value in values))
            require(len(values) == len(set(values)))
    try:
        normalized = normalize_options(conditions)
    except DomainError:
        raise ValueError('condition_proposal_invalid') from None
    rationale, refs = proposal['rationale'], proposal['source_refs']
    require(type(rationale) is str and bool(rationale.strip()) and len(rationale) <= 2000)
    require(type(refs) is list and 1 <= len(refs) <= 3 and all(type(ref) is str for ref in refs))
    require(len(refs) == len(set(refs)) and set(refs) <= set(available_sources(bundle)))
    try:
        require(len(json.dumps(proposal, ensure_ascii=False, allow_nan=False)) <= 20_000)
    except (TypeError, ValueError):
        raise ValueError('condition_proposal_invalid') from None
    return {**proposal, 'conditions': {key: deepcopy(normalized[key]) for key in conditions},
            'rationale': rationale.strip(), 'source_refs': sorted(refs)}
