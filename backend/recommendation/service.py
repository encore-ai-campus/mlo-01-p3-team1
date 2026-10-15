import os
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.module_loading import import_string
from .models import OwnerLock, Family, Job, Playlist, Catalog, Idempotency, PendingEvent, uid
from .errors import require
from .inputs import shape, options, strict_int, strings, DEFAULTS
from .policy import POLICY, MAPPING, OPTIONS, GENRES, initial_speeds
from .weather import obtain, validate


def event(kind, family, request_id, payload):
    event_id=uid()
    data = {'event_id':event_id,'owner_id':family.owner_id,'family_id':family.pk,'request_id':request_id,
            'is_test':settings.LOCAL_DEMO,**payload}
    if settings.EVENT_SINK:
        # B's hook must write to the same database transaction and must not call Kafka inline.
        import_string(settings.EVENT_SINK)(kind,data)
    else:
        require(settings.LOCAL_DEMO,'POLICY_NOT_READY','공통 이벤트 저장 연결을 기다리고 있어요.',503)
        PendingEvent.objects.create(event_id=event_id,event_type=kind,payload=data)
    return event_id


def owned(model, owner, pk, lock=False):
    query = model.objects.select_for_update() if lock else model.objects
    obj = query.filter(pk=pk, **({'owner_id':owner} if model is Family else {'family__owner_id':owner})).first()
    require(obj is not None,'NOT_FOUND','결과를 찾을 수 없어요.',404)
    return obj


def busy(family):
    return family.job_set.filter(status__in=['QUEUED','RUNNING']).exists()


def mutate(owner, scope, key, data, operation):
    require(type(key) is str and bool(key.strip()) and len(key)<=200)
    with transaction.atomic():
        OwnerLock.objects.get_or_create(owner_id=owner)
        OwnerLock.objects.select_for_update().get(owner_id=owner)
        cached = Idempotency.objects.filter(owner_id=owner,scope=scope,key=key).first()
        if cached:
            require(cached.body == data,'IDEMPOTENCY_CONFLICT','같은 요청 키에 다른 내용이 있어요.',409)
            return cached.response, cached.status
        response,status = operation()
        Idempotency.objects.create(owner_id=owner,scope=scope,key=key,body=data,response=response,status=status)
        return response,status


def catalog():
    obj = Catalog.objects.defer('tracks').filter(ready=True,is_test=settings.LOCAL_DEMO).order_by('-created_at').first()
    require(obj is not None,'POLICY_NOT_READY','검증된 음악 카탈로그를 준비하고 있어요.',503)
    return obj


def enqueue(family, request_id, parent=None):
    now = timezone.now()
    bundle = obtain(family.options['region_id'],now)
    segments = validate(bundle,now)
    speeds = family.allowed_speeds or initial_speeds(family.options['tempo_preference'],segments)
    fixed = {'options':family.options,'weather':bundle,'excluded_track_ids':family.excluded,
             'exclusion_revision':family.exclusion_revision,'allowed_genre_group_codes':family.allowed_genres or sorted(GENRES),
             'allowed_speed_codes':speeds,'policy_version':family.policy_version,'mapping_version':family.mapping_version}
    job = Job.objects.create(family=family,input=fixed,catalog=catalog(),request_id=request_id,
                             parent_id=parent.pk if parent else None,method='GEMINI_RECONFIGURE' if parent else 'RULE_BASED')
    return {'job_id':job.pk,'status':job.status,'poll_url':f'/api/recommendation-jobs/{job.pk}'},202


def basic(owner,key,data,request_id):
    body = shape(data,[*DEFAULTS,'region_id','excluded_track_ids'])
    require(body.get('region_id') not in (None,''),'REGION_REQUIRED','지역을 선택해 주세요.',400)
    require(type(body['region_id']) is str and body['region_id'].strip())
    body = {**options(body),'region_id':body['region_id'],'excluded_track_ids':strings(body.get('excluded_track_ids',[]))}
    require(not body['excluded_track_ids'])
    def op():
        require(body['option_version']==OPTIONS,'OPTIONS_CHANGED','선택 항목을 새로 확인해 주세요.',409)
        family = Family.objects.create(owner_id=owner,options={k:v for k,v in body.items() if k!='excluded_track_ids'},
                                       allowed_genres=body['selected_genre_codes'],policy_version=POLICY,mapping_version=MAPPING)
        return enqueue(family,request_id)
    return mutate(owner,'basic',key,body,op)


