import io
import json
import os
import signal
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import Mock, patch
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import close_old_connections, connection, transaction
from django.test import Client, SimpleTestCase, TransactionTestCase, override_settings, skipUnlessDBFeature
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from backend.recommendation import dispatch
from backend.recommendation.errors import DomainError
from backend.recommendation.models import Catalog, DispatchControl, Family, Idempotency, Job
from backend.recommendation.worker import heartbeat


@override_settings(LOCAL_DEMO=True, GEMINI_ENABLED=True, GEMINI_TIMEOUT_MS=60000,
                   GEMINI_MAX_CANDIDATES=200, GEMINI_MAX_CONCURRENT=1, GEMINI_MIN_INTERVAL_SECONDS=2)
class DispatchTests(TransactionTestCase):
    def setUp(self):
        self.catalog = Catalog.objects.create(version='dispatch-test', tracks=[], sha256='a'*64,
            source_ref='dispatch-fixture', source_sha256='b'*64, ready=True, is_test=True)
        self.family = Family.objects.create(owner_id='dispatch-owner', options={}, policy_version='test', mapping_version='test')

    def job(self, method='RULE_BASED'):
        return Job.objects.create(family=self.family, catalog=self.catalog, input={}, request_id='test', method=method)

    def expire(self, job):
        Job.objects.filter(pk=job.pk).update(lease_expires_at=timezone.now()-timedelta(seconds=1))

    def test_rule_lane_skips_gemini_and_compatibility_prefers_rule(self):
        gemini = self.job('GEMINI_RECONFIGURE')
        rule = self.job()
        self.assertEqual(dispatch.claim('all', 'control-a:rule').pk, rule.pk)
        self.assertIsNone(dispatch.claim('rule', 'control-b:rule'))
        self.assertEqual(dispatch.claim('gemini', 'control-a:gemini').pk, gemini.pk)

    def test_gemini_saturation_does_not_block_rule_lane(self):
        self.job('GEMINI_RECONFIGURE'); self.job('GEMINI_RECONFIGURE')
        self.assertIsNotNone(dispatch.claim('gemini', 'control-a:gemini'))
        self.assertIsNone(dispatch.claim('gemini', 'control-b:gemini'))
        rule = self.job()
        self.assertEqual(dispatch.claim('rule', 'control-b:rule').pk, rule.pk)

    def test_recovery_fences_old_worker_and_has_a_bounded_budget(self):
        original = self.job()
        first = dispatch.claim('rule', 'control-a:rule')
        self.expire(first)
        second = dispatch.claim('rule', 'control-b:rule')
        self.assertEqual(second.pk, original.pk)
        self.assertEqual(second.recovery_count, 1)
        self.assertNotEqual(second.lease_token, first.lease_token)
        self.assertEqual(dispatch.active_job(first).update(status='SUCCEEDED'), 0)
        self.expire(second)
        third = dispatch.claim('rule', 'control-a:rule')
        self.assertEqual(third.recovery_count, 2)
        self.expire(third)
        self.assertIsNone(dispatch.claim('rule'))
        original.refresh_from_db()
        self.assertEqual(original.error['code'], 'WORKER_RETRY_EXHAUSTED')

    @patch.dict('os.environ', {'GEMINI_API_KEY': 'test-only'})
    def test_ambiguous_call_is_not_retried_and_keeps_its_permit(self):
        original = self.job('GEMINI_RECONFIGURE')
        claimed = dispatch.claim('gemini', 'control-a:gemini')
        self.assertEqual(dispatch.begin_provider(claimed), 0)
        self.expire(claimed)
        self.job('GEMINI_RECONFIGURE')
        self.assertIsNone(dispatch.claim('gemini', 'control-b:gemini'))
        original.refresh_from_db()
        self.assertEqual(original.error['code'], 'PROVIDER_OUTCOME_UNKNOWN')
        self.assertGreater(original.provider_lease_until, timezone.now())
        self.assertEqual(dispatch.active_job(claimed).update(status='SUCCEEDED'), 0)
        DispatchControl.objects.filter(pk='gemini').update(next_provider_at=timezone.now()-timedelta(seconds=1))
        Job.objects.filter(pk=original.pk).update(provider_lease_until=timezone.now()-timedelta(seconds=1))
        self.assertIsNotNone(dispatch.claim('gemini', 'control-b:gemini'))

    @patch.dict('os.environ', {'GEMINI_API_KEY': 'test-only'})
    def test_confirmed_response_releases_slot_but_interval_is_shared(self):
        self.job('GEMINI_RECONFIGURE')
        first = dispatch.claim('gemini', 'control-a:gemini')
        self.assertEqual(dispatch.begin_provider(first), 0)
        dispatch.end_provider(first)
        dispatch.active_job(first).update(status='SUCCEEDED')
        self.job('GEMINI_RECONFIGURE')
        self.assertIsNone(dispatch.claim('gemini', 'control-b:gemini'))
        DispatchControl.objects.filter(pk='gemini').update(next_provider_at=timezone.now()-timedelta(seconds=1))
        second = dispatch.claim('gemini', 'control-b:gemini')
        self.assertEqual(dispatch.begin_provider(second), 0)
        self.assertEqual(Job.objects.filter(provider_lease_until__gt=timezone.now()).count(), 1)

    @override_settings(RECOMMENDATION_MAX_QUEUED_RULE=1)
    def test_admission_counts_only_queued_jobs_and_is_per_lane(self):
        self.job()
        with transaction.atomic(), self.assertRaises(DomainError) as error: dispatch.admit('RULE_BASED')
        self.assertEqual(error.exception.code, 'RECOMMENDATION_QUEUE_FULL')
        with transaction.atomic(): dispatch.admit('GEMINI_RECONFIGURE')
        dispatch.claim('rule')
        with transaction.atomic(): dispatch.admit('RULE_BASED')

    def test_heartbeat_cannot_extend_past_attempt_timeout(self):
        self.job()
        job = dispatch.claim('rule', 'control-a:rule')
        job.claimed_at = timezone.now()-timedelta(seconds=170)
        stopped = Mock(); stopped.wait.side_effect = [False, True]
        heartbeat(job, stopped)
        latest = Job.objects.get(pk=job.pk)
        self.assertLessEqual(latest.lease_expires_at, job.claimed_at+timedelta(seconds=180))

    def test_status_observation_is_read_only_and_does_not_expose_input(self):
        job = self.job(); job.input = {'secret': 'must-not-appear'}; job.save(update_fields=['input'])
        result = io.StringIO()
        with CaptureQueriesContext(connection) as queries: call_command('check_recommendations', stdout=result)
        report = json.loads(result.getvalue())
        self.assertEqual(report['queues']['rule']['states']['QUEUED'], 1)
        self.assertFalse(report['worker_liveness_verified'])
        self.assertNotIn('must-not-appear', result.getvalue())
        self.assertFalse(any(query['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')) for query in queries))

    def test_expired_lease_is_reported_as_attention(self):
        self.job(); self.expire(dispatch.claim('rule'))
        with self.assertRaises(CommandError): call_command('check_recommendations', stdout=io.StringIO())


