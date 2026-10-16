"""Configuration-driven service commands. No shell, credential output or implicit writes."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from pipeline.environment import read

KEYS={'COMMON_PYTHON','ADS_PYTHON','WEATHER_PYTHON','NODE_BINARY','API_BIND','ADS_BIND','WEB_BIND','WEB_PORT'}


def cross_configuration():
    def values(path):
        result=read(path)
        result.update(os.environ)
        return result
    common=values(ROOT/'backend/.env');weather=values(ROOT/'pipeline/weather/.env')
    ads=values(ROOT/'ad-server/backend/.env');front=values(ROOT/'frontend/.env.local')
    checks={}
    for name,env,required in [('common',common,['DJANGO_SECRET_KEY','PGHOST','PGDATABASE','PGUSER']),
                             ('weather',weather,['KMA_API_KEY','KAFKA_BOOTSTRAP','KAFKA_TOPIC','ES_URL','WEATHER_INDEX','SPARK_MASTER','CHECKPOINT_PATH']),
                             ('ads',ads,['DJANGO_SECRET_KEY','POSTGRES_HOST','POSTGRES_DB','POSTGRES_USER','ADS_MONGODB_URI','ADS_MONGODB_DATABASE','ADS_COMMON_API_URL','ADS_INTERNAL_SECRET']),
                             ('frontend',front,['VITE_RECOMMENDATION_API_TARGET','VITE_ADS_API_TARGET'])]:
        for key in required:checks[name+'.'+key]=bool(env.get(key) or os.environ.get(key))
    checks['shared_ads_secret_matches']=bool(common.get('ADS_INTERNAL_SECRET')) and common.get('ADS_INTERNAL_SECRET')==ads.get('ADS_INTERNAL_SECRET')
    for key in ('ES_URL','WEATHER_INDEX'):
        checks['weather_shared_'+key]=bool(common.get(key)) and common.get(key)==weather.get(key)
    checks['production_modes_match']=(common.get('C_LOCAL_DEMO','0')=='0' and ads.get('ADS_IS_TEST')=='0' and front.get('VITE_C_DEMO','0')=='0')
    if common.get('WEATHER_MAPPING_DSN') or weather.get('WEATHER_MAPPING_DSN'):
        checks['mapping_target_matches']=bool(common.get('WEATHER_MAPPING_DSN')) and common.get('WEATHER_MAPPING_DSN')==weather.get('WEATHER_MAPPING_DSN')
    else:
        checks['mapping_target_matches']=(all(common.get(k)==weather.get(k) and bool(common.get(k)) for k in ('PGHOST','PGDATABASE','PGUSER'))
                                          and common.get('PGPORT','5432')==weather.get('PGPORT','5432'))
    return checks


def plans(config, action, connect=False, apply=False, music=False, allow_pending_music=False):
    win=os.name=='nt';suffix=Path('Scripts/python.exe') if win else Path('bin/python')
    common=config.get('COMMON_PYTHON',str(ROOT/'.venv'/suffix))
    ads=config.get('ADS_PYTHON',str(ROOT/'ad-server/backend/.venv'/suffix))
    weather=config.get('WEATHER_PYTHON',common)
    manage=[common,str(ROOT/'backend/manage.py')]
    ads_manage=[ads,str(ROOT/'ad-server/backend/manage.py')]
    if action=='prepare':
        return {'common':(manage+['prepare_runtime','--streams']+(['--music'] if music else [])+(['--apply'] if apply else []),ROOT),
                'weather':([weather,'-m','pipeline.weather.prepare_store']+(['--apply'] if apply else []),ROOT),
                'ads':(ads_manage+['prepare_ads_runtime']+(['--apply'] if apply else []),ROOT/'ad-server/backend')}
    if action=='check':
        return {'common':(manage+['check_runtime']+(['--connect'] if connect else [])+(['--allow-pending-music'] if allow_pending_music else []),ROOT),
                'ads':(ads_manage+(['check_ads_runtime','--database'] if connect else ['check_ads_configuration']),ROOT/'ad-server/backend')}
    return {
        'common-api':(manage+['runserver',config.get('API_BIND','127.0.0.1:8001'),'--noreload'],ROOT),
        'common-worker':(manage+['run_recommendations'],ROOT),
        'feedback-relay':(manage+['relay_feedback','--watch'],ROOT),
        'feedback-consumer':([common,'-m','pipeline.feedback.process'],ROOT),
        'weather-collector':([weather,'-m','pipeline.weather.run_collector'],ROOT),
        'weather-spark':([weather,'-m','pipeline.weather.submit_spark'],ROOT),
        'ads-api':(ads_manage+['runserver',config.get('ADS_BIND','127.0.0.1:8000'),'--noreload'],ROOT/'ad-server/backend'),
        'ads-workers':(ads_manage+['run_ads_workers','--watch'],ROOT/'ad-server/backend'),
        'frontend':([config.get('NODE_BINARY','node'),'node_modules/vite/bin/vite.js','--host',config.get('WEB_BIND','127.0.0.1'),'--port',config.get('WEB_PORT','5173'),'--strictPort'],ROOT/'frontend')}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['plan','prepare','check','run','up'])
    parser.add_argument('--config',type=Path,default=ROOT/'config/environments/runtime.env')
    parser.add_argument('--role',default='all')
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--connect',action='store_true')
    parser.add_argument('--music',action='store_true')
    args=parser.parse_args()
    config=read(args.config,KEYS)
    config.update({k:os.environ[k] for k in KEYS if os.environ.get(k)})
    action='run' if args.action in ('plan','up') else args.action
    steps=plans(config,action,args.connect,args.apply,args.music)
    if args.role!='all':
        if args.role not in steps:parser.error('해당 작업에서 지원하지 않는 role입니다.')
        steps={args.role:steps[args.role]}
    if args.action=='plan':
        print(json.dumps({name:{'command':cmd,'cwd':str(cwd)} for name,(cmd,cwd) in steps.items()}));return
    if args.action in ('check','up') and args.role=='all':
        checks=cross_configuration()
        print(json.dumps({'configuration_checks':checks,'external_connections_checked':False}),flush=True)
        if not all(checks.values()):return 1
    if args.action=='run' and len(steps)!=1:parser.error('run은 --role을 지정하세요. 전체 실행은 up입니다.')
    processes=[]
    try:
        if args.action=='up':
            if args.apply:
                for command,cwd in plans(config,'prepare',apply=True,music=args.music).values():
                    code=subprocess.call(command,cwd=cwd)
                    if code:return code
            for command,cwd in plans(config,'check',connect=True,allow_pending_music=True).values():
                code=subprocess.call(command,cwd=cwd)
                if code:return code
            for command,cwd in steps.values():processes.append(subprocess.Popen(command,cwd=cwd))
            while True:
                for child in processes:
                    code=child.poll()
                    if code is not None:return code or 1
                import time
                time.sleep(0.5)
        for name,(command,cwd) in steps.items():
            print('runtime_step:'+name,flush=True)
            code=subprocess.call(command,cwd=cwd)
            if code:return code
        return 0
    except KeyboardInterrupt:return 130
    except OSError as error:
        print(json.dumps({'status':'FAILED','error_type':type(error).__name__}));return 1
    finally:
        for child in processes:
            if child.poll() is None:child.terminate()
        for child in processes:
            try:child.wait(timeout=10)
            except subprocess.TimeoutExpired:child.kill();child.wait()


if __name__=='__main__':raise SystemExit(main())
