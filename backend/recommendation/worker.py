import hashlib
import json
import threading
import zlib
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from django.conf import settings
from django.db import transaction, close_old_connections
from django.db.models import Q
from django.utils import timezone
from .models import Job, Playlist, Family, Catalog, uid
from .errors import DomainError, require
from .policy import eligible, score, weather_fit, off_preference_details, DURATION_POLICY, TARGET, MINIMUM, MAXIMUM, POLICY, MAPPING, WEATHER_SCORE_VERSION, OFF_SCORE_VERSION
from .weather import validate, obtain, current_profile, instant
from .solver import choose, choose_preview
from .provider import propose, validate_proposal, candidate_window
from .catalog_storage import unpack
from .service import current_catalog


_catalog_lock = threading.Lock()
_catalog_key = None
_catalog_tracks = None


def verified_catalog(catalog):
    """Keep one immutable, verified catalog version in this worker process."""
    global _catalog_key, _catalog_tracks
    require(catalog.ready, 'CATALOG_INVALID', '카탈로그 무결성 검증에 실패했어요.', 503)
    key = (catalog.pk, catalog.sha256)
    with _catalog_lock:
        if _catalog_key == key:
            return _catalog_tracks
        stored = Catalog.objects.only('tracks').get(pk=catalog.pk).tracks
        try:
            raw = unpack(stored)
        except (ValueError, TypeError, KeyError, UnicodeError, zlib.error):
            raise DomainError('CATALOG_INVALID', '카탈로그 무결성 검증에 실패했어요.', 503) from None
        digest = hashlib.sha256(json.dumps(raw, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        require(digest == catalog.sha256 and len({t['track_id'] for t in raw}) == len(raw),
                'CATALOG_INVALID', '카탈로그 무결성 검증에 실패했어요.', 503)
        _catalog_key, _catalog_tracks = key, raw
        return raw


def warm_current_catalog():
    catalog = current_catalog()
    if catalog is not None:
        verified_catalog(catalog)


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
        require(context['policy_version']==POLICY and context['mapping_version']==MAPPING
                and context.get('score_version')==(
                    WEATHER_SCORE_VERSION if context['options']['weather_influence_mode']=='ON' else OFF_SCORE_VERSION),
                'POLICY_NOT_READY','이 사이클의 고정 정책 구현을 확인해야 해요.',503)
        on=context['options']['weather_influence_mode']=='ON'
        if on:
            if now >= instant(context['weather']['valid_until']):
                raise DomainError('JOB_EXPIRED','대기 중 예보가 만료됐어요.',410)
            validate(context['weather'],now)
        catalog = Catalog.objects.defer('tracks').get(pk=job.catalog_id)
        raw = verified_catalog(catalog)
        candidates=[]
        candidate_audit={'catalog_count':len(raw),'common_eligible_count':0,'common_rejected_count':0,
                         'common_eligible_total_ms':0,'weather_rejected_count':0,'off_missing_preference_count':0}
        for t in raw:
            if not eligible(t,context['options'],context['allowed_genre_group_codes'],context['allowed_speed_codes'],context['excluded_track_ids']):
                candidate_audit['common_rejected_count']+=1
                continue
            candidate_audit['common_eligible_count']+=1
            candidate_audit['common_eligible_total_ms']+=t['duration_ms']
            scored=score(t,context['options'],context['weather_code'])
            if scored is None:
                candidate_audit['weather_rejected_count']+=1
                continue
            if not on and scored['P'] is None and (context['options']['selected_theme_codes'] or context['options']['selected_genre_codes'] or context['options']['tempo_preference']!='auto'):
                candidate_audit['off_missing_preference_count']+=1
                continue
            candidates.append(dict(t,scores=scored))
        candidate_audit['candidate_count']=len(candidates)
        candidate_audit['candidate_total_ms']=sum(t['duration_ms'] for t in candidates)
        preview=settings.LOCAL_DEMO and catalog.source_ref.startswith('local-preview:')
        if job.method=='RULE_BASED':
            search_diagnostics={}
            if preview:
                parent_ids={t['track_id'] for t in Playlist.objects.get(pk=job.parent_id).snapshot['items']} if job.parent_id else set()
                tracks,search_diagnostics=choose_preview(candidates,context['options']['weather_influence_mode'],
                                                          context['options']['selected_genre_codes'],context['seed'],parent_ids)
                if parent_ids:
                    search_diagnostics.update({'parent_track_count':len(parent_ids),
                                               'required_new_count':max(1,len(parent_ids)//5),
                                               'actual_new_count':len({t['track_id'] for t in tracks}-parent_ids)})
            else:
                tracks=choose(candidates,settings.SEARCH_MAX_CANDIDATES,settings.SEARCH_SECONDS,
                              context['options']['weather_influence_mode'],context['options']['selected_genre_codes'],context['seed'],search_diagnostics)
            summary=('실제 CSV에서 다른 곡으로 다시 구성한 로컬 선곡표예요.' if preview and job.parent_id else
                     '실제 CSV의 미검수 곡으로 만든 로컬 프리뷰예요.' if preview else
                     '날씨와 선택하신 취향을 반영했어요.' if on else '선택하신 취향을 반영했어요.')
            reasons={}
        else:
            parent=Playlist.objects.get(pk=job.parent_id)
            ids=[t['track_id'] for t in parent.snapshot['items']]
            offered=candidate_window(candidates,context,ids)
            require(active_job(job).update(provider_attempted=True)==1,'LEASE_LOST','작업 실행 권한이 만료됐어요.',409)
            proposal,diagnostics=propose(offered,context,ids)
            diagnostics.update({'eligible_candidate_count':len(candidates),'offered_candidate_count':len(offered),
                                'searched_full_pool':len(offered)==len(candidates)})
            active_job(job).update(provider_diagnostics=diagnostics)
            tracks=validate_proposal(proposal,offered,ids,context['options'],all_candidates=candidates)
            summary=proposal['summary']; reasons={r['track_id']:r['reason'] for r in proposal['track_reasons']}
        total=sum(t['duration_ms'] for t in tracks)
        if on:
            checked_at=timezone.now()
            validate(context['weather'],checked_at,max(TARGET,total))
            latest=obtain(context['options']['region_id'],checked_at)
            latest_code=current_profile(latest,validate(latest,checked_at),checked_at)
            require(latest_code==context['weather_code'],'JOB_EXPIRED',
                    '선곡 중 날씨가 바뀌었어요. 새 날씨로 다시 요청해 주세요.',410)
        def display(value):
            return None if value is None else str((Decimal(value.numerator)/Decimal(value.denominator)).quantize(Decimal('.01'),rounding=ROUND_HALF_UP))
        def exact(value):
            if hasattr(value,'numerator') and hasattr(value,'denominator'): return [value.numerator,value.denominator]
            if isinstance(value,dict): return {k:exact(v) for k,v in value.items()}
            if isinstance(value,list): return [exact(v) for v in value]
            return value
        items=[]
        for t in tracks:
            evidence=weather_fit(t,context['weather_code']) if on else off_preference_details(t,context['options'])
            item={k:v for k,v in t.items() if k != 'score_cache'}
            items.append({**item,'scores':{k:display(v) for k,v in t['scores'].items()},'scores_exact':exact(t['scores']),
                          'score_evidence':exact(evidence),
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
                   'family_id':f.pk,'catalog_version':job.catalog_id,'catalog_sha256':catalog.sha256,
                   'source_ref':catalog.source_ref,'source_sha256':catalog.source_sha256,
                   'duration_policy_version':DURATION_POLICY,'duration_mode':'STANDARD',
                   'effective_target_ms':TARGET,'effective_min_ms':MINIMUM,'effective_max_ms':MAXIMUM,'shortening_reason':None}
            result=Playlist.objects.create(job=current,family=f,snapshot={'context':fixed,'items':items,'total_ms':total,
                'summary':summary,'generation_method':job.method,'model':'gemini-3.8-flash' if job.method=='GEMINI_RECONFIGURE' else None,
                'provider_diagnostics':diagnostics if job.method=='GEMINI_RECONFIGURE' else None,
                'search_diagnostics':{**candidate_audit,**search_diagnostics} if job.method=='RULE_BASED' else candidate_audit,
                'is_test':catalog.is_test,'preview_only':preview,'validation_passed':not preview})
            if settings.INTEGRATION_ENABLED:
                from .service import event
                event('PLAYLIST_GENERATED',f,job.request_id,{'source_playlist_id':result.pk,'context_snapshot':fixed,
                                                           'track_snapshots':items})
            current.status='SUCCEEDED'; current.error=None; current.save()
    except DomainError as exc:
        if exc.code in ('CANDIDATE_SHORTAGE','SEARCH_INCOMPLETE','NO_MEANINGFUL_CHANGE') and 'candidate_audit' in locals():
            exc.details.update(candidate_audit)
        active_job(job).update(
            status='EXPIRED' if exc.code=='JOB_EXPIRED' else 'FAILED',error={'code':exc.code,'message':exc.message,'details':exc.details})
    except Exception:
        active_job(job).update(
            status='FAILED',error={'code':'INTERNAL_ERROR','message':'작업 처리에 실패했어요. 현재 결과는 유지됩니다.','details':{}})
        raise
    finally:
        stopped.set(); thread.join(timeout=1)
    return True
