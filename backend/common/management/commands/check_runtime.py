"""Configuration checks by default; explicit --connect performs bounded read checks."""
import json
import os
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


def configuration():
    required=['GUEST_TTL_SECONDS','ADMIN_SESSION_SECONDS','CSV_UPLOAD_MAX_BYTES','SEARCH_SECONDS','MUSIC_RAW_DIRECTORY']
    if not settings.LOCAL_DEMO:required+=['PGHOST','PGDATABASE','PGUSER','MUSIC_S3_BUCKET','MUSIC_S3_REGION','MUSIC_S3_PREFIX']
    checks={name:bool(getattr(settings,name,os.environ.get(name,''))) for name in required}
    from pathlib import Path
    for name in ('GUEST_TTL_SECONDS','ADMIN_SESSION_SECONDS','CSV_UPLOAD_MAX_BYTES','SEARCH_SECONDS'):
        checks[name]=getattr(settings,name)>0
    checks['MUSIC_RAW_DIRECTORY']=bool(settings.MUSIC_RAW_DIRECTORY) and Path(settings.MUSIC_RAW_DIRECTORY).is_absolute()
    from django.utils.module_loading import import_string
    for name in ('WEATHER_PROVIDER','OWNER_RESOLVER','EVENT_SINK'):
        try:checks[name]=callable(import_string(getattr(settings,name)))
        except Exception:checks[name]=False
    for name in ('ES_URL','WEATHER_INDEX','FEEDBACK_KAFKA_BOOTSTRAP','FEEDBACK_KAFKA_TOPIC','ADS_INTERNAL_SECRET'):
        checks[name]=bool(os.environ.get(name))
    checks['shared_mapping_configured']=bool(os.environ.get('WEATHER_MAPPING_DSN') or os.environ.get('PGHOST'))
    checks['integration_enabled']=settings.INTEGRATION_ENABLED
    return checks


def connections():
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor
    from backend.recommendation.models import Catalog
    from pipeline.weather.mapping_postgres import load_regions
    from pipeline.weather.es_latest import configuration as es_configuration
    from pipeline.weather.es_current import request
    def database():
        connection.ensure_connection()
        executor=MigrationExecutor(connection)
        return not executor.migration_plan(executor.loader.graph.leaf_nodes())
    def catalog():return Catalog.objects.filter(ready=True,is_test=settings.LOCAL_DEMO).exists()
    def administrators():
        from django.contrib.auth import get_user_model
        users=list(get_user_model().objects.filter(is_active=True,is_staff=True))
        return all(any(user.has_perm('common.'+permission) for user in users)
                   for permission in ('manage_ads','manage_music','view_feedback'))
    def regions():return bool(load_regions().get('entries'))
    def elasticsearch():
        base,index=es_configuration()
        from pipeline.weather.prepare_es import MAPPING
        actual=request(base,'GET','/'+index).get(index,{}).get('mappings',{})
        return actual.get('dynamic')=='strict' and all(actual.get('properties',{}).get(k)==v for k,v in MAPPING['mappings']['properties'].items())
    def kafka():
        from kafka import KafkaConsumer
        from pipeline.kafka_config import python_options
        client=KafkaConsumer(bootstrap_servers=os.environ['FEEDBACK_KAFKA_BOOTSTRAP'],
                             api_version_auto_timeout_ms=5000,request_timeout_ms=10000,
                             **python_options('FEEDBACK_KAFKA_'))
        try:return bool(client.partitions_for_topic(os.environ['FEEDBACK_KAFKA_TOPIC']))
        finally:client.close()
    def archive():
        if settings.LOCAL_DEMO and not settings.MUSIC_S3_BUCKET:return False
        import boto3
        from botocore.config import Config
        client=boto3.client('s3',region_name=settings.MUSIC_S3_REGION,
                           config=Config(connect_timeout=5,read_timeout=5,retries={'max_attempts':0}))
        return client.get_bucket_versioning(Bucket=settings.MUSIC_S3_BUCKET).get('Status')=='Enabled'
    report={}
    for name,check in [('postgres_migrations',database),('administrator_permissions',administrators),('active_catalog',catalog),('weather_regions',regions),
                       ('weather_es_schema',elasticsearch),('feedback_topic',kafka),('music_archive_versioning',archive)]:
        try:report[name]={'ok':bool(check())}
        except Exception as error:report[name]={'ok':False,'error_type':type(error).__name__}
    return report


class Command(BaseCommand):
    help='설정/준비 상태를 점검합니다. --connect 없이는 외부 저장소에 접속하지 않습니다.'
    requires_system_checks=[]
    requires_migrations_checks=False
    def add_arguments(self,parser):
        parser.add_argument('--connect',action='store_true')
        parser.add_argument('--allow-pending-music',action='store_true')
    def handle(self,*args,**options):
        config=configuration()
        live=connections() if options['connect'] else {}
        ready=all(config.values()) and bool(live) and all(row['ok'] for row in live.values())
        admin_ready=(all(config.values()) and bool(live) and options['allow_pending_music']
                     and all(row['ok'] for name,row in live.items() if name!='active_catalog')
                     and live.get('active_catalog')=={'ok':False})
        self.stdout.write(json.dumps({'configuration':config,'connections':live,'ready':ready,
                                     'status':'STORAGE_READY' if ready else 'ADMIN_READY_MUSIC_PENDING' if admin_ready else 'NOT_READY' if options['connect'] else 'NOT_CONNECTED',
                                     'scope':'STORAGE_STRUCTURE_AND_CONFIG','weather_data_verified':False,
                                     'ads_shared_authentication_verified':False}))
        if not all(config.values()) or (options['connect'] and not ready and not admin_ready):raise CommandError('runtime_not_ready')
