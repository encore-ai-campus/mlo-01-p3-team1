import io
import json
import sqlite3
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import SimpleTestCase, override_settings

from backend.recommendation.errors import DomainError
from backend.recommendation import youtube_registry as registry


class YoutubeRegistryTests(SimpleTestCase):
    def setUp(self):
        temporary_root = settings.BASE_DIR / '.local-preview-logs'
        temporary_root.mkdir(parents=True, exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=temporary_root)
        self.addCleanup(self.directory.cleanup)
        self.settings = override_settings(LOCAL_DEMO=True,
            YOUTUBE_REGISTRY_PATH=Path(self.directory.name) / 'registry.sqlite3',
            YOUTUBE_REVIEW_ACCESS_FILE=Path(self.directory.name) / 'access.json')
        self.settings.enable()
        self.addCleanup(self.settings.disable)
        self.track = {'track_id': 'track-one', 'track_name': 'Test title', 'artists_name': 'Test artist', 'duration_ms': 240000}

    def register(self, video='testVideo01', revision=0, track_id='track-one', **extra):
        return registry.register_mappings([{'track_id': track_id, 'video_url': video, 'expected_revision': revision, **extra}])

    def test_url_allowlist_never_fetches_and_rejects_confusable_or_credential_urls(self):
        for value in ('testVideo01', 'https://www.youtube.com/watch?v=testVideo01',
                      'https://youtu.be/testVideo01?si=abc', 'https://m.youtube.com/shorts/testVideo01',
                      'https://youtube.com/embed/testVideo01'):
            self.assertEqual(registry.normalize_video_url(value), 'testVideo01')
        for value in ('http://youtube.com/watch?v=testVideo01', 'https://youtube.com.evil.example/watch?v=testVideo01',
                      'https://user:pass@youtube.com/watch?v=testVideo01', 'https://youtube.com:444/watch?v=testVideo01',
                      'https://youtube.com/redirect?q=testVideo01', 'https://youtube.com/watch?v=testVideo01&v=nextVideo02',
                      'https://youtu.be/testVideo01/more', 'https://www.you\ttube.com/watch?v=testVideo01',
                      'https://youtube.com/watch?v=testVideo01#fragment', 'not-video'):
            with self.subTest(value=value), self.assertRaises(DomainError):
                registry.normalize_video_url(value)

    def test_registration_pending_then_operator_playing_and_identity_required(self):
        self.register()
        pending = registry.track_registry('track-one')
        self.assertEqual(pending['revision'], 1)
        self.assertEqual(pending['mappings'][0]['status'], 'CANDIDATE')
        self.assertEqual(registry.verified_candidates('track-one'), [])
        for identity, playing in ((False, True), (True, False), (1, True)):
            with self.assertRaises(DomainError):
                registry.verify_mapping(self.track, 'testVideo01', 1, identity, playing, 240)
        verified = registry.verify_mapping(self.track, 'testVideo01', 1, True, True, 241, 'Original recording checked')
        self.assertEqual(verified['revision'], 2)
        self.assertEqual(verified['mappings'][0]['status'], 'VERIFIED')
        self.assertTrue(verified['mappings'][0]['playback_observed'])
        self.assertTrue(verified['mappings'][0]['observed_at'])
        self.assertEqual(registry.verified_candidates('track-one')[0]['video_id'], 'testVideo01')

    def test_large_duration_mismatch_nan_and_bool_never_verify(self):
        self.register()
        for duration in (480, float('nan'), True, 0, -1):
            with self.subTest(duration=duration), self.assertRaises(DomainError):
                registry.verify_mapping(self.track, 'testVideo01', 1, True, True, duration)
        self.assertEqual(registry.track_registry('track-one')['revision'], 1)

    def test_revisions_prevent_overwriting_another_operator(self):
        self.register()
        with self.assertRaises(DomainError) as error:
            self.register(video='nextVideo02', revision=0)
        self.assertEqual(error.exception.code, 'MAPPING_REVISION_CONFLICT')
        self.assertEqual(len(registry.track_registry('track-one')['mappings']), 1)
        self.register(video='nextVideo02', revision=1)
        self.assertEqual(len(registry.track_registry('track-one')['mappings']), 2)

    def test_blocked_mapping_is_not_revived_by_same_url_or_legacy_seed(self):
        self.register()
        registry.block_mapping('track-one', 'testVideo01', 1, 'Embedding not permitted')
        registry.seed_legacy_mappings([{**self.track, 'youtube_video_id': 'testVideo01'}])
        self.register(revision=2)
        self.assertEqual(registry.track_registry('track-one')['mappings'][0]['status'], 'BLOCKED')
        self.assertEqual(registry.verified_candidates('track-one'), [])

    def test_legacy_verified_metadata_only_seeds_pending(self):
        source = [{**self.track, 'youtube_video_id': 'testVideo01', 'youtube_match_status': 'VERIFIED'}]
        self.assertEqual(registry.seed_legacy_mappings(source)['inserted_count'], 1)
        self.assertEqual(registry.seed_legacy_mappings(source)['inserted_count'], 0)
        mapping = registry.track_registry('track-one')['mappings'][0]
        self.assertEqual(mapping['source'], 'LEGACY_REVIEW_PENDING')
        self.assertEqual(mapping['status'], 'CANDIDATE')
        self.assertFalse(mapping['identity_confirmed'])

    def test_csv_bom_formula_note_and_same_track_alternatives_preserved(self):
        text = '\ufefftrack_id,video_url,expected_revision,note\ntrack-one,testVideo01,0,=SUM(1+1)\ntrack-one,nextVideo02,0,Second recording\n'
        result = registry.register_mappings(registry.parse_mapping_csv(text), source='OPERATOR_CSV')
        self.assertEqual(result['changed_track_count'], 1)
        self.assertEqual(result['items'][0]['revision'], 1)
        self.assertEqual({row['note'] for row in result['items'][0]['mappings']}, {'=SUM(1+1)', 'Second recording'})

    def test_invalid_csv_or_stale_later_row_rolls_back_all_rows(self):
        self.register()
        rows = [{'track_id': 'new-track', 'video_url': 'nextVideo02', 'expected_revision': 0},
                {'track_id': 'track-one', 'video_url': 'lastVideo03', 'expected_revision': 0}]
        with self.assertRaises(DomainError):
            registry.register_mappings(rows)
        self.assertEqual(registry.track_registry('new-track')['mappings'], [])
        duplicate = 'track_id,video_url,expected_revision\ntrack-one,testVideo01,1\ntrack-one,testVideo01,1\n'
        with self.assertRaises(DomainError) as error:
            registry.register_mappings(registry.parse_mapping_csv(duplicate))
        self.assertEqual(error.exception.code, 'CSV_DUPLICATE_MAPPING')
        self.assertEqual(registry.track_registry('track-one')['revision'], 1)

    def test_csv_headers_row_limit_and_bad_revision_rejected(self):
        values = ['track_id,video_url\nx,testVideo01\n',
                  'track_id,video_url,expected_revision\nx,testVideo01,-1\n',
                  'track_id,video_url,expected_revision,status\nx,testVideo01,0,VERIFIED\n',
                  'track_id,video_url,expected_revision\n' + 'x,testVideo01,0\n' * 501]
        for text in values:
            with self.subTest(size=len(text)), self.assertRaises(DomainError):
                registry.parse_mapping_csv(text)

    def test_code_is_persistent_rotatable_and_never_printed(self):
        output = io.StringIO()
        call_command('init_youtube_review', stdout=output)
        first = json.loads(registry.access_code_path().read_text())['access_code']
        self.assertNotIn(first, output.getvalue())
        registry.validate_access_code(first)
        for value in ('wrong-code', '잘못된 코드', None):
            with self.assertRaises(DomainError):
                registry.validate_access_code(value)
        registry.initialize_access_code()
        self.assertEqual(json.loads(registry.access_code_path().read_text())['access_code'], first)
        registry.initialize_access_code(rotate=True)
        with self.assertRaises(DomainError):
            registry.validate_access_code(first)

    @override_settings(LOCAL_DEMO=False)
    def test_production_never_accepts_local_secret(self):
        with self.assertRaises(DomainError) as error:
            registry.validate_access_code('any')
        self.assertEqual(error.exception.status, 503)

    def test_native_operator_review_is_independent_of_blocked_iframe(self):
        self.register()
        registry.block_mapping('track-one', 'testVideo01', 1, 'Iframe embed error 150')
        for identity, playing, duration in ((False, True, 240), (True, False, 240), (True, True, 480)):
            with self.assertRaises(DomainError):
                registry.verify_native_mapping(self.track, 'testVideo01', 2, identity, playing, duration)
        result = registry.verify_native_mapping(self.track, 'testVideo01', 2, True, True, 241)
        mapping = result['mappings'][0]
        self.assertEqual(result['revision'], 3)
        self.assertTrue(mapping['native_verified'])
        self.assertEqual(mapping['native_source'], 'OPERATOR_NATIVE_REPORTED_PLAYING')
        self.assertEqual(mapping['status'], 'BLOCKED')
        self.assertFalse(mapping['playback_observed'])
        self.assertEqual(registry.verified_candidates('track-one'), [])

    def test_native_legacy_seed_requires_exact_reviewed_identity_and_preserves_iframe(self):
        track = {**self.track, 'album_name': 'Original album', 'youtube_video_id': 'testVideo01', 'youtube_match_status': 'VERIFIED'}
        track['youtube_mapping_snapshot'] = {'track_id': track['track_id'], 'source_track_name': track['track_name'],
            'source_artists': track['artists_name'], 'source_album_name': track['album_name'], 'source_duration_ms': 240000,
            'youtube_video_id': 'testVideo01', 'youtube_title': 'Test title', 'youtube_channel': 'First artist - Topic',
            'platform_duration_seconds': 241, 'match_status': 'VERIFIED',
            'match_method': 'PRIMARY_METADATA_AND_NATIVE_QUEUE_INCLUSION', 'mapping_version': 'original-mapping',
            'verification_note': 'Metadata and native queue only, not full listening', 'verified_by': 'Original review',
            'checked_at': '2026-10-16T06:10:33+00:00'}
        for change in ({'source_track_name': 'Different recording'}, {'match_method': 'AUTOMATIC_SEARCH'},
                       {'checked_at': '2026-10-16'}, {'source_duration_ms': 241000}):
            invalid = {**track, 'youtube_mapping_snapshot': {**track['youtube_mapping_snapshot'], **change}}
            self.assertEqual(registry.seed_native_reviewed_mappings([invalid])['native_verified_count'], 0)
        result = registry.seed_native_reviewed_mappings([track])
        self.assertEqual(result['native_verified_count'], 1)
        self.assertEqual(registry.seed_native_reviewed_mappings([track])['native_verified_count'], 0)
        mapping = registry.track_registry('track-one')['mappings'][0]
        self.assertTrue(mapping['native_verified'])
        self.assertEqual(mapping['native_source'], 'LEGACY_NATIVE_METADATA_REVIEW')
        self.assertEqual(mapping['status'], 'CANDIDATE')
        self.assertFalse(mapping['playback_observed'])
        revision = registry.track_registry('track-one')['revision']
        registry.block_native_mapping('track-one', 'testVideo01', revision, 'Native video unavailable')
        self.assertEqual(registry.seed_native_reviewed_mappings([track])['native_verified_count'], 0)
        mapping = registry.track_registry('track-one')['mappings'][0]
        self.assertFalse(mapping['native_verified'])
        self.assertEqual(mapping['native_source'], 'OPERATOR_NATIVE_BLOCK')
        self.assertEqual(mapping['native_reason'], 'Native video unavailable')
        registry.verify_native_mapping(track, 'testVideo01', revision + 1, True, True, 241)
        self.assertEqual(registry.track_registry('track-one')['mappings'][0]['native_reason'], '')

    def test_existing_registry_additive_native_schema_upgrade_is_idempotent(self):
        connection = sqlite3.connect(registry.registry_path())
        connection.execute("CREATE TABLE mapping(track_id TEXT NOT NULL,video_id TEXT NOT NULL,status TEXT NOT NULL,source TEXT NOT NULL,note TEXT NOT NULL DEFAULT '',reason TEXT NOT NULL DEFAULT '',identity_confirmed INTEGER NOT NULL DEFAULT 0,playback_observed INTEGER NOT NULL DEFAULT 0,duration_seconds REAL,observed_at TEXT,updated_at TEXT NOT NULL,PRIMARY KEY(track_id,video_id))")
        connection.commit()
        connection.close()
        self.register()
        self.assertFalse(registry.track_registry('track-one')['mappings'][0]['native_verified'])
        self.assertFalse(registry.track_registry('track-one')['mappings'][0]['native_verified'])

    def test_native_duration_difference_requires_explicit_noted_acknowledgment(self):
        self.register()
        for flag, note in ((False, 'Official music video intro'), (True, ''), (True, '   ')):
            with self.assertRaises(DomainError):
                registry.verify_native_mapping(self.track, 'testVideo01', 1, True, True, 275, note, flag)
        result = registry.verify_native_mapping(self.track, 'testVideo01', 1, True, True, 275,
                                               'Official music video adds a checked 35-second intro', True)
        self.assertTrue(result['mappings'][0]['native_verified'])
        self.assertEqual(result['mappings'][0]['native_duration_seconds'], 275)
        with sqlite3.connect(registry.registry_path()) as connection:
            action = connection.execute('SELECT action FROM review_audit ORDER BY id DESC LIMIT 1').fetchone()[0]
        connection.close()
        self.assertEqual(action, 'VERIFY_NATIVE_DURATION_DIFFERENCE_ACK')
        self.assertEqual(self.track['duration_ms'], 240000)

    def test_native_duration_acknowledgment_is_bounded_and_does_not_change_iframe_rules(self):
        self.register()
        for duration, flag in ((301, True), (275, 1)):
            with self.assertRaises(DomainError):
                registry.verify_native_mapping(self.track, 'testVideo01', 1, True, True, duration,
                                               'Explicit checked video intro', flag)
        with self.assertRaises(DomainError):
            registry.verify_mapping(self.track, 'testVideo01', 1, True, True, 275, 'Video intro')
        self.assertEqual(registry.track_registry('track-one')['revision'], 1)