@override_settings(LOCAL_DEMO=True, INTEGRATION_ENABLED=False, WEATHER_PROVIDER='', RECOMMENDATION_MAX_QUEUED_RULE=1)
class QueueAdmissionApiTests(TransactionTestCase):
    def test_rejected_request_rolls_back_family_and_can_be_retried(self):
        call_command('seed_c_demo', stdout=io.StringIO())
        client = Client(); client.get('/api/c-demo/context')
        def post(key):
            return client.post('/api/recommendation-jobs', {'weather_influence_mode': 'OFF'},
                               content_type='application/json', HTTP_IDEMPOTENCY_KEY=key)
        first = post('first'); self.assertEqual(first.status_code, 202)
        rejected = post('retryable'); self.assertEqual(rejected.status_code, 503)
        self.assertEqual(rejected.json()['code'], 'RECOMMENDATION_QUEUE_FULL')
        self.assertEqual(Family.objects.count(), 1)
        self.assertEqual(Idempotency.objects.count(), 1)
        dispatch.claim('rule', 'control-a:rule')
        self.assertEqual(post('retryable').status_code, 202)


@override_settings(LOCAL_DEMO=True, GEMINI_ENABLED=False)
class WorkerCommandTests(SimpleTestCase):
    def test_once_forwards_lane_and_worker_identity(self):
        with patch('backend.recommendation.management.commands.run_recommendations.run_one', return_value=False) as run:
            call_command('run_recommendations', once=True, queue='rule', worker_id='control-a:rule', stdout=io.StringIO())
        run.assert_called_once_with('rule', 'control-a:rule')

    @override_settings(RECOMMENDATION_HEARTBEAT_SECONDS=30)
    def test_unsafe_heartbeat_configuration_is_rejected_before_database_use(self):
        with self.assertRaisesRegex(CommandError, 'recommendation_heartbeat'):
            call_command('run_recommendations', once=True, stdout=io.StringIO())

    def test_worker_identity_cannot_inject_log_lines(self):
        with self.assertRaisesRegex(CommandError, 'worker_id'):
            call_command('run_recommendations', once=True, worker_id='injected\nlog', stdout=io.StringIO())

    def test_sigterm_drains_current_job_and_stops_before_next_claim(self):
        previous = signal.getsignal(signal.SIGTERM)
        for stage in ('warmup', 'job'):
            def finish_current(*args):
                signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
                return True
            with self.subTest(stage=stage), \
                    patch('backend.recommendation.management.commands.run_recommendations.run_one',
                          side_effect=finish_current) as run, \
                    patch('backend.recommendation.management.commands.run_recommendations.warm_current_catalog',
                          side_effect=finish_current if stage == 'warmup' else None):
                call_command('run_recommendations', queue='rule', worker_id='control-a:rule', stdout=io.StringIO())
            self.assertEqual(run.call_count, 0 if stage == 'warmup' else 1)
            self.assertIs(signal.getsignal(signal.SIGTERM), previous)


