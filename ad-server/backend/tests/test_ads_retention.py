"""보관 기산점·경계·불확정 제외와 읽기 전용 점검을 검증합니다."""

import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from io import StringIO
from unittest.mock import MagicMock, Mock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from workers.ads_retention import (
    PROJECTION,
    RETENTION_DAYS,
    UNRESOLVED_COLLECTIONS,
    inspect_retention,
    reference_observations,
    retention_state,
)


def retention_database(documents):
    database = MagicMock()
    collections = {}
    for name in (*RETENTION_DAYS, *UNRESOLVED_COLLECTIONS):
        rows = deepcopy(documents.get(name, []))
        collection = MagicMock()
        collection.count_documents.return_value = len(rows)
        collection.find.return_value.sort.return_value.limit.return_value = rows
        collection.find_one.return_value = None
        collections[name] = collection
    database.__getitem__.side_effect = collections.__getitem__
    return database, collections


class AdsRetentionTests(SimpleTestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 16, tzinfo=UTC)

    def state(self, name, document, now=None):
        return retention_state(name, document, now=now or self.now)

    def test_event_uses_first_received_time_and_exact_ninety_day_boundary(self):
        document = {"received_at": self.now - timedelta(days=90), "processed_at": self.now}
        self.assertEqual(self.state("ad_events", document)["status"], "REVIEW_DUE")
        before = self.now - timedelta(milliseconds=1)
        self.assertEqual(self.state("ad_events", document, before)["status"], "WITHIN_RETENTION")

    def test_delivery_uses_later_real_use_or_first_new_event_receipt(self):
        document = {
            "last_used_at": self.now - timedelta(days=100),
            "last_received_at": self.now - timedelta(days=89),
            "issued_at": self.now - timedelta(days=200),
        }
        self.assertEqual(self.state("ad_deliveries", document)["status"], "WITHIN_RETENTION")
        document["last_received_at"] = None
        self.assertEqual(self.state("ad_deliveries", document)["status"], "REVIEW_DUE")

    def test_admin_and_ledger_keep_distinct_365_day_bases(self):
        for name, field in (
            ("ad_admin_changes", "occurred_at"),
            ("ad_estimated_usage_ledger", "processed_at"),
        ):
            with self.subTest(collection=name):
                document = {field: self.now - timedelta(days=365), "changed": True}
                self.assertEqual(self.state(name, document)["status"], "REVIEW_DUE")
                self.assertEqual(
                    self.state(name, document, self.now - timedelta(milliseconds=1))["status"],
                    "WITHIN_RETENTION",
                )

    def test_metrics_uses_next_kst_midnight_instead_of_refresh_time(self):
        document = {"metric_date_kst": "2025-10-14", "as_of": self.now}
        due = datetime(2026, 10, 14, 15, tzinfo=UTC)
        self.assertEqual(self.state("ad_daily_metrics", document, due)["status"], "REVIEW_DUE")
        self.assertEqual(
            self.state("ad_daily_metrics", document, due - timedelta(milliseconds=1))["status"],
            "WITHIN_RETENTION",
        )

    def test_noop_management_retention_is_pending(self):
        self.assertEqual(
            self.state("ad_admin_changes", {"changed": False}),
            {"status": "POLICY_PENDING", "due_at": None},
        )

    def test_missing_naive_future_invalid_or_overflow_bases_are_reported(self):
        for name, document in (
            ("ad_events", {}),
            ("ad_events", {"received_at": datetime(2026, 1, 1)}),
            ("ad_events", {"received_at": self.now + timedelta(seconds=1)}),
            ("ad_daily_metrics", {"metric_date_kst": "20251014"}),
            ("ad_daily_metrics", {"metric_date_kst": "9999-12-31"}),
            ("ad_admin_changes", {"changed": "false", "occurred_at": self.now}),
        ):
            with self.subTest(collection=name, document=document):
                self.assertEqual(self.state(name, document)["status"], "INVALID_BASIS")
        with self.assertRaises(ValueError):
            self.state("ad_assets", {"created_at": self.now})

    def test_inspection_is_bounded_environment_scoped_and_never_mutates(self):
        document = {"_id": "do-not-echo", "received_at": self.now - timedelta(days=91)}
        database, collections = retention_database({"ad_events": [document, document]})
        report = inspect_retention(database, is_test=False, limit=1, now=self.now)
        event = report["collections"]["ad_events"]
        self.assertTrue(event["sample_has_more"])
        self.assertEqual(event["sample_checked"], 1)
        self.assertEqual(event["sample_statuses"], {"REVIEW_DUE": 1})
        self.assertFalse(report["deletion_allowed"])
        self.assertFalse(report["snapshot_consistent"])
        self.assertNotIn("do-not-echo", json.dumps(report))
        for name, collection in collections.items():
            collection.count_documents.assert_called_once_with({"is_test": False})
            if name in RETENTION_DAYS:
                collection.find.assert_called_once_with({"is_test": False}, PROJECTION)
                collection.find.return_value.sort.return_value.limit.assert_called_once_with(2)
            else:
                collection.find.assert_not_called()
            for operation in ("insert_one", "update_one", "delete_one", "delete_many", "drop"):
                getattr(collection, operation).assert_not_called()
        database.command.assert_not_called()

    def test_reference_observations_use_same_environment_without_payload_or_user_data(self):
        database, collections = retention_database({})
        collections["ads"].find_one.return_value = {"_id": "ad"}
        collections["ad_deliveries"].find_one.return_value = {"_id": "delivery"}
        observed = reference_observations(
            database,
            "ad_admin_changes",
            {"ad_id": "ad", "asset_id": "asset"},
            is_test=True,
            now=self.now,
        )
        self.assertEqual(
            set(observed), {"AD_REFERENCE", "ASSET_REFERENCE", "DELIVERY_HISTORY_REFERENCE"}
        )
        for collection in collections.values():
            for call in collection.find_one.call_args_list:
                self.assertIs(call.args[0]["is_test"], True)
                self.assertEqual(call.args[1], {"_id": 1})

    def test_delivery_open_or_invalid_report_window_is_reviewed(self):
        database, _ = retention_database({})
        for value, reason in (
            (self.now + timedelta(seconds=1), "REPORT_WINDOW_OPEN"),
            (None, "REPORT_DEADLINE_INVALID"),
        ):
            with self.subTest(value=value):
                observed = reference_observations(
                    database,
                    "ad_deliveries",
                    {"event_expires_at": value},
                    is_test=True,
                    now=self.now,
                )
                self.assertIn(reason, observed)

    def test_invalid_input_is_rejected_before_querying(self):
        database = MagicMock()
        for limit in (0, 1001, True):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                inspect_retention(database, is_test=False, limit=limit)
        with self.assertRaises(ValueError):
            inspect_retention(database, is_test="false")
        database.__getitem__.assert_not_called()

    def test_invalid_sample_makes_report_fail_without_repair(self):
        database, _ = retention_database({"ad_events": [{"received_at": None}]})
        report = inspect_retention(database, is_test=True, now=self.now)
        self.assertEqual(report["status"], "INVALID_DATA")
        self.assertFalse(report["deletion_allowed"])

    def test_command_prints_safe_report_and_has_no_apply_mode(self):
        database, _ = retention_database({})
        with patch(
            "domains.ads.management.commands.check_ads_retention.get_ads_policy_repository",
            return_value=Mock(database=database, is_test=True),
        ) as factory:
            output = StringIO()
            call_command("check_ads_retention", limit=3, stdout=output)
            factory.assert_called_once_with()
        self.assertEqual(json.loads(output.getvalue())["status"], "REVIEW_READY")
        with patch(
            "domains.ads.management.commands.check_ads_retention.get_ads_policy_repository"
        ) as factory:
            with self.assertRaises(CommandError):
                call_command("check_ads_retention", "--apply", stdout=StringIO())
            factory.assert_not_called()

    def test_command_failure_redacts_connection_and_invalid_basis_is_nonzero(self):
        with patch(
            "domains.ads.management.commands.check_ads_retention.get_ads_policy_repository",
            side_effect=RuntimeError("mongodb://secret@private-host"),
        ):
            with self.assertRaises(CommandError) as raised:
                call_command("check_ads_retention", stdout=StringIO())
        self.assertNotIn("secret", str(raised.exception))
        database, _ = retention_database({"ad_events": [{}]})
        with patch(
            "domains.ads.management.commands.check_ads_retention.get_ads_policy_repository",
            return_value=Mock(database=database, is_test=False),
        ):
            with self.assertRaises(CommandError):
                call_command("check_ads_retention", stdout=StringIO())
