import io
from unittest.mock import patch
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings


class RuntimeCommandsTests(SimpleTestCase):
    @override_settings(MUSIC_S3_ARCHIVE_DEFERRED=True)
    def test_deferred_archive_is_explicit_and_does_not_hide_database_failure(self):
        path='backend.common.management.commands.check_runtime'
        checks={'postgres':{'ok':True},'music_archive_versioning':{'ok':None,'status':'DEFERRED'}}
        with patch(path+'.configuration',return_value={'setting':True}),patch(path+'.connections',return_value=checks):
            result=io.StringIO();call_command('check_runtime',connect=True,stdout=result)
        self.assertIn('STORAGE_READY_ARCHIVE_DEFERRED',result.getvalue())
        checks['postgres']={'ok':False}
        with patch(path+'.configuration',return_value={'setting':True}),patch(path+'.connections',return_value=checks):
            with self.assertRaises(CommandError):call_command('check_runtime',connect=True,stdout=io.StringIO())

    @override_settings(MUSIC_S3_ARCHIVE_DEFERRED=True)
    def test_deferred_archive_requires_a_preserved_local_original(self):
        import hashlib,tempfile
        from pathlib import Path
        from backend.common.music_archive import store
        from backend.recommendation.errors import DomainError
        with tempfile.TemporaryDirectory() as folder,override_settings(MUSIC_RAW_DIRECTORY=folder):
            path=Path(folder)/'source.csv';path.write_bytes(b'track_id\n')
            with patch('boto3.client') as client:
                result=store(path,hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(result['mode'],'S3_DEFERRED');client.assert_not_called()
            with override_settings(MUSIC_RAW_DIRECTORY=folder+'/other'):
                with self.assertRaises(DomainError):store(path,hashlib.sha256(path.read_bytes()).hexdigest())

    def test_prepare_dry_run_never_migrates_or_imports(self):
        with patch('backend.common.management.commands.prepare_runtime.call_command') as run:
            call_command('prepare_runtime',music=True,streams=True,stdout=io.StringIO())
        run.assert_not_called()

    def test_config_check_does_not_open_connections(self):
        path='backend.common.management.commands.check_runtime'
        with patch(path+'.configuration',return_value={'setting':True}),patch(path+'.connections') as connect:
            result=io.StringIO();call_command('check_runtime',stdout=result)
        connect.assert_not_called();self.assertIn('NOT_CONNECTED',result.getvalue())

    def test_connection_failure_cannot_be_reported_ready(self):
        path='backend.common.management.commands.check_runtime'
        with patch(path+'.configuration',return_value={'setting':True}),patch(path+'.connections',return_value={'postgres':{'ok':False}}):
            result=io.StringIO()
            with self.assertRaises(CommandError):call_command('check_runtime',connect=True,stdout=result)
        self.assertIn('NOT_READY',result.getvalue())

    def test_music_pending_can_start_admin_but_not_claim_recommendations_ready(self):
        path='backend.common.management.commands.check_runtime'
        with patch(path+'.configuration',return_value={'setting':True}),patch(path+'.connections',return_value={'postgres':{'ok':True},'active_catalog':{'ok':False}}):
            result=io.StringIO()
            call_command('check_runtime',connect=True,allow_pending_music=True,stdout=result)
        self.assertIn('ADMIN_READY_MUSIC_PENDING',result.getvalue())
        self.assertIn('"ready": false',result.getvalue())


class PreparedAccountTests(TestCase):
    def test_existing_admin_is_not_reset_by_preparation(self):
        from django.contrib.auth import get_user_model
        user=get_user_model().objects.create_user('configured-admin',password='Existing-only-123!',is_staff=True)
        original=user.password
        with patch.dict('os.environ',{'BOOTSTRAP_ADMIN_USERNAME':'configured-admin','BOOTSTRAP_ADMIN_PASSWORD':'replacement-must-not-apply','BOOTSTRAP_ADMIN_PERMISSIONS':'manage_ads'}),patch('backend.common.management.commands.prepare_runtime.call_command') as execute:
            call_command('prepare_runtime',apply=True,stdout=io.StringIO())
        user.refresh_from_db()
        self.assertEqual(user.password,original);self.assertFalse(user.user_permissions.exists())
        self.assertEqual(execute.call_count,1)
        self.assertEqual(execute.call_args.args[0],'migrate')

    def test_new_admin_requires_explicit_permissions(self):
        from django.contrib.auth import get_user_model
        with patch.dict('os.environ',{'BOOTSTRAP_ADMIN_USERNAME':'new-admin','BOOTSTRAP_ADMIN_PASSWORD':'Test-only-123!','BOOTSTRAP_ADMIN_PERMISSIONS':''}),patch('backend.common.management.commands.prepare_runtime.call_command'):
            with self.assertRaisesRegex(CommandError,'permissions_required'):
                call_command('prepare_runtime',apply=True,stdout=io.StringIO())
        self.assertFalse(get_user_model().objects.filter(username='new-admin').exists())


class DeferredPublicationTests(TestCase):
    def test_publication_still_requires_explicit_deferral_review_and_preserved_bytes(self):
        import hashlib
        import tempfile
        from pathlib import Path
        from types import SimpleNamespace
        from django.contrib.auth import get_user_model
        from django.contrib.auth.models import Permission
        from backend.common.models import MusicSource, Review
        from backend.music.models import Album, Track
        user=get_user_model().objects.create_user('publisher',password='Test-only-pass-123',is_staff=True)
        user.user_permissions.add(Permission.objects.get(content_type__app_label='common',codename='manage_music'))
        from .admin_roles import assign_role
        assign_role(user,'OPS_ADMIN')
        self.client.force_login(user)
        album=Album.objects.create(album_name='test album')
        track=Track.objects.create(track_id='test-track',track_name='test',artists_name='test',album=album,
                                   duration_ms=180000,explicit=False,play_url='https://example.com/track')
        review=Review.objects.create(track=track,status='approved')
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'source.csv';path.write_bytes(b'track_id\ntest-track\n')
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            MusicSource.objects.create(sha256=digest,schema='spotify-raw20-v1',raw_path=str(path),
                                       archive={'mode':'S3_DEFERRED','sha256':digest})
            body={'version':'test-version','source_ref':'music-source:'+digest,'source_sha256':digest}
            fake=SimpleNamespace(pk='test-version',sha256='a'*64,ready=True)
            def post(key):
                return self.client.post('/api/admin/music/catalogs',body,content_type='application/json',HTTP_IDEMPOTENCY_KEY=key)
            with patch('backend.common.music_api.publish',return_value=fake) as publish:
                with override_settings(LOCAL_DEMO=False,MUSIC_S3_ARCHIVE_DEFERRED=False):
                    self.assertEqual(post('archive-required').status_code,503)
                publish.assert_not_called()
                with override_settings(LOCAL_DEMO=False,MUSIC_S3_ARCHIVE_DEFERRED=True):
                    self.assertEqual(post('explicitly-deferred').status_code,201)
                    path.write_bytes(b'corrupt')
                    self.assertEqual(post('corrupted-source').status_code,503)
                    review.status='draft';review.save(update_fields=['status'])
                    self.assertEqual(post('review-still-required').status_code,409)
                publish.assert_called_once()
