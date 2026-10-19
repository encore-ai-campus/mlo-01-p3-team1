"""Regression for the already-deployed shared YouTube PostgreSQL contract."""
from django.test import TestCase, override_settings
from backend.recommendation import youtube_registry
from backend.recommendation.models import YoutubeMapping, YoutubeReviewAudit, YoutubeTrackRevision, DispatchControl


class SharedYoutubeDatabaseTests(TestCase):
    def test_registry_backend_setting_is_available(self):
        from django.conf import settings
        self.assertIn(settings.YOUTUBE_REGISTRY_BACKEND, {'local', 'database', 'disabled'})

    @override_settings(LOCAL_DEMO=False, YOUTUBE_REGISTRY_BACKEND='database')
    def test_production_registry_uses_django_db_and_preserves_actor(self):
        from backend.recommendation.youtube_database import review_actor
        token = review_actor.set('test-admin')
        try:
            inserted = youtube_registry.register_mappings([
                {'track_id': 'regression-track', 'video_url': 'abCde_12345',
                 'expected_revision': 0, 'note': 'verified entry'}
            ])
        finally:
            review_actor.reset(token)
        self.assertEqual(inserted['changed_track_count'], 1)
        self.assertTrue(YoutubeTrackRevision.objects.filter(pk='regression-track').exists())
        self.assertEqual(YoutubeMapping.objects.filter(track_id='regression-track').count(), 1)
        audit = YoutubeReviewAudit.objects.get(track_id='regression-track')
        self.assertEqual(audit.actor, 'test-admin')
        record = youtube_registry.track_registry('regression-track')
        self.assertEqual(record['revision'], 1)
        self.assertEqual(record['mappings'][0]['video_id'], 'abCde_12345')

    @override_settings(LOCAL_DEMO=False, YOUTUBE_REGISTRY_BACKEND='database', YOUTUBE_PLAYBACK_MODE='KEYLESS')
    def test_production_keyless_uses_shared_approved_mappings(self):
        from backend.recommendation.youtube_playback import resolve_playback_candidates
        track = {'track_id': 'verified-regression', 'track_name': 'Test Track',
                 'artists_name': 'Test Artist', 'duration_ms': 240000}
        self.assertEqual(resolve_playback_candidates(track)['status'], 'MAPPING_REQUIRED')
        youtube_registry.register_mappings([{'track_id': track['track_id'],
            'video_url': 'abCde_12345', 'expected_revision': 0, 'note': ''}])
        youtube_registry.verify_native_mapping(track,'abCde_12345',1,True,True,240)
        self.assertEqual(resolve_playback_candidates(track)['status'], 'MAPPING_REQUIRED')
        youtube_registry.verify_mapping(track,'abCde_12345',2,True,True,240)
        result = resolve_playback_candidates(track)
        self.assertEqual(result['status'], 'READY')
        self.assertEqual(result['candidates'][0]['video_id'], 'abCde_12345')

    def test_dispatch_control_is_distinct_from_youtube_registry_tables(self):
        self.assertEqual(DispatchControl._meta.db_table, 'recommendation_dispatchcontrol')
        self.assertEqual(YoutubeMapping._meta.db_table, 'youtube_mapping')
        self.assertEqual(YoutubeReviewAudit._meta.db_table, 'youtube_review_audit')
