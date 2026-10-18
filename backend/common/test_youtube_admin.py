"""Exercise shared sessions/permissions/CSRF against an isolated review registry."""
import tempfile
from pathlib import Path
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, Client, override_settings
from backend.recommendation.models import Catalog
from backend.recommendation import youtube_registry as registry


@override_settings(LOCAL_DEMO=True, ADMIN_SESSION_SECONDS=600)
class YoutubeAdminTests(TestCase):
    def setUp(self):
        temporary_root = settings.BASE_DIR / '.local-preview-logs'
        temporary_root.mkdir(exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=temporary_root)
        self.addCleanup(self.directory.cleanup)
        self.registry_file = Path(self.directory.name) / 'registry.sqlite3'
        self.override = override_settings(YOUTUBE_REGISTRY_PATH=self.registry_file,
            YOUTUBE_REVIEW_ACCESS_FILE=Path(self.directory.name) / 'excluded-access.json')
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.user = get_user_model().objects.create_user('music-reviewer', password='A-test-password-123', is_staff=True)
        self.user.user_permissions.add(Permission.objects.get(codename='manage_music', content_type__app_label='common'))
        Catalog.objects.create(version='admin-test', sha256='test', tracks=[{
            'track_id':'track-one', 'track_name':'One', 'artists_name':'Artist', 'duration_ms':180000}],
            source_ref='local-preview:test', is_test=True, ready=True)
        self.client = Client(enforce_csrf_checks=True)

    def authenticate(self):
        self.client.force_login(self.user)
        return self.client.get('/api/auth/me').json()['csrf_token']

    def post(self, suffix, body, csrf):
        return self.client.post('/api/admin/youtube-review/'+suffix, body,
            content_type='application/json', HTTP_X_CSRFTOKEN=csrf)

    def test_common_login_music_only_menu_and_no_external_redirect(self):
        token = self.client.get('/api/auth/me').json()['csrf_token']
        response = self.client.post('/api/auth/login', {'username':'music-reviewer','password':'A-test-password-123'},
            content_type='application/json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['landing_path'], '/admin/music')
        self.assertEqual([m['path'] for m in response.json()['allowed_menus']], ['/admin/music','/admin/music/youtube'])
        status = self.client.get('/api/admin/youtube-review/status').json()
        self.assertEqual(status, {'enabled':True,'is_test':True,'auth_mode':'ADMIN_SESSION'})
        self.assertFalse((Path(self.directory.name)/'excluded-access.json').exists())

    def test_anonymous_and_ads_permission_cannot_use_review(self):
        self.assertEqual(self.client.get('/api/admin/youtube-review/tracks', HTTP_X_YOUTUBE_REVIEW_CODE='not-an-admin-session').status_code,401)
        self.user.user_permissions.clear()
        self.user.user_permissions.add(Permission.objects.get(codename='manage_ads', content_type__app_label='common'))
        self.authenticate()
        self.assertEqual(self.client.get('/api/admin/youtube-review/tracks').status_code,403)
        self.assertFalse(self.registry_file.exists())

    def test_csrf_registration_native_review_and_iframe_independence(self):
        token = self.authenticate()
        row = {'track_id':'track-one','video_url':'testVideo01','expected_revision':0}
        self.assertEqual(self.post('mappings', row, '').status_code,403)
        self.assertEqual(self.post('mappings', row, token).status_code,200)
        result = self.post('native-verify', {'track_id':'track-one','video_id':'testVideo01',
            'expected_revision':1,'identity_confirmed':True,'playback_observed':True,'duration_seconds':180}, token)
        self.assertEqual(result.status_code,200,result.content)
        saved = registry.track_registry('track-one')['mappings'][0]
        self.assertTrue(saved['native_verified'])
        self.assertEqual(saved['status'],'CANDIDATE')
        self.assertEqual(self.client.get('/api/admin/youtube-review/tracks').json()['summary']['verified'],1)

    def test_conflict_and_unknown_track_do_not_partially_import(self):
        token = self.authenticate()
        row = {'track_id':'track-one','video_url':'testVideo01','expected_revision':0}
        self.assertEqual(self.post('mappings', row, token).status_code,200)
        response = self.post('import', {'csv_text':'track_id,video_url,expected_revision\ntrack-one,nextVideo02,0\n'}, token)
        self.assertEqual(response.status_code,409)
        self.assertEqual(response.json()['code'],'MAPPING_REVISION_CONFLICT')
        response = self.post('import', {'csv_text':'track_id,video_url,expected_revision\ntrack-one,nextVideo02,1\nunknown,lastVideo03,0\n'}, token)
        self.assertEqual(response.status_code,422)
        self.assertEqual(len(registry.track_registry('track-one')['mappings']),1)

    def test_permission_revocation_logout_and_snapshot_scope(self):
        token = self.authenticate()
        self.assertEqual(self.client.get('/api/admin/youtube-review/tracks?playlist_id=another-person').status_code,422)
        self.assertEqual(self.post('mappings', {'playlist_id':'another-person'},token).status_code,422)
        self.user.user_permissions.clear()
        self.assertEqual(self.client.get('/api/admin/youtube-review/tracks').status_code,403)
        self.client.logout()
        self.assertEqual(self.client.get('/api/admin/youtube-review/status').status_code,401)

    def test_production_registry_remains_unavailable(self):
        self.authenticate()
        with override_settings(LOCAL_DEMO=False):
            self.assertFalse(self.client.get('/api/admin/youtube-review/status').json()['enabled'])
            self.assertEqual(self.client.get('/api/admin/youtube-review/tracks').status_code,503)
        self.assertFalse(self.registry_file.exists())

    def test_account_without_management_permissions_cannot_login(self):
        self.user.user_permissions.clear()
        token = self.client.get('/api/auth/me').json()['csrf_token']
        response = self.client.post('/api/auth/login', {'username':'music-reviewer','password':'A-test-password-123'},
            content_type='application/json', HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code,403)
