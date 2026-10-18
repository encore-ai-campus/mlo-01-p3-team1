import json
import tempfile
from pathlib import Path

from django.conf import settings
from django.test import Client, TransactionTestCase, override_settings
from django.urls import path

from backend.recommendation import api, youtube_registry as registry, youtube_review_api as review
from backend.recommendation.models import Catalog, Family, Job, Playlist


urlpatterns = [
    path('api/c-demo/context', api.DemoContext.as_view()),
    path('api/youtube-review/status', review.ReviewStatus.as_view()),
    path('api/youtube-review/tracks', review.ReviewTracks.as_view()),
    path('api/youtube-review/mappings', review.ReviewMappings.as_view()),
    path('api/youtube-review/import', review.ReviewImport.as_view()),
    path('api/youtube-review/verify', review.ReviewVerify.as_view()),
    path('api/youtube-review/block', review.ReviewBlock.as_view()),
    path('api/youtube-review/native-verify', review.ReviewNativeVerify.as_view()),
    path('api/youtube-review/native-block', review.ReviewNativeBlock.as_view()),
]


@override_settings(LOCAL_DEMO=True, ROOT_URLCONF=__name__)
class YoutubeReviewApiTests(TransactionTestCase):
    def setUp(self):
        temporary_root = settings.BASE_DIR / '.local-preview-logs'
        temporary_root.mkdir(parents=True, exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=temporary_root)
        self.addCleanup(self.directory.cleanup)
        override = override_settings(YOUTUBE_REGISTRY_PATH=Path(self.directory.name) / 'mappings.sqlite3',
            YOUTUBE_REVIEW_ACCESS_FILE=Path(self.directory.name) / 'access.json')
        override.enable()
        self.addCleanup(override.disable)
        registry.initialize_access_code()
        self.code = json.loads(registry.access_code_path().read_text())['access_code']
        self.headers = {'HTTP_X_YOUTUBE_REVIEW_CODE': self.code}
        self.tracks = [{'track_id': 'track-one', 'track_name': 'First song', 'artists_name': 'First artist', 'duration_ms': 240000},
                       {'track_id': 'track-two', 'track_name': 'Second song', 'artists_name': 'Second artist', 'duration_ms': 240000}]
        self.catalog = Catalog.objects.create(version='general-test', tracks=self.tracks, sha256='a'*64,
                                             source_ref='local-preview:general', source_sha256='b'*64, is_test=True, ready=True)
        self.client.get('/api/c-demo/context')

    def post(self, suffix, body, headers=None, client=None):
        return (client or self.client).post('/api/youtube-review/' + suffix, body, content_type='application/json',
                                           **(self.headers if headers is None else headers))

    def test_status_has_no_secret_and_all_review_routes_require_local_code(self):
        response = self.client.get('/api/youtube-review/status')
        self.assertNotIn(self.code, response.content.decode())
        self.assertTrue(response.json()['enabled'])
        self.assertEqual(self.client.get('/api/youtube-review/tracks').status_code, 403)
        response = self.post('mappings', {'track_id': 'track-one', 'video_url': 'testVideo01', 'expected_revision': 0}, {})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(registry.track_registry('track-one')['mappings'], [])

    def test_registration_verification_block_and_filtered_review_queue(self):
        response = self.post('mappings', {'track_id': 'track-one', 'video_url': 'testVideo01', 'expected_revision': 0})
        self.assertEqual(response.status_code, 200, response.content)
        response = self.client.get('/api/youtube-review/tracks?status=PENDING', **self.headers)
        self.assertEqual(response.json()['total'], 1)
        self.assertEqual(response.json()['summary'], {'total': 2, 'unmapped': 1, 'pending': 1, 'verified': 0, 'blocked': 0})
        response = self.post('verify', {'track_id': 'track-one', 'video_id': 'testVideo01', 'expected_revision': 1,
            'identity_confirmed': True, 'playback_observed': True, 'duration_seconds': 241})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['mappings'][0]['status'], 'VERIFIED')
        response = self.post('block', {'track_id': 'track-one', 'video_id': 'testVideo01', 'expected_revision': 2, 'reason': 'Embedding failed'})
        self.assertEqual(response.status_code, 200, response.content)
        response = self.client.get('/api/youtube-review/tracks?status=BLOCKED&q=First', **self.headers)
        self.assertEqual(response.json()['total'], 1)
        self.assertEqual(registry.verified_candidates('track-one'), [])
        self.catalog.refresh_from_db()
        self.assertEqual(self.catalog.tracks, self.tracks)
        self.assertEqual(Job.objects.count(), 0)

    def test_unknown_track_in_later_csv_row_prevents_all_writes(self):
        response = self.post('import', {'csv_text': 'track_id,video_url,expected_revision\ntrack-one,testVideo01,0\nunknown,nextVideo02,0\n'})
        self.assertEqual(response.status_code, 422, response.content)
        self.assertEqual(response.json()['code'], 'TRACK_NOT_FOUND')
        self.assertEqual(response.json()['details']['row_errors'][0]['row'], 3)
        self.assertEqual(registry.track_registry('track-one')['mappings'], [])

    def test_csv_duplicate_stale_and_unsupported_fields_are_rejected(self):
        self.post('mappings', {'track_id': 'track-one', 'video_url': 'testVideo01', 'expected_revision': 0})
        response = self.post('import', {'csv_text': 'track_id,video_url,expected_revision\ntrack-two,nextVideo02,0\ntrack-one,lastVideo03,0\n'})
        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.json()['details']['row_errors'][0]['row'], 3)
        self.assertEqual(registry.track_registry('track-two')['mappings'], [])
        response = self.post('mappings', {'track_id': 'track-one', 'video_url': 'testVideo01', 'expected_revision': 1, 'status': 'VERIFIED'})
        self.assertEqual(response.status_code, 422)

    def test_owned_playlist_scope_does_not_expose_foreign_results(self):
        self.client.get('/api/youtube-review/tracks', **self.headers)
        owner = self.client.session['c_demo_owner']
        family = Family.objects.create(owner_id=owner, options={}, policy_version='test', mapping_version='test')
        job = Job.objects.create(family=family, input={}, catalog=self.catalog, request_id='test-owned')
        playlist = Playlist.objects.create(job=job, family=family, snapshot={'items': self.tracks[:1]})
        response = self.client.get(f'/api/youtube-review/tracks?playlist_id={playlist.pk}', **self.headers)
        self.assertEqual(response.json()['total'], 1)
        other = Client()
        other.get('/api/c-demo/context')
        response = other.get(f'/api/youtube-review/tracks?playlist_id={playlist.pk}', **self.headers)
        self.assertEqual(response.status_code, 404)

    def test_csrf_required_with_valid_review_code(self):
        strict = Client(enforce_csrf_checks=True)
        strict.cookies = self.client.cookies
        response = self.post('mappings', {'track_id': 'track-one', 'video_url': 'testVideo01', 'expected_revision': 0}, client=strict)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['code'], 'CSRF_FAILED')

    def test_owned_historical_track_registration_survives_catalog_replacement(self):
        owner=self.client.session['c_demo_owner']
        family=Family.objects.create(owner_id=owner,options={},policy_version='test',mapping_version='test')
        job=Job.objects.create(family=family,input={},catalog=self.catalog,request_id='historical-review')
        historical={**self.tracks[0],'track_id':'historical-retired-track'}
        playlist=Playlist.objects.create(job=job,family=family,snapshot={'items':[historical]})
        body={'track_id':historical['track_id'],'video_url':'testVideo01','expected_revision':0,'playlist_id':playlist.pk}
        response=self.post('mappings',body)
        self.assertEqual(response.status_code,200,response.content)
        other=Client();other.get('/api/c-demo/context')
        self.assertEqual(self.post('mappings',{**body,'expected_revision':1},client=other).status_code,404)

    def test_unclosed_csv_quote_rejects_entire_import(self):
        cases=[('track_id,video_url,expected_revision,note\ntrack-one,testVideo01,0,"unclosed note','CSV_ROW_INVALID'),
               ('"track_id,video_url,expected_revision,note\n','CSV_HEADERS_INVALID')]
        for content,code in cases:
            with self.subTest(code=code):
                response=self.post('import',{'csv_text':content})
                self.assertEqual(response.status_code,422,response.content)
                self.assertEqual(response.json()['code'],code)
                self.assertEqual(registry.track_registry('track-one')['mappings'],[])

    @override_settings(LOCAL_DEMO=False)
    def test_production_disabled_and_rejects_even_valid_local_code(self):
        self.assertFalse(self.client.get('/api/youtube-review/status').json()['enabled'])
        response = self.client.get('/api/youtube-review/tracks', **self.headers)
        self.assertEqual(response.status_code, 503)

    def test_native_review_keeps_iframe_blocked_but_counts_as_playback_ready(self):
        self.post('mappings', {'track_id': 'track-one', 'video_url': 'testVideo01', 'expected_revision': 0})
        self.post('block', {'track_id': 'track-one', 'video_id': 'testVideo01', 'expected_revision': 1, 'reason': 'Iframe error 150'})
        response = self.post('native-verify', {'track_id': 'track-one', 'video_id': 'testVideo01', 'expected_revision': 2,
            'identity_confirmed': True, 'playback_observed': True, 'duration_seconds': 241})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()['mappings'][0]['native_verified'])
        self.assertEqual(response.json()['mappings'][0]['status'], 'BLOCKED')
        response = self.client.get('/api/youtube-review/tracks?status=VERIFIED', **self.headers)
        self.assertEqual(response.json()['total'], 1)
        self.assertEqual(response.json()['summary']['verified'], 1)
        self.assertEqual(response.json()['summary']['blocked'], 0)
        response = self.post('native-block', {'track_id': 'track-one', 'video_id': 'testVideo01', 'expected_revision': 3,
            'reason': 'Native video removed'})
        self.assertEqual(response.status_code, 200, response.content)
        mapping = response.json()['mappings'][0]
        self.assertFalse(mapping['native_verified'])
        self.assertEqual(mapping['native_reason'], 'Native video removed')
        self.assertEqual(mapping['status'], 'BLOCKED')
