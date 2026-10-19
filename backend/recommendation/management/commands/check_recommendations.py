"""Read-only queue observation; does not claim jobs, call Gemini or prove worker liveness."""
import json
from math import ceil, isfinite
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.models import Count
from django.db.models.functions import Now
from backend.recommendation.dispatch import METHODS
from backend.recommendation.models import Job


def snapshot():
    queues = {}
    for queue, method in METHODS.items():
        jobs = Job.objects.filter(method=method)
        oldest = jobs.filter(status='QUEUED').only('created_at').annotate(dispatch_now=Now()).order_by('created_at').first()
        recent = list(jobs.filter(finished_at__isnull=False, claimed_at__isnull=False)
                      .order_by('-finished_at').values_list('claimed_at', 'finished_at')[:100])
        durations = sorted(max(0, (end - start).total_seconds()) for start, end in recent)
        queues[queue] = {
            'states': dict(jobs.values_list('status').annotate(total=Count('pk'))),
            'oldest_wait_seconds': round(max(0, (oldest.dispatch_now - oldest.created_at).total_seconds()), 3) if oldest else 0,
            'expired_leases': jobs.filter(status='RUNNING', lease_expires_at__lte=Now()).count(),
            'recent_finished_count': len(durations),
            'recent_run_p95_seconds': round(durations[ceil(len(durations) * .95) - 1], 3) if durations else None,
            'reserved_provider_calls': jobs.filter(provider_lease_until__gt=Now()).count(),
            'running_by_worker': dict(jobs.filter(status='RUNNING').values_list('worker_id').annotate(total=Count('pk'))),
        }
    return {'database': connection.vendor, 'queues': queues, 'worker_liveness_verified': False}


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument('--max-wait-seconds', type=float, default=0)

    def handle(self, *args, **options):
        threshold = options['max_wait_seconds']
        if not isfinite(threshold) or threshold < 0: raise CommandError('max_wait_seconds must be finite and nonnegative')
        report = snapshot()
        delayed = any(queue['expired_leases'] or (threshold > 0 and queue['oldest_wait_seconds'] > threshold)
                      for queue in report['queues'].values())
        report['status'] = 'ATTENTION' if delayed else 'OBSERVED'
        self.stdout.write(json.dumps(report, ensure_ascii=False))
        if delayed: raise CommandError('recommendation_queue_needs_attention')
