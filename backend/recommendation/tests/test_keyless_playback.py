from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from django.conf import settings

from backend.recommendation import youtube_registry as registry
from backend.recommendation.youtube_playback import resolve_playback_candidates


@override_settings(LOCAL_DEMO=True, YOUTUBE_PLAYBACK_MODE='KEYLESS', YOUTUBE_DATA_API_KEY='must-not-use')
class KeylessPlaybackTests(SimpleTestCase):
    def setUp(self):
        temporary_root=Path(settings.BASE_DIR)/'.local-preview-logs'/'keyless-tests'
        temporary_root.mkdir(parents=True,exist_ok=True)
        self.folder=TemporaryDirectory(dir=temporary_root)
        self.addCleanup(self.folder.cleanup)
        self.settings_override=override_settings(YOUTUBE_REGISTRY_PATH=Path(self.folder.name)/'registry.sqlite3')
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.track={'track_id':'local-track','track_name':'Original Song','artists_name':'Original Artist',
                    'duration_ms':240000,'youtube_video_id':'oldVideo001','youtube_match_status':'VERIFIED'}

    def resolve(self, excluded=()):
        with patch('backend.recommendation.youtube_playback._api_json', side_effect=AssertionError('remote search forbidden')), \
                patch('backend.recommendation.youtube_playback._catalog_candidate', side_effect=AssertionError('legacy bypass forbidden')):
            return resolve_playback_candidates(self.track,excluded,owner_id='local-owner')

    def register(self,video_id,revision):
        return registry.register_mappings([{'track_id':self.track['track_id'],'video_url':video_id,'expected_revision':revision}])

    def test_unmapped_and_legacy_pending_never_fall_through_to_remote_or_snapshot(self):
        self.assertEqual(self.resolve()['reason'],'UNMAPPED')
        registry.seed_legacy_mappings([self.track])
        result=self.resolve()
        self.assertEqual(result['status'],'MAPPING_REQUIRED')
        self.assertEqual(result['reason'],'PENDING')
        self.assertEqual(result['candidates'],[])

    def test_reviewed_alternatives_are_reused_and_blocked_video_never_reappears(self):
        self.register('newVideo001',0)
        registry.verify_mapping(self.track,'newVideo001',1,True,True,240)
        self.register('newVideo002',2)
        registry.verify_mapping(self.track,'newVideo002',3,True,True,241)
        result=self.resolve()
        self.assertEqual(result['status'],'READY')
        self.assertEqual({x['video_id'] for x in result['candidates']},{'newVideo001','newVideo002'})
        self.assertTrue(all(x['source']=='MAPPING_REGISTRY' for x in result['candidates']))
        self.assertEqual(len(self.resolve(['newVideo001'])['candidates']),1)
        registry.block_mapping(self.track['track_id'],'newVideo001',4,'Observed embed error 150')
        registry.block_mapping(self.track['track_id'],'newVideo002',5,'Observed embed error 101')
        self.assertEqual(self.resolve()['reason'],'BLOCKED')

    def test_storage_failure_holds_instead_of_silently_skipping_whole_queue(self):
        with patch.object(registry,'track_registry',side_effect=OSError('offline')):
            result=self.resolve()
        self.assertEqual(result['status'],'SEARCH_UNAVAILABLE')
        self.assertEqual(result['reason'],'REGISTRY_UNAVAILABLE')

    @override_settings(LOCAL_DEMO=False)
    def test_production_never_reads_unconfigured_local_registry(self):
        with patch.object(registry,'track_registry',side_effect=AssertionError('local data in production')):
            result=self.resolve()
        self.assertEqual(result['reason'],'REGISTRY_NOT_CONFIGURED')
