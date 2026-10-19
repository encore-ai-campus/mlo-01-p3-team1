"""Collected URLs reach public links/queues without changing review or result data."""
from copy import deepcopy
from unittest.mock import patch

from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext

from backend.recommendation import youtube_registry as registry
from backend.recommendation.models import YoutubeMapping, YoutubeReviewAudit, YoutubeTrackRevision
from backend.recommendation.youtube_queue_api import native_queue


@override_settings(LOCAL_DEMO=False, YOUTUBE_REGISTRY_BACKEND='database')
class CollectedYoutubeLinksTests(TestCase):
    def setUp(self):
        self.tracks = [{'track_id': f'track-{i}', 'track_name': f'Song {i}'} for i in range(4)]
        for i in range(3):
            registry.register_mappings([{'track_id': self.tracks[i]['track_id'], 'video_url': f'testVID000{i}', 'expected_revision': 0, 'note': 'private operator note'}])

    def test_candidates_in_queue_and_links_without_promoting_reviews_or_changing_tracks(self):
        before = deepcopy(self.tracks)
        audits = list(YoutubeReviewAudit.objects.values())
        rows = list(YoutubeMapping.objects.values())
        revisions = list(YoutubeTrackRevision.objects.values())
        result = native_queue('owned', self.tracks)
        self.assertEqual(result['ready_count'], 3)
        self.assertEqual(result['unreviewed_count'], 3)
        self.assertEqual(result['url'], 'https://www.youtube.com/watch_videos?video_ids=testVID0000,testVID0001,testVID0002')
        self.assertEqual(result['missing'][0]['reason'], 'MAPPING_REQUIRED')
        self.assertEqual([item['track_id'] for item in result['track_links']], [item['track_id'] for item in self.tracks])
        self.assertEqual(result['track_links'][0]['candidates'], [{'video_id': 'testVID0000', 'native_verified': False}])
        self.assertEqual(result['track_links'][3], {'track_id': 'track-3', 'revision': 0, 'candidates': []})
        self.assertNotIn('private operator', str(result))
        self.assertNotIn('note', str(result))
        self.assertEqual(self.tracks, before)
        self.assertEqual(list(YoutubeMapping.objects.values()), rows)
        self.assertEqual(list(YoutubeReviewAudit.objects.values()), audits)
        self.assertEqual(list(YoutubeTrackRevision.objects.values()), revisions)

    def test_native_approval_preferred_but_iframe_block_and_native_block_stay_independent(self):
        registry.register_mappings([{'track_id': 'track-0', 'video_url': 'approved001', 'expected_revision': 1}])
        track = {**self.tracks[0], 'duration_ms': 240000}
        registry.verify_native_mapping(track, 'approved001', 2, True, True, 240)
        registry.block_mapping('track-0', 'approved001', 3, 'iframe restriction')
        registry.block_native_mapping('track-1', 'testVID0001', 1, 'wrong version')
        registry.block_mapping('track-2', 'testVID0002', 1, 'rejected candidate')
        result = native_queue('owned', self.tracks)
        self.assertEqual(result['ready_count'], 1)
        self.assertEqual(result['unreviewed_count'], 0)
        self.assertEqual(result['tracks'][0]['video_id'], 'approved001')
        self.assertEqual(len(result['track_links'][0]['candidates']), 2)
        self.assertEqual(result['track_links'][1]['candidates'], [])
        self.assertEqual(result['track_links'][2]['candidates'], [])

    def test_duplicate_approved_video_falls_back_to_another_collected_candidate(self):
        registry.register_mappings([{'track_id': 'track-1', 'video_url': 'testVID0000', 'expected_revision': 1}])
        YoutubeMapping.objects.filter(track_id='track-1', video_id='testVID0000').update(native_verified=True)
        result = native_queue('owned', self.tracks)
        self.assertEqual([item['video_id'] for item in result['tracks']], ['testVID0000', 'testVID0001', 'testVID0002'])
        self.assertEqual(result['ready_count'], 3)

    def test_batch_read_limits_queries_to_requested_tracks_and_handles_unknown_and_duplicate_ids(self):
        with CaptureQueriesContext(connection) as queries:
            result = registry.track_registries(['track-1', 'track-1', 'unknown'])
        selects = [query for query in queries if query['sql'].lstrip().upper().startswith('SELECT')]
        self.assertEqual(len(selects), 2)
        self.assertEqual(list(result), ['track-1', 'unknown'])
        self.assertEqual(result['track-1']['revision'], 1)
        self.assertEqual(result['unknown']['mappings'], [])
        with patch.object(registry, '_connection') as opened:
            self.assertEqual(registry.track_registries([]), {})
        opened.assert_not_called()

    def test_more_than_sqlite_parameter_limit_uses_bounded_batches(self):
        with CaptureQueriesContext(connection) as queries:
            result = registry.track_registries([f'track-{i}' for i in range(1201)])
        selects = [query for query in queries if query['sql'].lstrip().upper().startswith('SELECT')]
        self.assertEqual(len(selects), 6)
        self.assertEqual(len(result), 1201)
        self.assertEqual(result['track-0']['mappings'][0]['video_id'], 'testVID0000')
