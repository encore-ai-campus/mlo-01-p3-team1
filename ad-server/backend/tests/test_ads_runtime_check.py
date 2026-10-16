"""배포 전 점검이 원본/claim을 바꾸거나 외부 연결을 성공으로 꾸미지 않는지 확인합니다."""

import json
from copy import deepcopy
from io import StringIO
from unittest.mock import MagicMock, Mock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from workers.ads_runtime_check import (
    check_configuration,
    expected_collections,
    inspect_runtime,
    schema_issues,
)

CONFIGURATION = {
    "ADS_MONGODB_URI": "mongodb://127.0.0.1:27019/?directConnection=true",
    "ADS_MONGODB_DATABASE": "fixture_dev",
    "ADS_IS_TEST": False,
    "ADS_ADMIN_AUTHORIZER": "api.ads_sandbox.sandbox_admin",
    "ADS_GUEST_CONTEXT_PROVIDER": "api.ads_sandbox.sandbox_guest",
    "ADS_PUBLIC_POLICY_PROVIDER": "domains.ads.runtime_policy.get_public_policy",
    "ADS_DELIVERY_SIGNING_KEY": "fixture-key-not-an-operating-key",
    "ADS_PUBLIC_BASE_URL": "https://example.test",
}


def schema_database():
    database = MagicMock()
    manifest = expected_collections()
    database.list_collections.return_value = [
        {"name": name, "options": {"validator": deepcopy(spec["validator"])}}
        for name, spec in manifest.items()
    ]
    collections = {}
    for name, spec in manifest.items():
        collection = MagicMock()
        collection.index_information.return_value = {
            index["name"]: {
                "key": [tuple(key) for key in index["keys"]],
                **{
                    key: deepcopy(value)
                    for key, value in index.items()
                    if key not in {"name", "keys"}
                },
            }
            for index in spec["indexes"]
        }
        collection.count_documents.return_value = 0
        collection.find_one.return_value = None
        collections[name] = collection
    database.__getitem__.side_effect = collections.__getitem__
    return database, collections


@override_settings(**CONFIGURATION)
class AdsRuntimeCheckTests(SimpleTestCase):
    def test_configuration_inspection_does_not_call_auth_or_sink_or_database(self):
        sink = Mock()
        with (
            self.settings(ADS_LOG_SINK=sink),
            patch("workers.ads_runtime_check.get_ads_policy_repository") as factory,
        ):
            report = inspect_runtime()
        self.assertTrue(all(report["configuration"].values()))
        self.assertEqual(report["database"]["status"], "NOT_CHECKED")
        self.assertEqual(report["status"], "INCOMPLETE")
        self.assertFalse(report["shared_authentication_verified"])
        self.assertEqual(report["log_storage"], "MONGODB")
        factory.assert_not_called()
        sink.assert_not_called()

    def test_missing_import_and_invalid_public_url_are_not_echoed(self):
        with self.settings(
            ADS_LOG_SINK="postgresql://password@private-host",
            ADS_ADMIN_AUTHORIZER="private-nonexistent.module",
            ADS_PUBLIC_BASE_URL="https://user:secret@example.test",
        ):
            checks = check_configuration()
        self.assertNotIn("log_sink_loadable", checks)
        self.assertFalse(checks["admin_adapter_loadable"])
        self.assertFalse(checks["public_policy_settings_valid"])
        self.assertNotIn("secret", json.dumps(checks))
        self.assertNotIn("private-host", json.dumps(checks))

    def test_expected_schema_passes_and_missing_collection_is_reported(self):
        database, _ = schema_database()
        self.assertFalse(schema_issues(database))
        database.list_collections.return_value = []
        issues = schema_issues(database)
        self.assertEqual(len(issues), 10)
        self.assertEqual({v["code"] for v in issues}, {"MISSING_COLLECTION"})
        database.create_collection.assert_not_called()
        database.command.assert_not_called()

    def test_validator_weakening_unique_drift_and_unexpected_ttl_fail_checks(self):
        database, collections = schema_database()
        database.list_collections.return_value[0]["options"]["validationAction"] = "warn"
        collections["ad_events"].index_information.return_value["public_event_id"]["unique"] = False
        collections["ad_deliveries"].index_information.return_value["public_delivery_request"].pop(
            "partialFilterExpression"
        )
        collections["ad_admin_changes"].index_information.return_value["dangerous_ttl"] = {
            "key": [("created_at", 1)],
            "expireAfterSeconds": 10,
        }
        issues = schema_issues(database)
        codes = {v["code"] for v in issues}
        self.assertTrue({"VALIDATOR_MISMATCH", "INDEX_MISMATCH", "UNEXPECTED_TTL"} <= codes)

    def test_database_exception_redacts_connection_details(self):
        repository = Mock()
        type(repository).database = property(
            lambda _: (_ for _ in ()).throw(RuntimeError("mongodb://password@private-host"))
        )
        with self.settings(ADS_LOG_SINK=lambda *args: True):
            report = inspect_runtime(check_database=True, repository=repository)
        self.assertEqual(report["database"], {"status": "ERROR", "error_type": "RuntimeError"})
        self.assertNotIn("password", json.dumps(report))

    def test_passing_local_checks_still_do_not_claim_shared_auth_or_postgres_commit(self):
        database, _ = schema_database()
        repository = Mock(database=database, is_test=False)
        with self.settings(ADS_LOG_SINK=lambda *args: True):
            report = inspect_runtime(check_database=True, repository=repository)
        self.assertEqual(report["status"], "CHECKS_PASSED")
        self.assertFalse(report["shared_authentication_verified"])
        self.assertEqual(report["log_storage"], "MONGODB")

    def test_command_without_database_flag_returns_unconfirmed_with_nonzero_semantics(self):
        with self.settings(ADS_LOG_SINK=""):
            output = StringIO()
            with self.assertRaises(CommandError):
                call_command("check_ads_runtime", stdout=output)
        self.assertEqual(json.loads(output.getvalue())["database"]["status"], "NOT_CHECKED")

    def test_command_can_return_successful_bounded_report(self):
        report = {"status": "CHECKS_PASSED"}
        with patch(
            "domains.ads.management.commands.check_ads_runtime.inspect_runtime",
            return_value=report,
        ) as inspect:
            output = StringIO()
            call_command("check_ads_runtime", database=True, stdout=output)
        inspect.assert_called_once_with(check_database=True)
        self.assertEqual(json.loads(output.getvalue()), report)
