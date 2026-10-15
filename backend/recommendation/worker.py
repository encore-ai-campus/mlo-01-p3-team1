import hashlib
import json
import threading
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from django.conf import settings
from django.db import transaction, close_old_connections
from django.db.models import Q
from django.utils import timezone
from .models import Job, Playlist, Family, uid
from .errors import DomainError, require
from .policy import eligible, score, DURATION_POLICY, TARGET, MINIMUM, MAXIMUM, POLICY, MAPPING
from .weather import validate
from .solver import choose
from .provider import propose, validate_proposal


def claim():
    now = timezone.now()
    with transaction.atomic():
        # SQLite is single-worker local verification only; PostgreSQL supports concurrent claims.
        jobs = Job.objects.select_for_update(skip_locked=not settings.LOCAL_DEMO).filter(
            Q(status='QUEUED') | Q(status='RUNNING',lease_expires_at__lt=now)).order_by('created_at')
        job = jobs.first()
        if not job: return None
        if job.provider_attempted and job.status == 'RUNNING':
            job.status='FAILED'; job.error={'code':'PROVIDER_OUTCOME_UNKNOWN','message':'중단된 외부 호출 결과를 확인해야 해요.','details':{}}
            job.save(); return None
        if job.lease_generation >= 3:
            job.status='FAILED'; job.error={'code':'WORKER_RETRY_EXHAUSTED','message':'작업 복구 한도를 초과했어요.','details':{}}
            job.save(); return None
        job.status='RUNNING'; job.lease_token=uid(); job.lease_generation+=1
        job.lease_expires_at=now+timedelta(seconds=30); job.save()
        return job


def heartbeat(job, stopped):
    close_old_connections()
    try:
        while not stopped.wait(10):
            changed = Job.objects.filter(pk=job.pk,status='RUNNING',lease_token=job.lease_token,
                                         lease_generation=job.lease_generation,
                                         lease_expires_at__gt=timezone.now()).update(lease_expires_at=timezone.now()+timedelta(seconds=30))
            if not changed: return
    finally: close_old_connections()


def active_job(job):
    return Job.objects.filter(pk=job.pk,status='RUNNING',lease_token=job.lease_token,
                              lease_generation=job.lease_generation,lease_expires_at__gt=timezone.now())


def run_one():
    job = claim()
    if not job: return False
    stopped = threading.Event()
    thread = threading.Thread(target=heartbeat,args=(job,stopped),daemon=True)
    thread.start()
    try:
        now=timezone.now(); context=job.input
        require(context['policy_version']==POLICY and context['mapping_version']==MAPPING,
                'POLICY_NOT_READY','이 사이클의 고정 정책 구현을 확인해야 해요.',503)
        if now >= __import__('backend.recommendation.weather',fromlist=['instant']).instant(context['weather']['valid_until']):
            raise DomainError('JOB_EXPIRED','대기 중 예보가 만료됐어요.',410)
        segments=validate(context['weather'],now)
        raw = job.catalog.tracks
        digest=hashlib.sha256(json.dumps(raw,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        require(job.catalog.ready and digest==job.catalog.sha256,'CATALOG_INVALID','카탈로그 무결성 검증에 실패했어요.',503)
        require(len({t['track_id'] for t in raw})==len(raw),'CATALOG_INVALID','중복 곡이 있는 카탈로그예요.',503)
        candidates=[dict(t,scores=score(t,context['options'],segments)) for t in raw
                    if eligible(t,context['options'],context['allowed_genre_group_codes'],context['allowed_speed_codes'],context['excluded_track_ids'])]
        if job.method=='RULE_BASED':
            tracks=choose(candidates,settings.SEARCH_MAX_CANDIDATES,settings.SEARCH_SECONDS)
            summary='날씨와 선택하신 취향을 반영했어요.'
            reasons={}
        else:
            parent=Playlist.objects.get(pk=job.parent_id)
            require(active_job(job).update(provider_attempted=True)==1,'LEASE_LOST','작업 실행 권한이 만료됐어요.',409)
            ids=[t['track_id'] for t in parent.snapshot['items']]
            proposal,diagnostics=propose(candidates,context,ids)
            active_job(job).update(provider_diagnostics=diagnostics)
            tracks=validate_proposal(proposal,candidates,ids)
            summary=proposal['summary']; reasons={r['track_id']:r['reason'] for r in proposal['track_reasons']}
        total=sum(t['duration_ms'] for t in tracks)
        validate(context['weather'],timezone.now(),max(TARGET,total))
        def display(value):
            return None if value is None else str((Decimal(value.numerator)/Decimal(value.denominator)).quantize(Decimal('.01'),rounding=ROUND_HALF_UP))
        items=[]
        for t in tracks:
            exact={k:None if v is None else [v.numerator,v.denominator] for k,v in t['scores'].items()}
            items.append({**t,'scores':{k:display(v) for k,v in t['scores'].items()},'scores_exact':exact,
                          'reason':reasons.get(t['track_id'])})
        with transaction.atomic():
            current=Job.objects.select_for_update().get(pk=job.pk)
            require(current.status=='RUNNING' and current.lease_token==job.lease_token and current.lease_generation==job.lease_generation
                    and current.lease_expires_at>timezone.now(),'LEASE_LOST','작업 실행 권한이 만료됐어요.',409)
            f=Family.objects.select_for_update().get(pk=job.family_id)
            if not job.parent_id:
                f.allowed_genres=sorted({g for t in tracks for g in t['genre_group_codes']}) if not f.options['selected_genre_codes'] else f.options['selected_genre_codes']
                f.allowed_speeds=sorted({t['speed'] for t in tracks}) if f.options['tempo_preference']=='auto' else context['allowed_speed_codes']
                f.save()
            fixed={**context,'allowed_genre_group_codes':f.allowed_genres,'allowed_speed_codes':f.allowed_speeds,
                   'family_id':f.pk,'catalog_version':job.catalog_id,'catalog_sha256':job.catalog.sha256,
                   'source_ref':job.catalog.source_ref,'source_sha256':job.catalog.source_sha256,
                   'duration_policy_version':DURATION_POLICY,'duration_mode':'STANDARD',
                   'effective_target_ms':TARGET,'effective_min_ms':MINIMUM,'effective_max_ms':MAXIMUM,'shortening_reason':None}
            Playlist.objects.create(job=current,family=f,snapshot={'context':fixed,'items':items,'total_ms':total,
                'summary':summary,'generation_method':job.method,'model':'gemini-3.8-flash' if job.parent_id else None,
                'provider_diagnostics':diagnostics if job.parent_id else None,
                'is_test':job.catalog.is_test,'validation_passed':True})
            current.status='SUCCEEDED'; current.error=None; current.save()
    except DomainError as exc:
        active_job(job).update(
            status='EXPIRED' if exc.code=='JOB_EXPIRED' else 'FAILED',error={'code':exc.code,'message':exc.message,'details':exc.details})
    except Exception:
        active_job(job).update(
            status='FAILED',error={'code':'INTERNAL_ERROR','message':'작업 처리에 실패했어요. 현재 결과는 유지됩니다.','details':{}})
        raise
    finally:
        stopped.set(); thread.join(timeout=1)
    return True
