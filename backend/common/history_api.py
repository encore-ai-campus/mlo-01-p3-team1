import hashlib
import json
from datetime import datetime, time, timezone, timedelta
from django.core import signing
from django.db.models import OuterRef, Subquery
from django.utils import timezone as clock
from rest_framework.response import Response
from backend.recommendation.api import Endpoint
from backend.recommendation.errors import require
from .identity import admin
from .models import FeedbackEvent, Guest, StreamRecord, Projection

EXCLUSION_EVENTS=['TRACK_EXCLUDED','TRACK_EXCLUSION_CANCELLED']


def view(event, latest=None):
    data=event.payload;context=data.get('context_snapshot',{});track=data.get('track_snapshot',{})
    options=context.get('options',{})
    expired=not Guest.objects.filter(pk=event.owner_id,active=True,expires_at__gt=clock.now()).exists()
    return {'event_id':event.pk,'occurred_at':event.occurred_at.isoformat().replace('+00:00','Z'),
            'event_type':event.event_type,'source_playlist_id':event.source_playlist_id,
            'track_id':event.track_id,'track_name':track.get('track_name'),
            'artists_name':track.get('artists_name'),'duration_ms':track.get('duration_ms'),
            'selected_theme_codes':options.get('selected_theme_codes',[]),
            'selected_genre_codes':options.get('selected_genre_codes',[]),
            'track_theme_codes':track.get('theme_codes',[]),'track_genre_codes':track.get('genre_group_codes',[]),
            'context_snapshot':context,'track_snapshot':track,
            'related_exclusion_event_id':data.get('related_exclusion_event_id'),
            'state':'EXCLUDED' if (latest or event.event_type)=='TRACK_EXCLUDED' else 'CANCELLED',
            'context_status':'EXPIRED' if expired else 'ACTIVE','is_test':event.is_test}


class History(Endpoint):
    def get(self,request):
        admin(request,'view_feedback')
        allowed={'from','to','track_id','selected_theme_code','selected_genre_code','track_theme_code','track_genre_code','action','state','cursor','as_of','limit'}
        require(not set(request.query_params)-allowed)
        filters={k:v for k,v in request.query_params.items() if k not in ('cursor','as_of','limit')}
        fingerprint=hashlib.sha256(json.dumps(filters,sort_keys=True).encode()).hexdigest()
        try:
            limit=int(request.query_params.get('limit',20));require(1<=limit<=100)
            as_of=datetime.fromisoformat(request.query_params['as_of'].replace('Z','+00:00')) if request.query_params.get('as_of') else clock.now()
            require(as_of.tzinfo is not None and as_of<=clock.now())
            cursor=None
            if request.query_params.get('cursor'):
                cursor=signing.loads(request.query_params['cursor'],salt='feedback-history')
                require(cursor['filter']==fingerprint and cursor['as_of']==as_of.isoformat(),'CURSOR_INVALID','검색 조건 또는 기준 시각이 다릅니다.',422)
        except (ValueError,KeyError,TypeError,signing.BadSignature):
            require(False,'CURSOR_INVALID','검색 조건과 커서를 확인해 주세요.',422)
        latest=FeedbackEvent.objects.filter(family_id=OuterRef('family_id'),track_id=OuterRef('track_id'),
                    event_type__in=EXCLUSION_EVENTS,occurred_at__lte=as_of).order_by('-occurred_at','-event_id')
        query=FeedbackEvent.objects.filter(event_type__in=EXCLUSION_EVENTS,occurred_at__lte=as_of).annotate(latest_action=Subquery(latest.values('event_type')[:1]))
        for field,compare in [('from','gte'),('to','lt')]:
            if filters.get(field):
                try:at=datetime.combine(datetime.fromisoformat(filters[field]).date(),time(),timezone(timedelta(hours=9)))
                except ValueError:require(False)
                query=query.filter(**{'occurred_at__'+compare:at})
        if filters.get('track_id'):query=query.filter(track_id=filters['track_id'])
        if filters.get('action'):
            require(filters['action'] in EXCLUSION_EVENTS)
            query=query.filter(event_type=filters['action'])
        if filters.get('state'):
            require(filters['state'] in ('EXCLUDED','CANCELLED'))
            query=query.filter(latest_action='TRACK_EXCLUDED' if filters['state']=='EXCLUDED' else 'TRACK_EXCLUSION_CANCELLED')
        if cursor:
            from django.db.models import Q
            query=query.filter(Q(occurred_at__lt=cursor['at'])|Q(occurred_at=cursor['at'],event_id__lt=cursor['id']))
        rows=[]
        # JSON membership is checked without backend-dependent SQLite contains operators.
        for event in query.order_by('-occurred_at','-event_id').iterator(chunk_size=100):
            item=view(event,event.latest_action)
            if any(filters.get(f) and filters[f] not in item[out] for f,out in [
                ('selected_theme_code','selected_theme_codes'),('selected_genre_code','selected_genre_codes'),
                ('track_theme_code','track_theme_codes'),('track_genre_code','track_genre_codes')]):continue
            rows.append((event,item))
            if len(rows)>limit:break
        next_cursor=None
        if len(rows)>limit:
            event=rows[limit-1][0]
            next_cursor=signing.dumps({'filter':fingerprint,'as_of':as_of.isoformat(),'at':event.occurred_at.isoformat(),'id':event.pk},salt='feedback-history')
        return Response({'items':[item for _,item in rows[:limit]],'next_cursor':next_cursor,'as_of':as_of.isoformat().replace('+00:00','Z')})


class HistoryDetail(Endpoint):
    def get(self,request,event_id):
        admin(request,'view_feedback')
        event=FeedbackEvent.objects.filter(pk=event_id,event_type__in=EXCLUSION_EVENTS).first()
        require(event is not None,'NOT_FOUND','기록을 찾을 수 없습니다.',404)
        latest=FeedbackEvent.objects.filter(family_id=event.family_id,track_id=event.track_id,event_type__in=EXCLUSION_EVENTS).order_by('-occurred_at','-event_id').first()
        return Response(view(event,latest.event_type))


class Metrics(Endpoint):
    def get(self,request):
        admin(request,'view_feedback')
        from .models import ProjectedState
        states=ProjectedState.objects.filter(is_test=False)
        ratings=[r.value for r in states.filter(target_key__startswith='rating:') if type(r.value) is int]
        reactions=[r.value for r in states.filter(target_key__startswith='reaction:') if r.value in ('LIKE','DISLIKE')]
        return Response({'rating_count':len(ratings),'rating_mean':sum(ratings)/len(ratings) if ratings else None,
                         'rating_distribution':{str(i):ratings.count(i) for i in range(1,6)},
                         'like_count':reactions.count('LIKE'),'dislike_count':reactions.count('DISLIKE'),
                         'like_ratio':reactions.count('LIKE')/len(reactions) if reactions else None,
                         'outbox_pending':FeedbackEvent.objects.filter(outbox__state__in=['PENDING','SENDING']).count(),
                         'raw_records':StreamRecord.objects.count(),'projected_events':Projection.objects.count(),
                         'is_test':False,'source':'postgresql_projection','as_of':clock.now().isoformat().replace('+00:00','Z')})
