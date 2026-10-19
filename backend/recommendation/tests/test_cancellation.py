from copy import deepcopy
from unittest.mock import patch
from django.core.management import call_command
from django.test import Client, TransactionTestCase, override_settings
from backend.recommendation import worker
from backend.recommendation.errors import DomainError
from backend.recommendation.models import Family, Job, Playlist
from backend.recommendation.service import enqueue


@override_settings(LOCAL_DEMO=True,INTEGRATION_ENABLED=False,OWNER_RESOLVER='',EVENT_SINK='',
                   WEATHER_PROVIDER='',SEARCH_SECONDS=20,SEARCH_MAX_CANDIDATES=96,GEMINI_ENABLED=False)
class CancellationTests(TransactionTestCase):
    def setUp(self):
        call_command('seed_c_demo',verbosity=0)
        self.client=Client();self.client.get('/api/c-demo/context')

    def post(self,path,body,key='create',client=None,**headers):
        return (client or self.client).post(path,body,content_type='application/json',
            HTTP_IDEMPOTENCY_KEY=key,**headers)

    def job(self):
        response=self.post('/api/recommendation-jobs',{'region_id':'demo-region'})
        self.assertEqual(response.status_code,202,response.content)
        return response.json()['job_id']

    def cancel(self,pk,key='cancel'):
        return self.post(f'/api/recommendation-jobs/{pk}/cancel',{},key)

    def test_queued_cancel_is_terminal_and_retry_safe(self):
        pk=self.job();response=self.cancel(pk)
        self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(response.json()['status'],'CANCELLED')
        self.assertEqual(self.cancel(pk).json(),response.json())
        self.assertEqual(self.cancel(pk,'second-key').json(),response.json())
        self.assertFalse(worker.run_one());self.assertFalse(Playlist.objects.exists())
        detail=self.client.get(f'/api/recommendation-jobs/{pk}').json()
        self.assertEqual(detail['status'],'CANCELLED');self.assertIsNone(detail['playlist_id'])

    def test_running_cancel_blocks_late_result_commit(self):
        pk=self.job();original=worker.choose
        def finish_after_cancel(*args,**kwargs):
            self.assertEqual(self.cancel(pk).json()['status'],'CANCELLED')
            return original(*args,**kwargs)
        with patch('backend.recommendation.worker.choose',side_effect=finish_after_cancel):
            self.assertTrue(worker.run_one())
        job=Job.objects.get(pk=pk)
        self.assertEqual(job.status,'CANCELLED');self.assertIsNone(job.lease_token)
        self.assertIsNone(job.lease_expires_at);self.assertIsNone(job.error)
        self.assertFalse(Playlist.objects.exists());self.assertFalse(worker.run_one())

    def test_worker_failure_cannot_overwrite_cancelled_status(self):
        pk=self.job()
        def fail_after_cancel(*args,**kwargs):
            self.cancel(pk)
            raise DomainError('SEARCH_INCOMPLETE','fixture failure',503)
        with patch('backend.recommendation.worker.choose',side_effect=fail_after_cancel):
            worker.run_one()
        job=Job.objects.get(pk=pk)
        self.assertEqual(job.status,'CANCELLED');self.assertIsNone(job.error)

    def test_other_owner_and_missing_job_both_return_404(self):
        pk=self.job();other=Client();other.get('/api/c-demo/context')
        foreign=self.post(f'/api/recommendation-jobs/{pk}/cancel',{},'other',client=other)
        missing=self.cancel('missing')
        self.assertEqual(foreign.status_code,404);self.assertEqual(missing.status_code,404)
        self.assertEqual(Job.objects.get(pk=pk).status,'QUEUED')

    def test_successful_result_is_preserved_when_completion_wins(self):
        pk=self.job();worker.run_one();before=deepcopy(Playlist.objects.get(job_id=pk).snapshot)
        response=self.cancel(pk)
        self.assertEqual(response.json()['status'],'SUCCEEDED')
        self.assertEqual(Playlist.objects.get(job_id=pk).snapshot,before)

    def test_cancel_regeneration_preserves_parent_exclusions_and_approval(self):
        pk=self.job();worker.run_one();parent=Playlist.objects.get(job_id=pk)
        family=parent.family;family.excluded=['keep-excluded'];family.exclusion_revision=2
        family.approved_playlist_id=parent.pk;family.approval_revision=3;family.save()
        before=deepcopy(parent.snapshot)
        accepted,_=enqueue(family,'test-regeneration',parent)
        self.assertEqual(self.cancel(accepted['job_id']).json()['status'],'CANCELLED')
        family.refresh_from_db();parent.refresh_from_db()
        self.assertEqual(family.excluded,['keep-excluded']);self.assertEqual(family.exclusion_revision,2)
        self.assertEqual(family.approved_playlist_id,parent.pk);self.assertEqual(family.approval_revision,3)
        self.assertEqual(parent.snapshot,before);self.assertEqual(Playlist.objects.count(),1)

    def test_csrf_and_idempotency_key_required(self):
        client=Client(enforce_csrf_checks=True);context=client.get('/api/c-demo/context').json()
        response=self.post('/api/recommendation-jobs',{'region_id':'demo-region'},client=client,
                           HTTP_X_CSRFTOKEN=context['csrf_token'])
        pk=response.json()['job_id'];path=f'/api/recommendation-jobs/{pk}/cancel'
        self.assertEqual(self.post(path,{},'cancel',client=client).status_code,403)
        response=client.post(path,{},content_type='application/json',HTTP_X_CSRFTOKEN=context['csrf_token'])
        self.assertEqual(response.status_code,422)
        self.assertEqual(Job.objects.get(pk=pk).status,'QUEUED')
        response=self.post(path,{},'cancel',client=client,HTTP_X_CSRFTOKEN=context['csrf_token'])
        self.assertEqual(response.status_code,200,response.content)

    def test_failed_and_expired_jobs_keep_their_terminal_state(self):
        pk=self.job()
        for state in ('FAILED','EXPIRED'):
            Job.objects.filter(pk=pk).update(status=state,error={'code':'fixture'})
            response=self.cancel(pk,state)
            self.assertEqual(response.json()['status'],state)
            self.assertEqual(Job.objects.get(pk=pk).error,{'code':'fixture'})
