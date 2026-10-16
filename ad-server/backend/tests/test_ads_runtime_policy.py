"""공개 운영 정책과 명시 실행형 batch/relay 연결. 실제 반복 기동·DB 접속은 없습니다."""

from datetime import UTC, datetime, timedelta
from io import StringIO
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from domains.ads.errors import DatabaseUnavailable, DomainError
from domains.ads.runtime_policy import budget_eligible, get_public_policy


class RuntimeBudgetPolicyTests(SimpleTestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 15, 14, 59, tzinfo=UTC)
        self.ad = {
            "_id": "ad-one",
            "daily_budget_tokens": 100,
            "total_budget_tokens": 1000,
            "budget_version": "budget-v1",
        }
        self.state = {
            "metric_date_kst": "2026-10-15",
            "verified_at": self.now,
            "daily_blocked_at": None,
            "total_blocked_at": None,
        }
        self.repository = Mock()
        self.repository.get_budget_state.return_value = self.state
        self.repository.latest_budget_state.return_value = None
        self.repository.total_budget_cutoff.return_value = None

    def test_fresh_verified_budget_is_eligible_without_recomputing_usage(self):
        self.assertTrue(budget_eligible(self.repository, self.ad, self.now))
        self.repository.get_budget_state.assert_called_once_with(
            "ad-one", "budget-v1", "2026-10-15"
        )
        self.repository.total_budget_cutoff.assert_called_once_with("ad-one", "budget-v1")
        self.repository.usage_rows.assert_not_called()

    def test_unconfigured_nonpositive_or_boolean_budget_is_not_served(self):
        invalid = (None, 0, -1, True, "100", 1.0)
        for field in ("daily_budget_tokens", "total_budget_tokens"):
            for value in invalid:
                with self.subTest(field=field, value=value):
                    self.assertFalse(
                        budget_eligible(self.repository, {**self.ad, field: value}, self.now)
                    )
        self.repository.get_budget_state.assert_not_called()

    def test_budget_version_is_an_opaque_nonempty_string(self):
        for version in (None, "", " ", True, 1):
            with self.subTest(version=version):
                self.assertFalse(
                    budget_eligible(
                        self.repository, {**self.ad, "budget_version": version}, self.now
                    )
                )
        self.repository.get_budget_state.assert_not_called()

    def test_missing_configuration_or_verification_state_is_not_served(self):
        self.assertFalse(budget_eligible(self.repository, {"_id": "ad-one"}, self.now))
        self.repository.get_budget_state.return_value = None
        self.assertFalse(budget_eligible(self.repository, self.ad, self.now))
        self.repository.total_budget_cutoff.assert_not_called()

    def test_exact_300_second_age_is_usable_and_next_millisecond_is_unavailable(self):
        self.state["verified_at"] = self.now - timedelta(seconds=300)
        self.assertTrue(budget_eligible(self.repository, self.ad, self.now))
        self.state["verified_at"] -= timedelta(milliseconds=1)
        with self.assertRaises(DomainError) as raised:
            budget_eligible(self.repository, self.ad, self.now)
        self.assertEqual(
            (raised.exception.code, raised.exception.status), ("ADS_POLICY_UNAVAILABLE", 503)
        )

    def test_future_or_invalid_verification_timestamp_is_a_service_error(self):
        for verified in (self.now + timedelta(milliseconds=1), None, "invalid", True):
            self.state["verified_at"] = verified
            with self.subTest(verified=verified), self.assertRaises(DomainError) as raised:
                budget_eligible(self.repository, self.ad, self.now)
            self.assertEqual(raised.exception.status, 503)

    def test_current_daily_cutoff_blocks_display_and_total_lookup_is_unnecessary(self):
        self.state["daily_blocked_at"] = self.now
        self.assertFalse(budget_eligible(self.repository, self.ad, self.now))
        self.repository.total_budget_cutoff.assert_not_called()

    def test_previous_daily_cutoff_does_not_carry_into_new_kst_day(self):
        next_day = self.now + timedelta(minutes=2)
        self.repository.get_budget_state.return_value = {
            **self.state,
            "metric_date_kst": "2026-10-16",
            "verified_at": next_day,
        }
        self.assertTrue(budget_eligible(self.repository, self.ad, next_day))
        self.repository.get_budget_state.assert_called_once_with(
            "ad-one", "budget-v1", "2026-10-16"
        )

    def test_total_cutoff_survives_daily_rollover(self):
        next_day = self.now + timedelta(minutes=2)
        self.repository.get_budget_state.return_value = {**self.state, "verified_at": next_day}
        self.repository.total_budget_cutoff.return_value = self.now
        self.assertFalse(budget_eligible(self.repository, self.ad, next_day))

    def test_repository_failure_does_not_become_an_eligible_or_unlimited_budget(self):
        self.repository.get_budget_state.side_effect = DatabaseUnavailable()
        with self.assertRaises(DatabaseUnavailable):
            budget_eligible(self.repository, self.ad, self.now)

    def test_runtime_policy_uses_adopted_delivery_and_material_rules(self):
        policy = get_public_policy()
        self.assertEqual(policy.version, "phase3-ads-20261015.1")
        self.assertEqual(policy.delivery_ttl_seconds, 1800)
        self.assertTrue(policy.split_deadlines)
        self.assertFalse(policy.cap_at_midnight)
        self.assertTrue(policy.check_budget_history)
        original = {"creative_version": "first", "placement": "top"}
        changed = {**original, "creative_version": "second"}
        self.assertTrue(policy.open_delivery_eligible(original, original, self.now))
        self.assertFalse(policy.open_delivery_eligible(original, changed, self.now))
        self.assertTrue(policy.occurrence_eligible(original, original, self.now))


