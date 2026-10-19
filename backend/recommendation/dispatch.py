"""PostgreSQL-backed dispatch shared by independent hosts and worker processes."""
import os
from math import isfinite
from datetime import timedelta
from django.conf import settings
from django.db import connection, transaction
from django.db.models import Q
from django.db.models.functions import Now
from .errors import require
from .models import DispatchControl, Job, uid


METHODS = {'rule': 'RULE_BASED', 'gemini': 'GEMINI_RECONFIGURE'}


def configuration():
    """No connections or writes; all workers must receive the same shared limits."""
    return {
        'recommendation_queue': settings.RECOMMENDATION_QUEUE in ('all', *METHODS),
        'recommendation_lease': settings.RECOMMENDATION_LEASE_SECONDS > 0,
        'recommendation_heartbeat': 0 < settings.RECOMMENDATION_HEARTBEAT_SECONDS < settings.RECOMMENDATION_LEASE_SECONDS / 2,
        'recommendation_job_timeout': settings.RECOMMENDATION_JOB_TIMEOUT_SECONDS > settings.RECOMMENDATION_LEASE_SECONDS,
        'recommendation_recoveries': settings.RECOMMENDATION_MAX_RECOVERIES >= 0,
        'recommendation_idle': isfinite(settings.RECOMMENDATION_WORKER_IDLE_SECONDS) and settings.RECOMMENDATION_WORKER_IDLE_SECONDS > 0,
        'recommendation_rule_capacity': settings.RECOMMENDATION_MAX_QUEUED_RULE > 0,
        'recommendation_gemini_capacity': settings.RECOMMENDATION_MAX_QUEUED_GEMINI > 0,
        'gemini_concurrency': settings.GEMINI_MAX_CONCURRENT > 0,
        'gemini_interval': isfinite(settings.GEMINI_MIN_INTERVAL_SECONDS) and settings.GEMINI_MIN_INTERVAL_SECONDS > 0,
        'gemini_timeout': not settings.GEMINI_ENABLED or 0 < settings.GEMINI_TIMEOUT_MS / 1000 < settings.RECOMMENDATION_JOB_TIMEOUT_SECONDS,
        'gemini_candidate_budget': not settings.GEMINI_ENABLED or settings.GEMINI_MAX_CANDIDATES > 0,
    }


def locked_control(name, nonblocking=False):
    DispatchControl.objects.get_or_create(name=name)
    return DispatchControl.objects.select_for_update(
        skip_locked=nonblocking and connection.features.has_select_for_update_skip_locked,
    ).annotate(dispatch_now=Now()).filter(pk=name).first()


def admit(method):
    """Called inside the API transaction, after ownership/idempotency checks."""
    require(connection.in_atomic_block, 'POLICY_NOT_READY', '작업 저장 연결을 확인해 주세요.', 503)
    queue = next(name for name, value in METHODS.items() if value == method)
    locked_control('admission-' + queue)
    limit = getattr(settings, 'RECOMMENDATION_MAX_QUEUED_' + queue.upper())
    require(Job.objects.filter(method=method, status='QUEUED').count() < limit,
            'RECOMMENDATION_QUEUE_FULL', '추천 요청이 많아요. 잠시 후 다시 시도해 주세요.', 503,
            queue=queue, retry_after_seconds=max(1, int(settings.RECOMMENDATION_WORKER_IDLE_SECONDS)))


def active_job(job):
    return Job.objects.filter(pk=job.pk, status='RUNNING', lease_token=job.lease_token,
                              lease_generation=job.lease_generation, lease_expires_at__gt=Now())


def fail_expired(job, now):
    if job.provider_attempted:
        code, message = 'PROVIDER_OUTCOME_UNKNOWN', '중단된 외부 호출 결과를 확인해야 해요.'
    elif job.recovery_count >= settings.RECOMMENDATION_MAX_RECOVERIES:
        code, message = 'WORKER_RETRY_EXHAUSTED', '작업 복구 한도를 초과했어요.'
    else:
        return False
    job.status = 'FAILED'
    job.error = {'code': code, 'message': message, 'details': {}}
    job.finished_at = now
    job.save(update_fields=['status', 'error', 'finished_at'])
    return True


