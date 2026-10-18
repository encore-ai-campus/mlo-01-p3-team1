"""MongoDB 내장 광고 로그의 무결성·이전 자료 호환·외부 전달 제거를 검증합니다."""

import json
from copy import deepcopy
from datetime import UTC, datetime
from io import StringIO
from unittest.mock import MagicMock, Mock, patch

from django.core.management import call_command, get_commands
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from domains.ads.service import canonical_hash
from workers.ads_logs import LOG_COLLECTIONS, inspect_logs


def local_record():
    payload = {"log_event_id": "ads-management:fixture", "result": "CHANGED"}
    return {
        "log_event_id": payload["log_event_id"],
        "log_schema_version": "ads-mongo-log-20261015.1",
        "payload": payload,
        "payload_hash": canonical_hash(payload),
        "stored_at": datetime(2026, 10, 15, tzinfo=UTC),
    }


def log_database(documents):
    database = MagicMock()
    collections = {}
    for name in LOG_COLLECTIONS:
        collection = MagicMock()
        collection.count_documents.side_effect = [0, len(documents), 0]
        collection.find.return_value.sort.return_value.limit.return_value = deepcopy(documents)
        collections[name] = collection
    database.__getitem__.side_effect = collections.__getitem__
    return database, collections


class AdsLogsTests(SimpleTestCase):
    def test_valid_local_records_are_read_only_and_environment_scoped(self):
        database, collections = log_database([{"log_record": local_record()}])
        report = inspect_logs(database, is_test=False, limit=7)
        for name, row in report.items():
            self.assertEqual(row["sample_checked"], 1)
            self.assertEqual(row["sample_invalid"], 0)
            self.assertEqual(row["sample_document_limit"], 7)
            collection = collections[name]
            for call in collection.count_documents.call_args_list:
                self.assertIs(call.args[0]["is_test"], False)
            collection.find.assert_called_once()
            self.assertIs(collection.find.call_args.args[0]["is_test"], False)
            collection.find.return_value.sort.return_value.limit.assert_called_once_with(7)
            collection.update_one.assert_not_called()
            collection.find_one_and_update.assert_not_called()
            collection.delete_many.assert_not_called()

    def test_legacy_pending_is_preserved_without_fake_sent_ack(self):
        legacy = local_record()
        legacy.update(status="PENDING", attempt_count=3, last_error="old-error")
        del legacy["log_schema_version"], legacy["stored_at"]
        document = {"log_relay": legacy}
        original = deepcopy(document)
        database, collections = log_database([document])
        report = inspect_logs(database, is_test=True)
        self.assertTrue(all(row["sample_invalid"] == 0 for row in report.values()))
        self.assertEqual(document, original)
        for collection in collections.values():
            collection.update_one.assert_not_called()

    def test_corrupt_hash_id_and_timestamp_are_reported_without_payload(self):
        for field, value in (
            ("payload_hash", "bad"),
            ("log_event_id", "wrong"),
            ("stored_at", None),
        ):
            with self.subTest(field=field):
                record = local_record()
                record[field] = value
                database, _ = log_database([{"log_record": record}])
                report = inspect_logs(database, is_test=False)
                self.assertTrue(all(row["sample_invalid"] == 1 for row in report.values()))
                self.assertNotIn("CHANGED", json.dumps(report))

    def test_invalid_configuration_is_rejected_before_database_access(self):
        database = MagicMock()
        for limit in (0, 101, True):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                inspect_logs(database, is_test=True, limit=limit)
        with self.assertRaises(ValueError):
            inspect_logs(database, is_test="false")
        database.__getitem__.assert_not_called()

    @override_settings(ADS_LOG_SINK="this.setting.must.never.load")
    def test_command_uses_only_mongo_and_retired_relay_commands_are_absent(self):
        database, _ = log_database([{"log_record": local_record()}])
        repository = Mock(database=database, is_test=True)
        with patch(
            "domains.ads.management.commands.check_ads_logs.get_ads_policy_repository",
            return_value=repository,
        ):
            output = StringIO()
            call_command("check_ads_logs", limit=5, stdout=output)
        self.assertEqual(set(json.loads(output.getvalue())), set(LOG_COLLECTIONS))
        for name in ("relay_ads_logs", "relay_ads_event_logs", "relay_ads_budget_logs"):
            self.assertNotIn(name, get_commands())

    def test_command_failure_redacts_database_credentials(self):
        with patch(
            "domains.ads.management.commands.check_ads_logs.get_ads_policy_repository",
            side_effect=RuntimeError("mongodb://secret@private-host"),
        ):
            with self.assertRaises(CommandError) as raised:
                call_command("check_ads_logs", stdout=StringIO())
        self.assertNotIn("secret", str(raised.exception))

    def test_command_reports_missing_log_with_nonzero_exit(self):
        database, collections = log_database([])
        for collection in collections.values():
            collection.count_documents.side_effect = [1, 0, 0]
        with patch(
            "domains.ads.management.commands.check_ads_logs.get_ads_policy_repository",
            return_value=Mock(database=database, is_test=False),
        ):
            with self.assertRaises(CommandError):
                call_command("check_ads_logs", stdout=StringIO())