class RuntimePolicyCommandsTests(SimpleTestCase):
    def test_refresh_default_runs_one_batch_without_sleep_or_migrations(self):
        repository = Mock()
        service = Mock()
        service.run_once.return_value = {"ads_checked": 2, "blocked": 1, "metrics_rows": 3}
        with (
            patch(
                "domains.ads.management.commands.refresh_ads_policy.get_ads_policy_repository",
                return_value=repository,
            ),
            patch(
                "domains.ads.management.commands.refresh_ads_policy.AdsBudgetService",
                return_value=service,
            ) as factory,
            patch("domains.ads.management.commands.refresh_ads_policy.time.sleep") as sleep,
        ):
            output = StringIO()
            call_command("refresh_ads_policy", stdout=output)
        factory.assert_called_once_with(repository)
        service.run_once.assert_called_once_with()
        sleep.assert_not_called()
        self.assertIn("blocked=1", output.getvalue())

    def test_watch_uses_300_second_start_interval_and_handles_ctrl_c(self):
        service = Mock()
        service.run_once.return_value = {"ads_checked": 0, "blocked": 0, "metrics_rows": 0}
        with (
            patch("domains.ads.management.commands.refresh_ads_policy.get_ads_policy_repository"),
            patch(
                "domains.ads.management.commands.refresh_ads_policy.AdsBudgetService",
                return_value=service,
            ),
            patch(
                "domains.ads.management.commands.refresh_ads_policy.time.monotonic",
                side_effect=[100, 102, 405],
            ),
            patch(
                "domains.ads.management.commands.refresh_ads_policy.time.sleep",
                side_effect=[None, KeyboardInterrupt],
            ) as sleep,
        ):
            output = StringIO()
            call_command("refresh_ads_policy", watch=True, stdout=output)
        self.assertEqual(service.run_once.call_count, 2)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [298, 295])
        self.assertIn("Ctrl+C", output.getvalue())
        self.assertIn("종료", output.getvalue())

    def test_refresh_database_failure_is_a_command_error(self):
        with patch(
            "domains.ads.management.commands.refresh_ads_policy.get_ads_policy_repository",
            side_effect=DatabaseUnavailable(),
        ):
            with self.assertRaises(CommandError):
                call_command("refresh_ads_policy", stdout=StringIO())
