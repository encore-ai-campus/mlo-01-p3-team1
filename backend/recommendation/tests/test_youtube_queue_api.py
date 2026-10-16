from copy import deepcopy
from unittest.mock import patch

from django.core.management import call_command
from django.test import Client, TransactionTestCase, override_settings

from backend.recommendation.models import Playlist, PendingEvent
from backend.recommendation.worker import run_one
from backend.recommendation.youtube_queue_api import native_queue


@override_settings(LOCAL_DEMO=True, SEARCH_SECONDS=20, SEARCH_MAX_CANDIDATES=96, YOUTUBE_PLAYBACK_MODE='KEYLESS')
class YoutubeQueueApiTests(TransactionTestCase):
    def setUp(self):
        call_command('seed_c_demo',verbosity=0)
        self.client=Client()
        self.client.get('/api/c-demo/context')
        job=self.client.post('/api/recommendation-jobs',{'region_id':'demo-region'},content_type='application/json',HTTP_IDEMPOTENCY_KEY='native-queue-test').json()
        self.assertTrue(run_one())
        self.playlist=Playlist.objects.get(job_id=job['job_id'])
        self.path=f'/api/playlists/{self.playlist.pk}/youtube-queue'

    def test_owned_native_queue_preserves_order_and_result_without_search_or_account_write(self):
        before=deepcopy(self.playlist.snapshot)
        ids=[item['track_id'] for item in before['items']]
        def lookup(track_id):
            index=ids.index(track_id)
            return {'mappings':[{'video_id':f'video{index:06}','status':'BLOCKED','native_verified':True,'native_source':'LEGACY_NATIVE_METADATA_REVIEW'}]}
        with patch('backend.recommendation.youtube_registry.track_registry',side_effect=lookup), \
                patch('backend.recommendation.youtube_playback._api_json',side_effect=AssertionError('API forbidden')):
            response=self.client.get(self.path)
        self.assertEqual(response.status_code,200,response.content)
        result=response.json()
        self.assertTrue(result['is_complete'])
        self.assertFalse(result['account_saved'])
        self.assertEqual([item['track_id'] for item in result['tracks']],ids)
        self.assertIn('watch_videos?video_ids=video000000,video000001',result['url'])
        self.playlist.refresh_from_db()
        self.assertEqual(self.playlist.snapshot,before)
        self.assertFalse(PendingEvent.objects.exists())

    def test_partial_queue_does_not_silently_deduplicate_or_claim_complete(self):
        tracks=self.playlist.snapshot['items'][:3]
        def lookup(track_id):
            return {'mappings':[] if track_id==tracks[2]['track_id'] else [{'video_id':'sameVideo01','native_verified':True}]}
        with patch('backend.recommendation.youtube_registry.track_registry',side_effect=lookup):
            result=native_queue('owned',tracks)
        self.assertFalse(result['is_complete'])
        self.assertEqual(result['ready_count'],1)
        self.assertEqual(result['total_count'],3)
        self.assertEqual([item['reason'] for item in result['missing']],['DUPLICATE_VIDEO','NATIVE_REVIEW_REQUIRED'])

    def test_pending_native_review_does_not_use_iframe_verification_as_substitute(self):
        with patch('backend.recommendation.youtube_registry.track_registry',return_value={'mappings':[{'video_id':'testVideo01','status':'VERIFIED','native_verified':False}]}):
            result=native_queue('owned',self.playlist.snapshot['items'])
        self.assertIsNone(result['url'])
        self.assertEqual(result['ready_count'],0)

    def test_foreign_owner_and_unapplied_exclusions_never_read_mapping_registry(self):
        other=Client();other.get('/api/c-demo/context')
        with patch('backend.recommendation.youtube_registry.track_registry') as lookup:
            self.assertEqual(other.get(self.path).status_code,404)
            family=self.playlist.family
            family.excluded=[self.playlist.snapshot['items'][0]['track_id']]
            family.save(update_fields=['excluded'])
            self.assertEqual(self.client.get(self.path).status_code,409)
        lookup.assert_not_called()

    @override_settings(LOCAL_DEMO=False, OWNER_RESOLVER='')
    def test_unconfigured_production_has_no_local_registry_fallback(self):
        with patch('backend.recommendation.youtube_registry.track_registry') as lookup:
            self.assertEqual(self.client.get(self.path).status_code,503)
        lookup.assert_not_called()
