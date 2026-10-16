import io
from unittest.mock import patch
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase


class RuntimeCommandsTests(SimpleTestCase):
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