@skipUnlessDBFeature('has_select_for_update_skip_locked')
class PostgresDispatchTests(DispatchTests):
    """Each concurrent caller owns an independent PostgreSQL session."""
    def concurrent(self, function, count=2):
        barrier = threading.Barrier(count)
        def invoke(index):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return function(index)
            finally: connection.close()
        with ThreadPoolExecutor(max_workers=count) as pool:
            futures = [pool.submit(invoke, index) for index in range(count)]
            return [future.result(timeout=15) for future in futures]

    def test_same_job_is_claimed_by_exactly_one_session(self):
        job = self.job()
        def claim(index):
            current = dispatch.claim('rule', f'control-{index}:rule')
            return current.pk if current else None
        results = self.concurrent(claim)
        self.assertEqual(results.count(job.pk), 1)
        self.assertEqual(results.count(None), 1)

    def test_locked_job_is_skipped_instead_of_blocking_other_worker(self):
        first, second = self.job(), self.job()
        def claim():
            try: return dispatch.claim('rule', 'control-b:rule').pk
            finally: connection.close()
        with transaction.atomic():
            Job.objects.select_for_update().get(pk=first.pk)
            with ThreadPoolExecutor(max_workers=1) as pool:
                self.assertEqual(pool.submit(claim).result(timeout=5), second.pk)

    def test_gemini_claim_limit_is_shared_across_sessions(self):
        DispatchControl.objects.create(name='gemini')
        for _ in range(4): self.job('GEMINI_RECONFIGURE')
        def claim(index):
            job = dispatch.claim('gemini', f'control-{index}:gemini')
            return job.pk if job else None
        self.assertEqual(sum(value is not None for value in self.concurrent(claim, 4)), 1)

    @override_settings(GEMINI_MAX_CONCURRENT=2)
    @patch.dict('os.environ', {'GEMINI_API_KEY': 'test-only'})
    def test_provider_start_interval_is_atomic_across_sessions(self):
        self.job('GEMINI_RECONFIGURE'); self.job('GEMINI_RECONFIGURE')
        jobs = [dispatch.claim('gemini', f'control-{i}:gemini') for i in range(2)]
        delays = self.concurrent(lambda index: dispatch.begin_provider(jobs[index]))
        self.assertEqual(delays.count(0), 1)
        self.assertEqual(sum(delay > 0 for delay in delays), 1)

    @override_settings(RECOMMENDATION_MAX_QUEUED_RULE=1)
    def test_admission_capacity_cannot_be_exceeded_by_two_api_sessions(self):
        DispatchControl.objects.create(name='admission-rule')
        def enqueue(index):
            try:
                with transaction.atomic():
                    dispatch.admit('RULE_BASED'); self.job()
                return 'accepted'
            except DomainError as exc: return exc.code
        self.assertCountEqual(self.concurrent(enqueue), ['accepted', 'RECOMMENDATION_QUEUE_FULL'])

    def test_two_processes_finish_two_jobs_without_duplicate_results(self):
        from backend.recommendation.models import Playlist
        call_command('seed_c_demo', stdout=io.StringIO())
        client = Client(); client.get('/api/c-demo/context')
        for index in range(2):
            response = client.post('/api/recommendation-jobs', {'weather_influence_mode': 'OFF'},
                content_type='application/json', HTTP_IDEMPOTENCY_KEY=f'process-{index}')
            self.assertEqual(response.status_code, 202, response.content)
        # A child gets the runner's isolated test DB, never the developer's configured database.
        database = connection.settings_dict
        self.assertTrue(database['NAME'].startswith('test_'))
        env = os.environ.copy()
        env.update(C_LOCAL_DEMO='0', INTEGRATION_ENABLED='0', DJANGO_SECRET_KEY='isolated-worker-process-test',
                   PGDATABASE=database['NAME'], PGHOST=database['HOST'], PGPORT=str(database['PORT']),
                   PGUSER=database['USER'], PGPASSWORD=database['PASSWORD'], GEMINI_ENABLED='0',
                   SEARCH_SECONDS='20', SEARCH_MAX_CANDIDATES='96', DJANGO_SETTINGS_MODULE='backend.cafe.settings')
        env['PGSSLMODE'] = database.get('OPTIONS', {}).get('sslmode', 'disable')
        snippet = '''
import os,sys,time
from pathlib import Path
import django
django.setup()
from django.core.management import call_command
from backend.recommendation import worker
from unittest.mock import patch
folder,identity=Path(sys.argv[1]),sys.argv[2]
choose=worker.choose
def synchronized_choose(*args,**kwargs):
    (folder/identity).write_text('claimed')
    deadline=time.monotonic()+15
    while len(list(folder.iterdir()))<2:
        if time.monotonic()>deadline: raise RuntimeError('parallel worker did not arrive')
        time.sleep(.02)
    return choose(*args,**kwargs)
with patch.object(worker,'choose',side_effect=synchronized_choose):
    call_command('run_recommendations',once=True,queue='rule',worker_id=identity)
'''
        with tempfile.TemporaryDirectory(prefix='recommendation-process-test-') as folder:
            processes = []
            try:
                for identity in ('control-a:rule', 'control-b:rule'):
                    processes.append(subprocess.Popen([sys.executable, '-B', '-c', snippet, folder, identity.replace(':', '-')],
                        env=env, cwd=Path(__file__).resolve().parents[3], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
                for process in processes:
                    output, error = process.communicate(timeout=35)
                    self.assertEqual(process.returncode, 0, 'worker process failed: ' + error[-2500:])
            finally:
                for process in processes:
                    if process.poll() is None: process.kill(); process.wait(timeout=5)
        jobs = Job.objects.filter(method='RULE_BASED')
        self.assertEqual(jobs.filter(status='SUCCEEDED').count(), 2)
        self.assertEqual(len(set(jobs.values_list('worker_id', flat=True))), 2)
        self.assertEqual(Playlist.objects.count(), 2)
        for job in jobs: self.assertEqual(Playlist.objects.filter(job=job).count(), 1)