def claim(queue='all', worker_id=''):
    require(queue in ('all', *METHODS), 'POLICY_NOT_READY', '작업자 큐 설정을 확인해 주세요.', 503)
    # Compatibility mode prefers rule jobs. Production uses separate queue processes.
    for lane in METHODS if queue == 'all' else (queue,):
        with transaction.atomic():
            gate = locked_control('gemini', nonblocking=True) if lane == 'gemini' else None
            if lane == 'gemini' and gate is None:
                continue
            for _ in range(32):
                job = Job.objects.select_for_update(
                    skip_locked=connection.features.has_select_for_update_skip_locked,
                ).filter(method=METHODS[lane]).filter(
                    Q(status='QUEUED') | Q(status='RUNNING', lease_expires_at__lte=Now()),
                ).annotate(dispatch_now=Now()).order_by('created_at', 'pk').first()
                if job is None:
                    break
                now = job.dispatch_now
                expired = job.status == 'RUNNING'
                if expired and fail_expired(job, now):
                    continue
                if lane == 'gemini':
                    if gate.next_provider_at and gate.next_provider_at > now:
                        break
                    occupied = Job.objects.filter(method=METHODS[lane]).exclude(pk=job.pk).filter(
                        Q(status='RUNNING', lease_expires_at__gt=Now()) | Q(provider_lease_until__gt=Now()),
                    ).count()
                    if occupied >= settings.GEMINI_MAX_CONCURRENT:
                        break
                job.status = 'RUNNING'
                job.lease_token = uid()
                job.lease_generation += 1
                job.recovery_count += int(expired)
                job.lease_expires_at = now + timedelta(seconds=settings.RECOMMENDATION_LEASE_SECONDS)
                job.worker_id = worker_id[:160]
                job.claimed_at = now
                job.finished_at = None
                job.save()
                return job
    return None


def begin_provider(job):
    """Reserve a call before sending; return delay without holding any DB lock."""
    require(settings.GEMINI_ENABLED and bool(os.environ.get('GEMINI_API_KEY')) and settings.GEMINI_TIMEOUT_MS > 0,
            'RECONFIGURATION_UNAVAILABLE', '재설정 API 설정을 확인해 주세요.', 503)
    with transaction.atomic():
        gate = locked_control('gemini')
        current = active_job(job).select_for_update().annotate(dispatch_now=Now()).first()
        require(current is not None, 'LEASE_LOST', '작업 실행 권한이 만료됐어요.', 409)
        require(not current.provider_attempted, 'PROVIDER_OUTCOME_UNKNOWN', '중단된 외부 호출 결과를 확인해야 해요.', 503)
        now = current.dispatch_now
        occupied = Job.objects.exclude(pk=job.pk).filter(provider_lease_until__gt=Now())
        if occupied.count() >= settings.GEMINI_MAX_CONCURRENT:
            return max(0.05, (occupied.order_by('provider_lease_until').first().provider_lease_until - now).total_seconds())
        if gate.next_provider_at and gate.next_provider_at > now:
            return (gate.next_provider_at - now).total_seconds()
        # An interrupted/ambiguous HTTP call retains its permit until timeout + lease grace.
        current.provider_attempted = True
        current.provider_started_at = now
        current.provider_lease_until = now + timedelta(
            seconds=settings.GEMINI_TIMEOUT_MS / 1000 + settings.RECOMMENDATION_LEASE_SECONDS)
        current.save(update_fields=['provider_attempted', 'provider_started_at', 'provider_lease_until'])
        gate.next_provider_at = now + timedelta(seconds=settings.GEMINI_MIN_INTERVAL_SECONDS)
        gate.save(update_fields=['next_provider_at'])
        return 0


def end_provider(job):
    # A confirmed response frees the permit. Ambiguous failure/crash keeps its deadline.
    Job.objects.filter(pk=job.pk, lease_token=job.lease_token,
                       lease_generation=job.lease_generation).update(provider_lease_until=None)
