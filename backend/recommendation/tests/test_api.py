from datetime import timedelta
from unittest.mock import patch
from django.test import TransactionTestCase, Client, override_settings
from django.core.management import call_command
from django.utils import timezone
from backend.recommendation.models import Job, Playlist, PendingEvent, Family
from backend.recommendation.worker import run_one
from backend.recommendation.errors import DomainError


@override_settings(LOCAL_DEMO=True,SEARCH_SECONDS=20,SEARCH_MAX_CANDIDATES=96,GEMINI_ENABLED=False)
class ApiTests(TransactionTestCase):
    def setUp(self):
        call_command('seed_c_demo',verbosity=0)
        self.client=Client();self.client.get('/api/c-demo/context')
    def post(self,path,body,key='key',client=None):
        return (client or self.client).post(path,body,content_type='application/json',HTTP_IDEMPOTENCY_KEY=key)
    def basic(self):
        r=self.post('/api/recommendation-jobs',{'region_id':'demo-region'})
        self.assertEqual(r.status_code,202,r.content)
        return r.json()['job_id']
    def result(self):
        job=self.basic();self.assertTrue(run_one())
        p=Playlist.objects.get(job_id=job)
        return p
    def test_default_flow_idempotency_ownership(self):
        j=self.basic()
        duplicate=self.post('/api/recommendation-jobs',{'region_id':'demo-region'})
        self.assertEqual(duplicate.json()['job_id'],j);self.assertEqual(Job.objects.count(),1)
        self.assertTrue(run_one())
        p=Playlist.objects.get(job_id=j)
        self.assertEqual(len(p.snapshot['items']),45)
        self.assertEqual(p.snapshot['total_ms'],10800000)
        self.assertEqual(p.family.allowed_genres,['JAZZ']);self.assertEqual(p.family.allowed_speeds,['medium'])
        other=Client()
        self.assertEqual(other.get(f'/api/playlists/{p.pk}').status_code,404)
        changed=self.post('/api/recommendation-jobs',{'region_id':'demo-region','tempo_preference':'slow'})
        self.assertEqual(changed.status_code,409)
    def test_strict_inputs_and_country_language_rejection(self):
        for body,expected in [({'region_id':'demo-region','language':'ko'},400),
                               ({'region_id':'demo-region','unknown':True},422),
                               ({},400),({'region_id':'demo-region','selected_genre_codes':'JAZZ'},422)]:
            r=self.post('/api/recommendation-jobs',body)
            self.assertEqual(r.status_code,expected,r.content)
        self.assertFalse(Job.objects.exists())
    def test_exclusion_noop_revision_retry_and_approval_block(self):
        p=self.result();path=f'/api/playlist-families/{p.family_id}/exclusions';track=p.snapshot['items'][0]['track_id']
        body={'source_playlist_id':p.pk,'expected_revision':0,'excluded_track_ids':[track]}
        r=self.client.put(path,body,content_type='application/json',HTTP_IDEMPOTENCY_KEY='exclude')
        self.assertEqual(r.status_code,200,r.content);self.assertEqual(r.json()['revision'],1)
        self.assertEqual(PendingEvent.objects.count(),1)
        retry=self.client.put(path,body,content_type='application/json',HTTP_IDEMPOTENCY_KEY='exclude')
        self.assertEqual(retry.json(),r.json());self.assertEqual(PendingEvent.objects.count(),1)
        noop=self.client.put(path,{**body,'expected_revision':1},content_type='application/json',HTTP_IDEMPOTENCY_KEY='noop')
        self.assertEqual(noop.json()['revision'],1);self.assertEqual(PendingEvent.objects.count(),1)
        approval=self.post(f'/api/playlists/{p.pk}/approval',{'approval_revision':0,'exclusion_revision':1},'approve')
        self.assertEqual(approval.status_code,409)
        cancel=self.client.put(path,{**body,'expected_revision':1,'excluded_track_ids':[]},content_type='application/json',HTTP_IDEMPOTENCY_KEY='cancel')
        self.assertEqual(cancel.status_code,200,cancel.content)
        self.assertIsNotNone(PendingEvent.objects.get(event_type='TRACK_EXCLUSION_CANCELLED').payload['related_exclusion_event_id'])
        approval=self.post(f'/api/playlists/{p.pk}/approval',{'approval_revision':0,'exclusion_revision':2},'approve2')
        self.assertEqual(approval.status_code,200,approval.content)
        repeated=self.post(f'/api/playlists/{p.pk}/approval',{'approval_revision':0,'exclusion_revision':2},'approve2')
        self.assertEqual(repeated.json(),approval.json())
    def test_cycle_change_409_before_provider_and_failure_preserves_parent(self):
        p=self.result()
        r=self.post(f'/api/playlists/{p.pk}/regenerations',{'exclusion_revision':0,'tempo_preference':'slow'},'regen')
        self.assertEqual(r.status_code,409,r.content)
        r=self.post(f'/api/playlists/{p.pk}/regenerations',{'exclusion_revision':0},'regen2')
        self.assertEqual(r.status_code,503,r.content)
        self.assertEqual(Playlist.objects.count(),1);self.assertEqual(Job.objects.count(),1)
    def test_stale_and_invalid_exclusion_roll_back(self):
        p=self.result();path=f'/api/playlist-families/{p.family_id}/exclusions'
        for rev,ids,expected in [(False,[],422),(5,[],409),(0,['outside'],422)]:
            r=self.client.put(path,{'source_playlist_id':p.pk,'expected_revision':rev,'excluded_track_ids':ids},content_type='application/json',HTTP_IDEMPOTENCY_KEY='x')
            self.assertEqual(r.status_code,expected,r.content)
        self.assertEqual(PendingEvent.objects.count(),0)
    def test_csrf_is_required_for_anonymous_mutation(self):
        client=Client(enforce_csrf_checks=True)
        context=client.get('/api/c-demo/context').json()
        r=self.post('/api/recommendation-jobs',{'region_id':'demo-region'},client=client)
        self.assertEqual(r.status_code,403)
        r=client.post('/api/recommendation-jobs',{'region_id':'demo-region'},content_type='application/json',HTTP_IDEMPOTENCY_KEY='csrf',HTTP_X_CSRFTOKEN=context['csrf_token'])
        self.assertEqual(r.status_code,202,r.content)
    def test_expired_job_does_not_generate_result(self):
        pk=self.basic();j=Job.objects.get(pk=pk);j.input['weather']['valid_until']=(timezone.now()-timedelta(seconds=1)).isoformat();j.save()
        run_one();j.refresh_from_db();self.assertEqual(j.status,'EXPIRED');self.assertFalse(Playlist.objects.exists())
    def test_snapshot_preserved_after_catalog_mutation(self):
        p=self.result();name=p.snapshot['items'][0]['track_name'];catalog=p.job.catalog
        catalog.tracks[0]['track_name']='바뀐 현재 이름';catalog.save()
        response=self.client.get(f'/api/playlists/{p.pk}').json()
        self.assertEqual(response['items'][0]['track_name'],name)
    def test_expired_worker_cannot_fail_job_and_recovery_can_finish(self):
        pk=self.basic()
        def expire_then_fail(*args):
            Job.objects.filter(pk=pk).update(lease_expires_at=timezone.now()-timedelta(seconds=1))
            raise DomainError('SEARCH_INCOMPLETE','검색을 완료하지 못했어요.',503)
        with patch('backend.recommendation.worker.choose',side_effect=expire_then_fail):
            run_one()
        job=Job.objects.get(pk=pk)
        self.assertEqual(job.status,'RUNNING');self.assertIsNone(job.error)
        self.assertFalse(Playlist.objects.exists())
        run_one();job.refresh_from_db()
        self.assertEqual(job.status,'SUCCEEDED');self.assertEqual(job.lease_generation,2)
    def test_expired_worker_exception_does_not_overwrite_recoverable_job(self):
        pk=self.basic()
        def expire_then_crash(*args):
            Job.objects.filter(pk=pk).update(lease_expires_at=timezone.now()-timedelta(seconds=1))
            raise RuntimeError('worker interrupted')
        with patch('backend.recommendation.worker.choose',side_effect=expire_then_crash),self.assertRaises(RuntimeError):
            run_one()
        job=Job.objects.get(pk=pk)
        self.assertEqual(job.status,'RUNNING');self.assertIsNone(job.error)
