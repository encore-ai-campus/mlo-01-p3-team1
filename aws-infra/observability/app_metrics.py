"""Read-only Django projections. Run with the application's existing venv and env.

Never read Catalog.tracks, playlist snapshots, cookies, images or admin before/after bodies.
"""
import datetime
import json
import os
import sys


def emit(value):
    def encode(item):
        if isinstance(item, (datetime.datetime, datetime.date)):
            return item.isoformat()
        return str(item)
    print(json.dumps(value, default=encode, separators=(',',':')))


def control():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE','cafe.settings')
    import django
    django.setup()
    from django.db import connection
    from django.db.models import Count
    from django.utils import timezone
    from backend.recommendation.models import Job, Playlist
    from backend.common.models import Outbox, StreamRecord, Projection
    with connection.cursor() as cursor:
        cursor.execute("SET statement_timeout = '5000ms'")
        cursor.execute('SET default_transaction_read_only = on')
    now=timezone.now()
    # Bounded recent metadata query; no JSON catalog/snapshot columns are selected.
    terminal=list(Job.objects.filter(created_at__gte=now-datetime.timedelta(days=7),
                  status__in=['SUCCEEDED','FAILED','EXPIRED']).order_by('-created_at').values(
                  'id','method','status','created_at','error','catalog__is_test')[:5000])
    finished=dict(Playlist.objects.filter(job_id__in=[r['id'] for r in terminal]).values_list('job_id','created_at'))
    for row in terminal:
        if row['catalog__is_test']:continue
        item={'dataset':'recommendation','event_id':'recommendation:'+row['id']+':'+row['status'],
              '@timestamp':row['created_at'].isoformat(),'job_id':row['id'],'method':row['method'],
              'status':row['status'],'timestamp_basis':'job_created_at','is_test':False}
        if row['id'] in finished:item['latency_seconds']=max(0,(finished[row['id']]-row['created_at']).total_seconds())
        error=row['error']
        if isinstance(error,dict):item['error_type']=str(error.get('code') or error.get('error_type') or 'unknown')[:100]
        emit(item)
    emit({'dataset':'feedback','@timestamp':now.isoformat(),
          'pending':Outbox.objects.exclude(state='SENT').count(),
          'stream_records':StreamRecord.objects.count(),'projected_events':Projection.objects.count()})
    for row in Job.objects.filter(status__in=['QUEUED','RUNNING']).values('status').annotate(count=Count('id')):
        emit({'dataset':'recommendation_queue','@timestamp':now.isoformat(),**row})


def advertising():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
    import django
    django.setup()
    from repositories.ads_mongo import get_ads_repository
    from workers.ads_logs import inspect_logs
    repository=get_ads_repository()
    database=repository.database
    now=datetime.datetime.now(datetime.timezone.utc).isoformat()
    allowed=('log_event_id','source_event_id','schema_version','request_id','ad_id','creative_version',
             'placement','event_type','result','counted','occurred_at','received_at','processed_at','is_test')
    report=inspect_logs(database,is_test=repository.is_test,limit=20)
    for collection,values in report.items():
        emit({'dataset':'ads_audit','@timestamp':now,'collection':collection,
              'count':values['stored'],'pending':values['missing_required'],
              'failed_events':values['sample_invalid'],'is_test':repository.is_test})
        # Select only nested scalar metadata at MongoDB; large snapshots and assets never leave MongoDB.
        projection={'log_record.'+key:1 for key in ['log_event_id','stored_at']}
        projection.update({'log_record.payload.'+key:1 for key in allowed})
        for document in database[collection].find({'is_test':repository.is_test,'log_record':{'$ne':None}},projection).sort('_id',-1).limit(5000):
            record=document.get('log_record') or {}
            payload=record.get('payload') or {}
            item={key:payload[key] for key in allowed if key in payload}
            item.update(dataset='ads',collection=collection,event_id=record.get('log_event_id',''),
                        **{'@timestamp':payload.get('occurred_at') or record.get('stored_at') or now})
            emit(item)


if __name__=='__main__':
    {'control':control,'advertising':advertising}[sys.argv[1]]()
