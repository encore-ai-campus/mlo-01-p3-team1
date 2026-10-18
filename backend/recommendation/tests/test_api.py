from datetime import timedelta
import os
from unittest.mock import patch
from django.test import TransactionTestCase, Client, override_settings
from django.core.management import call_command
from django.utils import timezone
from backend.recommendation.models import Job, Playlist, PendingEvent, Family, DemoFeedback, Catalog
from backend.recommendation.worker import run_one, verified_catalog, warm_current_catalog
from backend.recommendation.service import current_catalog
from backend.recommendation.errors import DomainError
from backend.recommendation.policy import GENRES, THEMES
from backend.recommendation.weather import obtain


@override_settings(LOCAL_DEMO=True,WEATHER_PROVIDER='',SEARCH_SECONDS=20,SEARCH_MAX_CANDIDATES=96,GEMINI_ENABLED=False)
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
    def test_verified_catalog_reuse_and_hash_change(self):
        catalog=Catalog.objects.defer('tracks').get(pk='c-demo-v3')
        tracks=verified_catalog(catalog)
        with patch('backend.recommendation.worker.hashlib.sha256',side_effect=AssertionError('unexpected rehash')):
            self.assertIs(verified_catalog(catalog),tracks)
        catalog.sha256='0'*64;catalog.save(update_fields=['sha256'])
        with self.assertRaises(DomainError) as failure: verified_catalog(catalog)
        self.assertEqual(failure.exception.code,'CATALOG_INVALID')
    def catalog_copy(self, version, source_ref, is_test=True, ready=True):
        source=Catalog.objects.get(pk='c-demo-v3')
        return Catalog.objects.create(version=version,tracks=source.tracks,sha256=source.sha256,
            source_ref=source_ref,source_sha256=source.source_sha256,is_test=is_test,ready=ready)
    def test_general_recommendation_and_warmup_skip_latest_fixed_playback_catalog(self):
        self.catalog_copy('general-old','local-preview:general-old.csv')
        expected=self.catalog_copy('general-current','local-preview:general-current.csv')
        fixed=self.catalog_copy('fixed-playback','local-preview:youtube-playback-selection:source.csv')
        self.catalog_copy('not-ready','local-preview:pending.csv',ready=False)
        self.catalog_copy('production-newer','released:catalog',is_test=False)
        self.assertEqual(current_catalog().pk,expected.pk)
        with patch('backend.recommendation.worker.verified_catalog') as verify:
            warm_current_catalog()
        self.assertEqual(verify.call_args.args[0].pk,expected.pk)
        job=Job.objects.get(pk=self.basic())
        self.assertEqual(job.catalog_id,expected.pk)
        self.assertTrue(Catalog.objects.filter(pk=fixed.pk,ready=True).exists())
    def test_fixed_playback_catalog_alone_cannot_supply_general_recommendation(self):
        fixed=self.catalog_copy('fixed-only','local-preview:youtube-playback-selection:source.csv')
        Catalog.objects.exclude(pk=fixed.pk).delete()
        with patch('backend.recommendation.worker.verified_catalog') as verify:
            warm_current_catalog()
        verify.assert_not_called()
        response=self.post('/api/recommendation-jobs',{'region_id':'demo-region'},'fixed-only')
        self.assertEqual(response.status_code,503,response.content)
        self.assertEqual(response.json()['code'],'POLICY_NOT_READY')
        self.assertIn('일반 추천용 전체 음악 카탈로그',response.json()['message'])
        self.assertFalse(Job.objects.exists())
        self.assertFalse(Family.objects.exists())
    def test_catalog_selection_keeps_production_catalog_scope(self):
        self.catalog_copy('production-old','released:old',is_test=False)
        newest=self.catalog_copy('production-current','released:current',is_test=False)
        self.catalog_copy('local-fixed','local-preview:youtube-playback-selection:source.csv')
        with override_settings(LOCAL_DEMO=False):
            self.assertEqual(current_catalog().pk,newest.pk)
    @override_settings(GEMINI_ENABLED=True,GEMINI_TIMEOUT_MS=60000,GEMINI_MAX_CANDIDATES=200)
    @patch.dict(os.environ,{'GEMINI_API_KEY':'test-only','GEMINI_MAX_OUTPUT_TOKENS':'8192'})
    def test_preview_parent_keeps_catalog_when_new_general_catalog_is_published(self):
        parent=self.result()
        original=parent.job.catalog
        original.source_ref='local-preview:source.csv';original.save(update_fields=['source_ref'])
        parent.snapshot['preview_only']=True;parent.save(update_fields=['snapshot'])
        self.catalog_copy('general-newer','local-preview:newer.csv')
        self.catalog_copy('fixed-newest','local-preview:youtube-playback-selection:source.csv')
        response=self.post(f'/api/playlists/{parent.pk}/regenerations',{'exclusion_revision':0},'keep-parent')
        self.assertEqual(response.status_code,202,response.content)
        regenerated=Job.objects.get(pk=response.json()['job_id'])
        self.assertEqual(regenerated.parent_id,parent.pk)
        self.assertEqual(regenerated.catalog_id,original.pk)
    @override_settings(GEMINI_ENABLED=True,GEMINI_TIMEOUT_MS=60000,GEMINI_MAX_CANDIDATES=200)
    @patch.dict(os.environ,{'GEMINI_API_KEY':'test-only','GEMINI_MAX_OUTPUT_TOKENS':'8192'})
    def test_historical_fixed_playback_result_stays_readable_and_parent_fixed(self):
        parent=self.result()
        original=parent.job.catalog
        original.source_ref='local-preview:youtube-playback-selection:source.csv'
        original.save(update_fields=['source_ref'])
        parent.snapshot['preview_only']=True;parent.save(update_fields=['snapshot'])
        self.catalog_copy('general-after-fixed','local-preview:general.csv')
        detail=self.client.get(f'/api/playlists/{parent.pk}')
        self.assertEqual(detail.status_code,200,detail.content)
        self.assertEqual(detail.json()['items'],parent.snapshot['items'])
        self.assertEqual(detail.json()['total_ms'],parent.snapshot['total_ms'])
        response=self.post(f'/api/playlists/{parent.pk}/regenerations',{'exclusion_revision':0},'historical-parent')
        self.assertEqual(response.status_code,202,response.content)
        self.assertEqual(Job.objects.get(pk=response.json()['job_id']).catalog_id,original.pk)
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
    def test_off_mode_does_not_depend_on_weather(self):
        with patch('backend.recommendation.service.obtain',side_effect=RuntimeError('weather unavailable')):
            response=self.post('/api/recommendation-jobs',{'region_id':'demo-region','weather_influence_mode':'OFF'},'off')
        self.assertEqual(response.status_code,202,response.content)
        self.assertTrue(run_one())
        playlist=Playlist.objects.get(job_id=response.json()['job_id'])
        self.assertIsNone(playlist.snapshot['context']['weather'])
        self.assertEqual(playlist.snapshot['context']['options']['weather_influence_mode'],'OFF')
        self.assertEqual(playlist.snapshot['total_ms'],10800000)
        self.assertTrue(all(item['scores']['W'] is None for item in playlist.snapshot['items']))
    def test_all_selected_tags_keep_raw_selection_but_use_any_filter(self):
        response=self.post('/api/recommendation-jobs',{
            'region_id':'demo-region','selected_theme_codes':list(THEMES),
            'selected_genre_codes':list(GENRES)},'all-tags')
        self.assertEqual(response.status_code,202,response.content)
        family=Job.objects.get(pk=response.json()['job_id']).family
        self.assertEqual(family.options['selected_theme_codes'],[])
        self.assertEqual(family.options['selected_genre_codes'],[])
        self.assertEqual(set(family.raw_selection['selected_theme_codes']),set(THEMES))
        self.assertEqual(set(family.raw_selection['selected_genre_codes']),set(GENRES))
        conflict=self.post('/api/recommendation-jobs',{'region_id':'demo-region'},'all-tags')
        self.assertEqual(conflict.status_code,409)
    def test_strict_inputs_and_country_language_rejection(self):
        for body,expected in [({'region_id':'demo-region','language':'ko'},400),
                               ({'region_id':'demo-region','unknown':True},422),
                               ({'region_id':False},422),({'region_id':'demo-region','selected_genre_codes':'JAZZ'},422)]:
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
    @override_settings(GEMINI_ENABLED=True,GEMINI_TIMEOUT_MS=60000,GEMINI_MAX_CANDIDATES=200)
    @patch.dict(os.environ,{'GEMINI_API_KEY':'test-only','GEMINI_MAX_OUTPUT_TOKENS':'8192'})
    def test_csv_uses_gemini_and_preserves_catalog_seed_and_local_approval(self):
        p=self.result()
        catalog=p.job.catalog
        catalog.source_ref='local-preview:spotify_dataset.csv';catalog.save(update_fields=['source_ref'])
        p.snapshot['preview_only']=True;p.snapshot['validation_passed']=False;p.save(update_fields=['snapshot'])
        response=self.post(f'/api/playlists/{p.pk}/regenerations',{'exclusion_revision':0},'csv-alternative')
        self.assertEqual(response.status_code,202,response.content)
        job=Job.objects.get(pk=response.json()['job_id'])
        self.assertEqual(job.method,'GEMINI_RECONFIGURE')
        self.assertEqual(job.parent_id,p.pk)
        self.assertEqual(job.catalog_id,catalog.pk)
        self.assertEqual(job.input['seed'],p.job.input['seed'])
        parent_ids={t['track_id'] for t in p.snapshot['items']}
        def proposal(candidates,context,ids):
            ordered=sorted(candidates,key=lambda t:t['track_id'] in parent_ids)[:45]
            selected=[t['track_id'] for t in ordered]
            return {'track_ids':selected,'summary':'Gemini 응답 검증',
                    'track_reasons':[{'track_id':x,'reason':'선호 반영'} for x in selected]}, {'attempts':1}
        with patch('backend.recommendation.worker.propose',side_effect=proposal) as provider:
            self.assertTrue(run_one())
        provider.assert_called_once()
        job.refresh_from_db();self.assertEqual(job.status,'SUCCEEDED',job.error)
        result=Playlist.objects.get(job=job)
        self.assertEqual(result.snapshot['generation_method'],'GEMINI_RECONFIGURE')
        self.assertEqual(result.snapshot['model'],'gemini-3.8-flash')
        self.assertGreaterEqual(len({t['track_id'] for t in result.snapshot['items']}-parent_ids),9)
        approval=self.post(f'/api/playlists/{p.pk}/approval',{'approval_revision':0,'exclusion_revision':0},'csv-approval')
        self.assertEqual(approval.status_code,200,approval.content)
        self.assertEqual(approval.json()['approved_playlist_id'],p.pk)

    def test_csv_missing_key_does_not_fall_back_to_rules(self):
        p=self.result();catalog=p.job.catalog
        catalog.source_ref='local-preview:spotify_dataset.csv';catalog.save(update_fields=['source_ref'])
        p.snapshot['preview_only']=True;p.save(update_fields=['snapshot'])
        response=self.post(f'/api/playlists/{p.pk}/regenerations',{'exclusion_revision':0},'csv-no-key')
        self.assertEqual(response.status_code,503,response.content)
        self.assertEqual(Job.objects.count(),1)
        self.assertEqual(Playlist.objects.count(),1)

    def test_local_feedback_restores_reactions_and_rating_without_changing_approval(self):
        p=self.result()
        p.snapshot['preview_only']=True;p.snapshot['validation_passed']=False;p.save(update_fields=['snapshot'])
        track=p.snapshot['items'][0]['track_id']
        feedback=f'/api/playlists/{p.pk}/feedback'
        reaction=f'/api/playlists/{p.pk}/tracks/{track}/reaction'
        rating=f'/api/playlists/{p.pk}/rating'
        initial=self.client.get(feedback)
        self.assertEqual(initial.status_code,200,initial.content)
        self.assertEqual(len(initial.json()['track_reactions']),len(p.snapshot['items']))
        self.assertEqual(initial.json()['track_reactions'][0]['reaction'],None)
        self.assertEqual(initial.json()['playlist_rating'],{'rating':None,'revision':0})
        def put(path,body,key):
            return self.client.put(path,body,content_type='application/json',HTTP_IDEMPOTENCY_KEY=key)
        like=put(reaction,{'reaction':'LIKE','expected_revision':0},'like')
        self.assertEqual(like.status_code,200,like.content)
        self.assertEqual(like.json()['revision'],1)
        self.assertEqual(put(reaction,{'reaction':'LIKE','expected_revision':0},'like').json(),like.json())
        self.assertEqual(put(reaction,{'reaction':'LIKE','expected_revision':1},'same').json()['event_id'],None)
        self.assertEqual(put(reaction,{'reaction':None,'expected_revision':1},'clear').json()['revision'],2)
        self.assertEqual(put(reaction,{'reaction':'DISLIKE','expected_revision':2},'dislike').json()['revision'],3)
        self.assertEqual(put(reaction,{'reaction':'LIKE','expected_revision':3},'like-again').json()['revision'],4)
        conflict=put(reaction,{'reaction':'DISLIKE','expected_revision':1},'stale')
        self.assertEqual(conflict.status_code,409)
        self.assertEqual(conflict.json()['code'],'FEEDBACK_REVISION_CONFLICT')
        for invalid in [0,6,1.5,'5',True]:
            self.assertEqual(put(rating,{'rating':invalid,'expected_revision':0},str(invalid)).status_code,422)
        self.assertEqual(put(rating,{'rating':5,'expected_revision':0},'five').json()['revision'],1)
        self.assertEqual(put(rating,{'rating':None,'expected_revision':1},'rating-clear').json()['revision'],2)
        restored=self.client.get(feedback).json()
        self.assertEqual(restored['track_reactions'][0],{'track_id':track,'reaction':'LIKE','revision':4})
        self.assertEqual(restored['playlist_rating'],{'rating':None,'revision':2})
        self.assertIsNone(Family.objects.get(pk=p.family_id).approved_playlist_id)
        self.assertEqual(DemoFeedback.objects.filter(playlist=p).count(),2)
        self.assertEqual(PendingEvent.objects.filter(event_type__startswith='TRACK_REACTION').count(),4)
        self.assertEqual(Client().get(feedback).status_code,404)
        self.assertEqual(put(f'/api/playlists/{p.pk}/tracks/not-in-result/reaction',
                             {'reaction':'LIKE','expected_revision':0},'wrong-track').status_code,404)
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
    def test_weather_change_during_generation_rejects_stale_result(self):
        pk=self.basic()
        changed=obtain('demo-region',timezone.now())
        changed['current']['pty']=1
        with patch('backend.recommendation.worker.obtain',return_value=changed):
            run_one()
        job=Job.objects.get(pk=pk)
        self.assertEqual(job.status,'EXPIRED')
        self.assertFalse(Playlist.objects.exists())
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