def exclusions(owner,family_id,key=None,data=None,request_id=''):
    family = owned(Family,owner,family_id)
    if data is None:
        return {'family_id':family.pk,'excluded_track_ids':family.excluded,'revision':family.exclusion_revision,
                'items':[family.excluded_items[t] for t in family.excluded]}
    body = shape(data,['source_playlist_id','expected_revision','excluded_track_ids'],['source_playlist_id','expected_revision','excluded_track_ids'])
    require(type(body['source_playlist_id']) is str)
    body['expected_revision'] = strict_int(body['expected_revision'])
    body['excluded_track_ids'] = strings(body['excluded_track_ids'])
    def op():
        f = owned(Family,owner,family_id,True)
        source = owned(Playlist,owner,body['source_playlist_id'])
        require(source.family_id==f.pk,'NOT_FOUND','결과를 찾을 수 없어요.',404)
        require(body['expected_revision']==f.exclusion_revision,'EXCLUSION_REVISION_CONFLICT','최신 제외 목록을 확인해 주세요.',409,
                revision=f.exclusion_revision,excluded_track_ids=f.excluded)
        require(not busy(f),'JOB_IN_PROGRESS','선곡표를 생성하고 있어요.',409)
        tracks = {t['track_id']:t for t in source.snapshot['items']}
        before, after = set(f.excluded),set(body['excluded_track_ids'])
        require(after-before <= tracks.keys())
        if before != after:
            f.exclusion_revision += 1
            for track_id in sorted(before ^ after):
                added = track_id in after
                previous = f.excluded_items.get(track_id,{})
                event_id=event('TRACK_EXCLUDED' if added else 'TRACK_EXCLUSION_CANCELLED',f,request_id,
                      {'source_playlist_id':source.pk,'track_id':track_id,'revision':f.exclusion_revision,
                       'related_exclusion_event_id':None if added else previous.get('event_id'),
                       'context_snapshot':source.snapshot['context'],
                       'track_snapshot':tracks[track_id] if added else f.excluded_items[track_id]['track_snapshot']})
                if added:
                    t = tracks[track_id]
                    f.excluded_items[track_id] = {k:t[k] for k in ['track_id','track_name','artists_name']}
                    f.excluded_items[track_id]['track_snapshot'] = t
                    f.excluded_items[track_id]['event_id'] = event_id
            f.excluded = sorted(after); f.save()
        return {'family_id':f.pk,'excluded_track_ids':f.excluded,'revision':f.exclusion_revision},200
    return mutate(owner,'exclusions:'+family_id,key,body,op)


def regenerate(owner,playlist_id,key,data,request_id):
    parent = owned(Playlist,owner,playlist_id)
    body = shape(data,[*DEFAULTS,'exclusion_revision'])
    require('exclusion_revision' in body,'EXCLUSION_REVISION_REQUIRED','제외 버전이 필요해요.',400)
    body = {**options(body,parent.family.options),'exclusion_revision':strict_int(body['exclusion_revision'])}
    def op():
        f = owned(Family,owner,parent.family_id,True)
        require({k:v for k,v in body.items() if k!='exclusion_revision'}==f.options,
                'CYCLE_CONDITIONS_CHANGED','조건을 바꾸셨다면 새 선곡표를 받아 주세요.',409)
        require(body['exclusion_revision']==f.exclusion_revision,'EXCLUSION_REVISION_CONFLICT','최신 제외 목록을 확인해 주세요.',409)
        require(not busy(f),'JOB_IN_PROGRESS','선곡표를 생성하고 있어요.',409)
        require(settings.GEMINI_ENABLED and settings.GEMINI_TIMEOUT_MS > 0 and settings.GEMINI_MAX_CANDIDATES > 0
                and bool(os.environ.get('GEMINI_API_KEY')) and int(os.environ.get('GEMINI_MAX_OUTPUT_TOKENS','0'))>0,
                'RECONFIGURATION_UNAVAILABLE','재설정 서비스 연결을 기다리고 있어요. 현재 선곡표는 유지됩니다.',503)
        return enqueue(f,request_id,parent)
    return mutate(owner,'regenerate:'+playlist_id,key,body,op)


def approve(owner,playlist_id,key,data,request_id):
    result = owned(Playlist,owner,playlist_id)
    body = shape(data,['approval_revision','exclusion_revision'])
    require('exclusion_revision' in body,'EXCLUSION_REVISION_REQUIRED','제외 버전이 필요해요.',400)
    body = {k:strict_int(body.get(k)) for k in ['approval_revision','exclusion_revision']}
    def op():
        f = owned(Family,owner,result.family_id,True)
        require(body['approval_revision']==f.approval_revision,'APPROVAL_REVISION_CONFLICT','최신 승인 상태를 확인해 주세요.',409)
        require(body['exclusion_revision']==f.exclusion_revision,'EXCLUSION_REVISION_CONFLICT','최신 제외 목록을 확인해 주세요.',409)
        require(not busy(f),'JOB_IN_PROGRESS','선곡표를 생성하고 있어요.',409)
        require(result.snapshot.get('validation_passed') is True
                and result.snapshot['context'].get('duration_policy_version')=='phase3-duration-20261014.2',
                'RESULT_NOT_APPROVABLE','현재 시간 정책으로 검증한 결과가 아니에요.',409)
        require(set(result.snapshot['context']['excluded_track_ids'])==set(f.excluded),
                'EXCLUSIONS_NOT_APPLIED','제외 변경을 반영한 선곡표가 필요해요.',409)
        if f.approved_playlist_id != result.pk:
            f.approval_revision += 1; f.approved_playlist_id = result.pk; f.save()
            event('PLAYLIST_APPROVED',f,request_id,{'source_playlist_id':result.pk,'revision':f.approval_revision,
                                                 'context_snapshot':result.snapshot['context'],'track_snapshots':result.snapshot['items']})
        return {'family_id':f.pk,'approved_playlist_id':result.pk,'approval_revision':f.approval_revision},200
    return mutate(owner,'approval:'+playlist_id,key,body,op)
