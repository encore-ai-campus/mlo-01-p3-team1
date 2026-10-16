import csv
import hashlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, Client, override_settings

from backend.recommendation.models import Catalog, Playlist
from backend.recommendation.occasion import load_occasion_decisions
from backend.recommendation.worker import run_one
from pipeline.music.normalize import RAW_FIELDS


@override_settings(LOCAL_DEMO=True, SEARCH_SECONDS=10, GEMINI_ENABLED=False)
class OccasionPreviewTests(TestCase):
    def setUp(self):
        temp_root = Path(__file__).resolve().parent / '.test-tmp'
        temp_root.mkdir(exist_ok=True)
        self.temp = TemporaryDirectory(prefix='music-occasion-test-', dir=temp_root)
        self.root = Path(self.temp.name)
        self.root.resolve().relative_to(temp_root.resolve())
        self.addCleanup(self.temp.cleanup)
        self.source = self.root / 'source.csv'
        fields = sorted(RAW_FIELDS)
        with self.source.open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fields)
            writer.writeheader()
            for index in range(5):
                row = dict.fromkeys(fields, '0')
                row.update(track_id=f'track-{index}', track_name=f'General song {index}', artists='Fixture Artist',
                           album_name='Fixture album', duration_ms='3600000', explicit='False', energy='.6',
                           mode='1', acousticness='.5', valence='.7', tempo='90', time_signature='4',
                           instrumentalness='.9', track_genre='jazz')
                writer.writerow(row)
        self.source_sha = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.decisions = self.root / 'occasion_decisions.csv'
        with self.decisions.open('w', encoding='utf-8-sig', newline='') as stream:
            fields = ['track_id', 'occasion_status', 'decision_source', 'occasion_policy_version', 'occasion_decision_version']
            writer = csv.DictWriter(stream, fields)
            writer.writeheader()
            for index, status in enumerate(['GENERAL']*3 + ['SEASONAL_EVENT', 'REVIEW_REQUIRED']):
                writer.writerow(dict(zip(fields, [f'track-{index}', status, 'RULE_SCREEN', 'fixture-occasion-v1', f'decision-{index}'])))
        self.write_manifest()

    def write_manifest(self, source_sha=None):
        (self.root/'manifest.json').write_text(json.dumps({
            'schema_version': 'GENERAL_CANDIDATES_MANIFEST_V1', 'source_dataset_sha256': source_sha or self.source_sha,
            'occasion_policy_version': 'fixture-occasion-v1',
            'artifacts': {'occasion_decisions.csv': hashlib.sha256(self.decisions.read_bytes()).hexdigest()}}), encoding='utf-8')

    def seed(self, **extra):
        output = io.StringIO()
        call_command('seed_csv_preview', str(self.source), expected_sha256=self.source_sha,
                     general_dir=str(self.root), stdout=output, **extra)
        return json.loads(output.getvalue())

    def test_main_csv_preview_and_existing_playlist_api_are_general_only(self):
        result = self.seed()
        catalog = Catalog.objects.get(pk=result['version'])
        self.assertEqual(len(catalog.tracks), 3)
        self.assertEqual(result['not_general_skipped'], 2)
        self.assertTrue(catalog.is_test)
        self.assertTrue(catalog.source_ref.startswith('local-preview:'))
        self.assertTrue(all(row['occasion_status']=='GENERAL' for row in catalog.tracks))
        self.assertTrue(all(row['play_url']==f'https://open.spotify.com/track/{row["track_id"]}' for row in catalog.tracks))
        client = Client()
        client.get('/api/c-demo/context')
        response = client.post('/api/recommendation-jobs', {'region_id':'demo-region'},
                               content_type='application/json', HTTP_IDEMPOTENCY_KEY='general-preview')
        self.assertEqual(response.status_code, 202, response.content)
        self.assertTrue(run_one())
        playlist = Playlist.objects.get(job_id=response.json()['job_id'])
        response = client.get(f'/api/playlists/{playlist.pk}')
        self.assertEqual(response.status_code, 200)
        value = response.json()
        self.assertTrue(value['preview_only'])
        self.assertTrue(value['is_test'])
        self.assertFalse(value['validation_passed'])
        self.assertEqual(value['total_ms'], 10800000)
        self.assertTrue(all(row['occasion_status']=='GENERAL' for row in value['items']))
        self.assertTrue(all(row['occasion_decisions_sha256']==result['occasion_decisions_sha256'] for row in value['items']))

    def test_changed_source_or_artifact_fails_before_catalog_write(self):
        self.write_manifest('0'*64)
        with self.assertRaises(CommandError): self.seed()
        self.assertEqual(Catalog.objects.count(), 0)
        self.write_manifest()
        self.decisions.write_text(self.decisions.read_text(encoding='utf-8-sig')+'\n', encoding='utf-8-sig')
        with self.assertRaises(ValueError): load_occasion_decisions(self.root, self.source_sha)
        self.assertEqual(Catalog.objects.count(), 0)

    def test_same_snapshot_is_idempotent_and_old_catalog_is_preserved(self):
        Catalog.objects.create(version='old-unfiltered', tracks=[], sha256='old', source_ref='local-preview:old',
                               source_sha256=self.source_sha, is_test=True, ready=True)
        first, second = self.seed(), self.seed()
        self.assertEqual(first['version'], second['version'])
        self.assertEqual(Catalog.objects.count(), 2)
        self.assertEqual(Catalog.objects.get(pk='old-unfiltered').sha256, 'old')

    def test_missing_decision_never_falls_back_to_unscreened_source(self):
        self.decisions.write_text(self.decisions.read_text(encoding='utf-8-sig').replace('track-0,', 'unknown-track,'), encoding='utf-8-sig')
        self.write_manifest()
        with self.assertRaises(CommandError): self.seed()
        self.assertEqual(Catalog.objects.count(), 0)

    def mapping_file(self, **changes):
        mapping = {'track_id':'track-0','source_track_name':'General song 0','source_artists':'Fixture Artist',
                   'source_album_name':'Fixture album','source_duration_ms':3600000,'youtube_video_id':'abcdefghijk',
                   'match_status':'VERIFIED','youtube_title':'Fixture video','youtube_channel':'Fixture channel',
                   'platform_duration_seconds':3600,'verification_note':'Synthetic offline test only',
                   'verified_by':'fixture-reviewer','checked_at':'2026-10-16T00:00:00Z',**changes}
        path = self.root/'youtube-mappings.json'
        path.write_text(json.dumps({'schema_version':'YOUTUBE_MAPPING_V1','mappings':[mapping]}), encoding='utf-8')
        return path

    def test_verified_mapping_is_snapshotted_without_changing_spotify_url(self):
        path = self.mapping_file()
        result = self.seed(youtube_mappings=str(path))
        catalog = Catalog.objects.get(pk=result['version'])
        row = next(row for row in catalog.tracks if row['track_id']=='track-0')
        self.assertEqual(row['youtube_video_id'], 'abcdefghijk')
        self.assertEqual(row['youtube_match_status'], 'VERIFIED')
        self.assertEqual(row['play_url'], 'https://open.spotify.com/track/track-0')
        path.write_text('{}', encoding='utf-8')
        self.assertEqual(Catalog.objects.get(pk=result['version']).tracks[0]['youtube_mapping_snapshot']['verification_note'],
                         'Synthetic offline test only')

    def test_blocked_embed_is_preserved_and_never_promoted(self):
        path = self.mapping_file(match_status='BLOCKED_EMBED')
        before = path.read_bytes()
        result = self.seed(youtube_mappings=str(path))
        self.assertEqual(result['verified_youtube_mapping_count'], 0)
        self.assertTrue(all('youtube_video_id' not in row for row in Catalog.objects.get(pk=result['version']).tracks))
        self.assertEqual(path.read_bytes(), before)

    def test_stale_original_or_missing_evidence_mapping_rejects_before_write(self):
        for changes in ({'source_album_name':'Different album'}, {'source_duration_ms':1},
                        {'youtube_video_id':'invalid'}, {'verification_note':''}, {'checked_at':'2026-10-16T00:00:00'}):
            with self.subTest(changes=changes):
                path = self.mapping_file(**changes)
                with self.assertRaises(CommandError): self.seed(youtube_mappings=str(path))
                self.assertEqual(Catalog.objects.count(), 0)

    def selection_inputs(self, **selection_changes):
        path = self.mapping_file()
        template = json.loads(path.read_text(encoding='utf-8'))['mappings'][0]
        records = [{**template, 'track_id':f'track-{index}', 'source_track_name':f'General song {index}',
                    'youtube_video_id':f'abcdefghij{index}'} for index in range(3)]
        path.write_text(json.dumps({'schema_version':'YOUTUBE_MAPPING_V1','mappings':records}), encoding='utf-8')
        selection = self.root/'selection.json'
        value = {'schema_version':'YOUTUBE_PLAYBACK_SELECTION_V1','source_dataset_sha256':self.source_sha,
                 'track_ids':['track-2','track-0','track-1'],'selection_version':'fixture-selection-v1',
                 **selection_changes}
        selection.write_text(json.dumps(value), encoding='utf-8')
        return path, selection

    def test_explicit_playback_selection_preserves_order_and_existing_catalog(self):
        base = self.seed()
        path, selection = self.selection_inputs()
        result = self.seed(youtube_mappings=str(path), playback_selection=str(selection))
        catalog = Catalog.objects.get(pk=result['version'])
        self.assertEqual([row['track_id'] for row in catalog.tracks], ['track-2','track-0','track-1'])
        self.assertEqual([row['playback_selection_position'] for row in catalog.tracks], [1,2,3])
        self.assertTrue(all(row['youtube_match_status']=='VERIFIED' for row in catalog.tracks))
        self.assertTrue(all(row['playback_selection_version']=='fixture-selection-v1' for row in catalog.tracks))
        self.assertEqual(catalog.source_ref, 'local-preview:youtube-playback-selection:source.csv')
        self.assertTrue(catalog.is_test)
        self.assertIn('-selection-'+hashlib.sha256(selection.read_bytes()).hexdigest()[:12], catalog.version)
        self.assertEqual(Catalog.objects.count(), 2)
        self.assertEqual(len(Catalog.objects.get(pk=base['version']).tracks), 3)
        self.assertNotIn('playback_selection_position', Catalog.objects.get(pk=base['version']).tracks[0])

    def test_invalid_or_non_general_selection_never_writes_catalog(self):
        for changes in ({'source_dataset_sha256':'0'*64}, {'schema_version':'other'}, {'selection_version':''},
                        {'track_ids':[]}, {'track_ids':['track-0','track-0']},
                        {'track_ids':['missing-track']}, {'track_ids':['track-3']}, {'track_ids':[True]}):
            with self.subTest(changes=changes):
                path, selection = self.selection_inputs(**changes)
                with self.assertRaises(CommandError):
                    self.seed(youtube_mappings=str(path), playback_selection=str(selection))
                self.assertEqual(Catalog.objects.count(), 0)

    def test_selection_requires_every_selected_mapping_verified(self):
        for status in ('CANDIDATE', 'BLOCKED_EMBED', 'MISSING'):
            with self.subTest(status=status):
                path, selection = self.selection_inputs()
                payload = json.loads(path.read_text(encoding='utf-8'))
                if status == 'MISSING': payload['mappings'].pop()
                else: payload['mappings'][-1]['match_status'] = status
                path.write_text(json.dumps(payload), encoding='utf-8')
                before = path.read_bytes()
                with self.assertRaises(CommandError):
                    self.seed(youtube_mappings=str(path), playback_selection=str(selection))
                self.assertEqual(Catalog.objects.count(), 0)
                self.assertEqual(path.read_bytes(), before)

    def test_playback_selection_is_local_only_and_requires_mapping_file(self):
        path, selection = self.selection_inputs()
        with self.assertRaises(CommandError): self.seed(playback_selection=str(selection))
        with override_settings(LOCAL_DEMO=False):
            with self.assertRaises(CommandError):
                self.seed(youtube_mappings=str(path), playback_selection=str(selection))
        self.assertEqual(Catalog.objects.count(), 0)
