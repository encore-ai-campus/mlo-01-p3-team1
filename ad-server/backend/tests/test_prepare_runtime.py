import io
from unittest.mock import MagicMock, patch
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings
from domains.ads.management.commands.prepare_ads_runtime import prepare


class PrepareRuntimeTests(SimpleTestCase):
    def test_configuration_check_never_connects(self):
        with patch('domains.ads.management.commands.check_ads_configuration.check_configuration',return_value={'ok':True}),override_settings(ADS_COMMON_API_URL='https://common',ADS_INTERNAL_SECRET='test'),patch('domains.ads.management.commands.prepare_ads_runtime.MongoClient') as client:
            call_command('check_ads_configuration',stdout=io.StringIO())
        client.assert_not_called()

    def test_dry_run_does_not_connect(self):
        with patch('domains.ads.management.commands.prepare_ads_runtime.MongoClient') as client:
            call_command('prepare_ads_runtime',stdout=io.StringIO())
        client.assert_not_called()

    def test_conflicting_validator_is_not_modified(self):
        database=MagicMock()
        database.list_collections.return_value=[{'name':'ads','options':{'validator':{'different':True}}}]
        with self.assertRaises(CommandError):prepare(database,{'ads':{'validator':{},'indexes':[]}})
        database.create_collection.assert_not_called();database.command.assert_not_called()

    @override_settings(ADS_MONGODB_URI='mongodb://configured-host/?replicaSet=actual-rs',ADS_MONGODB_DATABASE='advertising')
    def test_remote_replica_name_is_configurable(self):
        client=MagicMock();client.__enter__.return_value=client
        client.admin.command.return_value={'setName':'actual-rs','isWritablePrimary':True}
        with patch('domains.ads.management.commands.prepare_ads_runtime.MongoClient',return_value=client),patch('domains.ads.management.commands.prepare_ads_runtime.prepare'),patch('domains.ads.management.commands.prepare_ads_runtime.schema_issues',return_value=[]):
            call_command('prepare_ads_runtime',apply=True,stdout=io.StringIO())
        client.admin.command.assert_called_once_with('hello')
