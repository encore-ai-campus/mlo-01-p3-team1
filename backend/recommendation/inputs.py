from .errors import require
from .policy import GENRES, THEMES, OPTIONS

DEFAULTS = {'vocal_option':'any', 'tempo_preference':'auto', 'selected_theme_codes':[], 'selected_genre_codes':[], 'option_version':OPTIONS}


def shape(data, allowed, required=()):
    require(type(data) is dict)
    require(not any('language' in k.lower() or 'country' in k.lower() for k in data),
            'OPTION_NOT_SUPPORTED','국가·언어 선택은 제공하지 않아요.',400)
    require(not set(data)-set(allowed),fields=sorted(set(data)-set(allowed)))
    require(set(required) <= set(data),fields=sorted(set(required)-set(data)))
    return dict(data)


def strict_int(value):
    require(type(value) is int and value >= 0)
    return value


def strings(value):
    require(type(value) is list and all(type(x) is str and x.strip() for x in value))
    return sorted(set(value))


def options(data, inherited=None):
    result = dict(DEFAULTS if inherited is None else inherited)
    for key in DEFAULTS:
        if key in data: result[key] = data[key]
    for key, choices in [('vocal_option',('any','instrumental_only')),('tempo_preference',('auto','slow','fast'))]:
        require(type(result[key]) is str)
        require(result[key] in choices,'OPTION_INVALID','선택 항목을 확인해 주세요.',400)
    for key, choices in [('selected_theme_codes',THEMES),('selected_genre_codes',GENRES)]:
        result[key] = strings(result[key])
        require(set(result[key]) <= choices.keys(),'OPTION_INVALID','선택 코드를 확인해 주세요.',400)
    require(type(result['option_version']) is str and bool(result['option_version']))
    return result
