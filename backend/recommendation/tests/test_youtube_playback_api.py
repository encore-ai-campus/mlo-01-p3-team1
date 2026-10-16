from unittest.mock import patch

from django.core.cache import cache
from django.core.management import call_command
from django.test import Client, TransactionTestCase, override_settings

from backend.recommendation.models import Family, Job, Playlist, PendingEvent
from backend.recommendation.worker import run_one


@override_settings(LOCAL_DEMO=True, SEARCH_SECONDS=20, SEARCH_MAX_CANDIDATES=96, YOUTUBE_DATA_API_KEY='', YOUTUBE_PLAYBACK_MODE='OPTIONAL_SEARCH')
class YoutubePlaybackApiTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        call_command('seed_c_demo', verbosity=0)
        self.client=Client()
        self.client.get('/api/c-demo/context')
        response=self.client.post('/api/recommendation-jobs', {'region_id':'demo-region'},
            content_type='application/json', HTTP_IDEMPOTENCY_KEY='playback-fixture')
        self.assertEqual(response.status_code,202,response.content)
        self.assertTrue(run_one())
        self.playlist=Playlist.objects.get(job_id=response.json()['job_id'])
        self.track=self.playlist.snapshot['items'][0]
        self.path=f'/api/playlists/{self.playlist.pk}/youtube-playback'

    def post(self, body, client=None):
        return (client or self.client).post(self.path, body, content_type='application/json')

    def test_catalog_candidate_works_without_key_and_preserves_music_state(self):
        # Synthetic ID is used only by the offline resolver contract test.
        self.track.update(youtube_video_id='testVID0001',youtube_match_status='VERIFIED')
        self.playlist.save(update_fields=['snapshot'])
        before=self.playlist.snapshot
        jobs=Job.objects.count()
        with patch('backend.recommendation.youtube_playback._api_json', side_effect=AssertionError('unexpected search')), \
                patch('backend.recommendation.provider.propose', side_effect=AssertionError('unexpected LLM')):
            response=self.post({'track_id':self.track['track_id']})
        self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(response.json()['status'],'READY')
        self.assertEqual(response.json()['candidates'][0]['video_id'],'testVID0001')
        self.playlist.refresh_from_db()
        self.assertEqual(self.playlist.snapshot,before)
        self.assertEqual(Job.objects.count(),jobs)
        self.assertFalse(PendingEvent.objects.exists())
        self.assertIsNone(Family.objects.get(pk=self.playlist.family_id).approved_playlist_id)

    def test_unmapped_track_reports_missing_search_connection_without_an_llm(self):
        with patch('backend.recommendation.youtube_playback._api_json', side_effect=AssertionError('unexpected search')):
            response=self.post({'track_id':self.track['track_id']})
        self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(response.json()['status'],'SEARCH_UNAVAILABLE')
        self.assertEqual(response.json()['reason'],'API_KEY_MISSING')
        self.assertEqual(response.json()['candidates'],[])

    def test_foreign_owner_and_track_outside_result_never_reach_resolver(self):
        with patch('backend.recommendation.api.resolve_playback_candidates') as resolver:
            foreign=Client();foreign.get('/api/c-demo/context')
            self.assertEqual(self.post({'track_id':self.track['track_id']},foreign).status_code,404)
            self.assertEqual(self.post({'track_id':'not-in-this-playlist'}).status_code,404)
        resolver.assert_not_called()

    def test_unapplied_exclusions_hold_playback_without_mutating_parent(self):
        family=self.playlist.family
        family.excluded=[self.track['track_id']];family.exclusion_revision=1
        family.save(update_fields=['excluded','exclusion_revision'])
        with patch('backend.recommendation.api.resolve_playback_candidates') as resolver:
            response=self.post({'track_id':self.track['track_id']})
        self.assertEqual(response.status_code,409,response.content)
        self.assertEqual(response.json()['code'],'EXCLUSIONS_NOT_APPLIED')
        resolver.assert_not_called()
        self.playlist.refresh_from_db()
        self.assertEqual(self.playlist.snapshot['context']['excluded_track_ids'],[])

    def test_client_cannot_submit_a_url_query_password_or_unbounded_exclusions(self):
        for body in ({'track_id':self.track['track_id'],'url':'https://foreign.example'},
                     {'track_id':self.track['track_id'],'query':'different song'},
                     {'track_id':self.track['track_id'],'password':'offline-fixture-only'},
                     {'track_id':self.track['track_id'],'excluded_video_ids':['invalid']},
                     {'track_id':self.track['track_id'],'excluded_video_ids':['testVID0001']*11}):
            with self.subTest(fields=list(body)), patch('backend.recommendation.api.resolve_playback_candidates') as resolver:
                self.assertEqual(self.post(body).status_code,422)
                resolver.assert_not_called()

    def test_csrf_is_required_before_playback_lookup(self):
        strict=Client(enforce_csrf_checks=True)
        strict.cookies=self.client.cookies
        with patch('backend.recommendation.api.resolve_playback_candidates') as resolver:
            self.assertEqual(self.post({'track_id':self.track['track_id']},strict).status_code,403)
        resolver.assert_not_called()
