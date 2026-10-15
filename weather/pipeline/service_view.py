"""저장소 공통 특징을 구성하고 조회 시 만료/요청 범위를 재평가."""
import json
from datetime import datetime
from importlib.resources import files
from weather.pipeline.common import KST
from weather.pipeline.handoff import music_weather
from weather.weather_features import guidance_features, RULE_VERSION

def config():
    return json.loads(files('weather.pipeline').joinpath('runtime_config.json').read_text(encoding='utf-8'))

def enrich(document, now=None):
    now=now or datetime.now(KST)
    settings=config()
    result=dict(document)
    result['guidance']=guidance_features(document,now,settings)
    result['music_weather']=music_weather(document,now,config=settings)
    result['evaluated_at']=now.isoformat()
    result['feature_rule_version']=RULE_VERSION
    return result
