"""광고 로직의 실제 서비스와 메모리 원자 저장을 연결합니다. 운영 예산값은 아닙니다."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from itertools import count
from unittest.mock import patch

from django.test import SimpleTestCase

from domains.ads.budget_service import AdsBudgetService
from domains.ads.errors import DatabaseUnavailable, NotFound
from domains.ads.measurement import ADS_POLICY_VERSION
from domains.ads.public_service import AdsPublicService
from domains.ads.runtime_policy import get_public_policy
from domains.ads.service import AdsService, ad_status
from domains.ads.validation import AD_FIELDS
from tests.policy_fixtures import MemoryPolicyRepository
from tests.public_fixtures import fixture_public_policy
from tests.test_ads_domain import image_bytes


class AdsBudgetServiceTests(SimpleTestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 15, 12, tzinfo=UTC)
        self.base = self.now
        self.identifiers = count(1)
        self.repository = MemoryPolicyRepository(is_test=False)
        self.actor = {"identity_source": "common-auth", "account_id": "fixture-admin"}
        self.manager = AdsService(
            self.repository, clock=lambda: self.now, id_factory=self.identifier, is_test=False
        )
        asset = self.manager.upload_asset(
            image_bytes(), actor=self.actor, idempotency_key="asset", request_id="upload"
        ).body
        self.ad = self.manager.create_ad(
            {
                "title": "광고 정책 테스트 전용",
                "asset_id": asset["asset_id"],
                "link_url": "https://example.test/cafe",
                "placement": "top",
                "starts_at": self.now - timedelta(hours=1),
                "ends_at": self.now + timedelta(days=3),
                "priority": 1,
                "daily_budget_tokens": 8,
                "total_budget_tokens": 1000,
            },
            actor=self.actor,
            idempotency_key="create",
            request_id="create",
        ).body
        self.ad_id = self.ad["ad_id"]
        self.batch = AdsBudgetService(self.repository, clock=lambda: self.now)
        self.public = AdsPublicService(
            self.repository,
            policy=get_public_policy(),
            signing_key="fixture-budget-signing-key-only",
            public_base_url="https://ads.example.test",
            is_test=False,
            clock=lambda: self.now,
            id_factory=self.identifier,
        )

    def identifier(self):
        return f"policy-fixture-{next(self.identifiers)}"

    def current_ad(self):
        return self.repository.ads[self.ad_id]

    def current_state(self, day="2026-10-15"):
        return self.repository.get_budget_state(
            self.ad_id, self.current_ad()["budget_version"], day
        )

    def provide(self, **overrides):
        return self.public.provide(
            "top",
            owner_guest_id="guest-one",
            measurement_available=True,
            request_id="public-fixture",
            **overrides,
        )

    def test_later_total_exhaustion_does_not_move_first_daily_block_forward(self):
        current = self.current_ad()
        self.manager.update_ad(
            current["_id"],
            {
                **{name: current[name] for name in AD_FIELDS},
                "daily_budget_tokens": 8,
                "total_budget_tokens": 16,
                "version": current["version"],
            },
            actor=self.actor,
            idempotency_key="small-total",
            request_id="small-total",
        )
        self.batch.run_once()
        delivery = self.provide()
        self.record(delivery, self.event_data(delivery))
        self.now = self.base + timedelta(seconds=300)
        self.batch.run_once()
        first_cutoff = self.now
        self.now += timedelta(seconds=1)
        self.record(
            delivery,
            self.event_data(delivery, "CLICK", occurred_at=first_cutoff - timedelta(seconds=1)),
        )
        self.now += timedelta(seconds=1)
        self.batch.run_once()
        self.assertEqual(self.current_state()["daily_blocked_at"], first_cutoff)
        self.assertEqual(self.current_state()["total_blocked_at"], self.now)
        self.assertEqual(self.current_ad()["budget_blocked_at"], first_cutoff)

    def test_failed_ad_annotation_rolls_back_metrics_and_budget_state(self):
        self.batch.run_once()
        delivery = self.provide()
        self.record(delivery, self.event_data(delivery))
        before = self.repository.snapshot()
        with patch.object(self.repository, "replace_ad", return_value=False):
            with self.assertRaises(DatabaseUnavailable):
                self.batch.run_once()
        self.assertEqual(self.repository.snapshot(), before)

    def event_data(self, delivery, event_type="VIEWABLE_IMPRESSION", **overrides):
        return {
            "event_id": self.identifier(),
            "delivery_id": delivery["ad"]["delivery_id"],
            "event_type": event_type,
            "occurred_at": self.now,
            **overrides,
        }

    def record(self, delivery, data):
        return self.public.record_event(
            data,
            owner_guest_id="guest-one",
            measurement_available=True,
            delivery_token=delivery["ad"]["delivery_token"],
            request_id="measurement-fixture",
        )

    def change_budget(self, daily, total):
        current = self.current_ad()
        return self.manager.update_ad(
            self.ad_id,
            {
                **{name: current[name] for name in AD_FIELDS},
                "version": current["version"],
                "daily_budget_tokens": daily,
                "total_budget_tokens": total,
            },
            actor=self.actor,
            idempotency_key=self.identifier(),
            request_id="budget-change",
        ).body

    def exhaust_daily_and_refresh(self):
        self.batch.run_once()
        delivery = self.provide()
        self.record(delivery, self.event_data(delivery))
        self.now = self.base + timedelta(seconds=300)
        self.batch.run_once()
        return delivery

    def test_initial_refresh_distinguishes_real_zero_and_makes_ad_eligible(self):
        self.assertIsNone(self.provide()["ad"])
        self.assertEqual(self.repository.metrics_summary(self.now)["aggregation_status"], "PENDING")
        counts = self.batch.run_once()
        self.assertEqual(counts, {"ads_checked": 1, "blocked": 0, "metrics_rows": 1})
        state = self.current_state()
        self.assertEqual((state["daily_tokens"], state["total_tokens"]), (0, 0))
        self.assertIsNone(state["daily_blocked_at"])
        summary = self.repository.metrics_summary(self.now)
        self.assertEqual(summary["aggregation_status"], "READY")
        self.assertEqual(summary["today_estimated_tokens"], 0)
        self.assertEqual(summary["today_valid_impressions"], 0)
        self.assertIsNotNone(self.provide()["ad"])

    def test_reports_before_next_verification_can_exceed_budget_without_hard_cap(self):
        self.batch.run_once()
        delivery = self.provide()
        self.record(delivery, self.event_data(delivery))
        self.now += timedelta(seconds=1)
        clicked = self.record(delivery, self.event_data(delivery, "CLICK"))
        self.assertTrue(clicked["counted"])
        self.assertEqual(sum(row["estimated_tokens"] for row in self.repository.usage.values()), 23)
        self.assertIsNone(self.current_state()["daily_blocked_at"])
        self.assertIsNotNone(self.provide()["ad"])

    def test_cutoff_hides_existing_delivery_new_delivery_and_image_without_manual_pause(self):
        original = deepcopy(self.current_ad())
        delivery = self.exhaust_daily_and_refresh()
        self.assertEqual(self.current_state()["daily_blocked_at"], self.now)
        self.assertIsNone(self.provide()["ad"])
        self.assertIsNone(
            self.provide(
                delivery_id=delivery["ad"]["delivery_id"],
                delivery_token=delivery["ad"]["delivery_token"],
            )["ad"]
        )
        with self.assertRaises(NotFound):
            self.public.read_image(
                delivery["ad"]["delivery_id"], delivery_token=delivery["ad"]["delivery_token"]
            )
        current = self.current_ad()
        self.assertFalse(current["paused"])
        for field in ("starts_at", "ends_at", "stopped_at", "version", "updated_at"):
            self.assertEqual(current[field], original[field], field)
        self.assertEqual(ad_status(current, self.now), "ENDED")

    def test_pre_cutoff_event_arriving_after_cutoff_is_counted_even_if_it_exceeds_budget(self):
        delivery = self.exhaust_daily_and_refresh()
        occurred = self.now - timedelta(seconds=1)
        self.now += timedelta(seconds=1)
        result = self.record(delivery, self.event_data(delivery, "CLICK", occurred_at=occurred))
        self.assertEqual(result["result"], "COUNTED")
        self.assertEqual(sum(row["estimated_tokens"] for row in self.repository.usage.values()), 23)
        self.assertIsNotNone(self.current_state()["daily_blocked_at"])

    def test_exact_cutoff_and_later_occurrence_are_invalid_without_consuming_click(self):
        delivery = self.exhaust_daily_and_refresh()
        cutoff = self.now
        self.now += timedelta(seconds=2)
        for occurred in (cutoff, cutoff + timedelta(milliseconds=1)):
            with self.subTest(occurred=occurred):
                result = self.record(
                    delivery, self.event_data(delivery, "CLICK", occurred_at=occurred)
                )
                self.assertEqual(result["result"], "DELIVERY_INVALID")
        stored = self.repository.get_delivery(delivery["ad"]["delivery_id"])
        self.assertNotIn("CLICK", stored["claims"])
        self.assertEqual(len(self.repository.usage), 1)

    def test_pre_cutoff_report_at_exact_300_second_receive_delay_is_valid(self):
        delivery = self.exhaust_daily_and_refresh()
        self.now = self.base + timedelta(seconds=301)
        result = self.record(
            delivery,
            self.event_data(delivery, "CLICK", occurred_at=self.base + timedelta(seconds=1)),
        )
        self.assertEqual(result["result"], "COUNTED")

    def test_first_response_replay_is_stable_after_cutoff_and_delivery_expiration(self):
        self.batch.run_once()
        delivery = self.provide()
        data = self.event_data(delivery)
        original = self.record(delivery, data)
        self.now += timedelta(seconds=300)
        self.batch.run_once()
        self.now += timedelta(hours=2)
        before = self.repository.snapshot()
        self.assertEqual(self.record(delivery, data), original)
        self.assertEqual(self.repository.snapshot(), before)

    def test_refresh_replaces_metrics_and_keeps_first_cutoff_log_and_payload(self):
        delivery = self.exhaust_daily_and_refresh()
        first_state = self.current_state()
        first_cutoff = first_state["daily_blocked_at"]
        first_relay = deepcopy(first_state["log_record"])
        self.now += timedelta(seconds=1)
        self.record(
            delivery,
            self.event_data(delivery, "CLICK", occurred_at=first_cutoff - timedelta(seconds=1)),
        )
        self.now += timedelta(seconds=1)
        self.assertEqual(self.batch.run_once()["blocked"], 0)
        second = self.current_state()
        self.assertEqual(second["daily_blocked_at"], first_cutoff)
        self.assertEqual(second["log_record"], first_relay)
        self.assertEqual(second["daily_tokens"], 23)
        self.assertEqual(self.repository.metrics_summary(self.now)["today_estimated_tokens"], 23)
        self.batch.run_once()
        self.assertEqual(len(self.repository.metrics), 1)
        self.assertEqual(self.repository.metrics_summary(self.now)["today_estimated_tokens"], 23)

    def test_daily_rollover_keeps_old_cutoff_and_releases_only_the_daily_boundary(self):
        self.exhaust_daily_and_refresh()
        old_state = self.current_state()
        self.now = datetime(2026, 10, 15, 15, 0, 1, tzinfo=UTC)
        self.batch.run_once()
        new_state = self.current_state("2026-10-16")
        self.assertIsNone(new_state["daily_blocked_at"])
        self.assertEqual(new_state["daily_tokens"], 0)
        self.assertEqual(new_state["total_tokens"], 8)
        self.assertEqual(self.current_state(), old_state)
        self.assertIsNotNone(self.provide()["ad"])

    def test_total_cutoff_survives_daily_rollover(self):
        self.change_budget(daily=100, total=8)
        self.exhaust_daily_and_refresh()
        cutoff = self.current_state()["total_blocked_at"]
        self.now = datetime(2026, 10, 15, 15, 0, 1, tzinfo=UTC)
        self.batch.run_once()
        new_state = self.current_state("2026-10-16")
        self.assertEqual(new_state["total_blocked_at"], cutoff)
        self.assertEqual(
            self.repository.total_budget_cutoff(self.ad_id, self.current_ad()["budget_version"]),
            cutoff,
        )
        self.assertIsNone(self.provide()["ad"])

    def test_budget_increase_needs_new_version_verification_and_keeps_old_history(self):
        self.exhaust_daily_and_refresh()
        old_version = self.current_ad()["budget_version"]
        old_state = self.current_state()
        self.now += timedelta(seconds=1)
        self.change_budget(daily=100, total=1000)
        self.assertNotEqual(self.current_ad()["budget_version"], old_version)
        self.assertIsNone(self.provide()["ad"])
        self.batch.run_once()
        self.assertIsNotNone(self.provide()["ad"])
        self.assertEqual(
            self.repository.get_budget_state(self.ad_id, old_version, "2026-10-15"), old_state
        )

    def test_manual_stop_is_kept_across_budget_refresh_and_new_day(self):
        self.batch.run_once()
        self.now += timedelta(seconds=1)
        stopped = self.manager.stop_ad(
            self.ad_id,
            {"version": self.current_ad()["version"]},
            actor=self.actor,
            idempotency_key="stop",
            request_id="manual-stop",
        )
        expected = deepcopy(self.current_ad())
        self.now = datetime(2026, 10, 15, 15, 0, 1, tzinfo=UTC)
        self.batch.run_once()
        current = self.current_ad()
        self.assertTrue(current["paused"])
        self.assertEqual(current["stopped_at"], expected["stopped_at"])
        self.assertEqual(current["version"], stopped.body["version"])
        self.assertEqual(ad_status(current, self.now), "STOPPED")
        self.assertIsNone(self.provide()["ad"])

    def test_unconfigured_budget_gets_real_zero_metrics_without_a_budget_state(self):
        current = self.current_ad()
        current["daily_budget_tokens"] = None
        current["total_budget_tokens"] = None
        current["budget_version"] = None
        counts = self.batch.run_once()
        self.assertEqual(counts, {"ads_checked": 1, "blocked": 0, "metrics_rows": 1})
        self.assertFalse(self.repository.budget_states)
        self.assertEqual(self.repository.metrics_summary(self.now)["today_estimated_tokens"], 0)
        self.assertIsNone(self.provide()["ad"])

    def test_failed_budget_state_save_rolls_back_metrics_annotation_and_state(self):
        self.batch.run_once()
        delivery = self.provide()
        self.record(delivery, self.event_data(delivery))
        self.now += timedelta(seconds=300)
        before = self.repository.snapshot()
        self.repository.fail_budget_state = True
        with self.assertRaises(DatabaseUnavailable):
            self.batch.run_once()
        self.assertEqual(self.repository.snapshot(), before)
        self.repository.fail_budget_state = False
        self.batch.run_once()
        self.assertEqual(self.current_state()["daily_blocked_at"], self.now)

    def test_legacy_delivery_is_not_retroactively_subject_to_budget_cutoff(self):
        self.public.policy = fixture_public_policy()
        delivery = self.provide()
        stored = self.repository.get_delivery(delivery["ad"]["delivery_id"])
        self.assertNotIn("budget_policy_version", stored)
        self.batch.run_once()
        self.record(delivery, self.event_data(delivery))
        self.now += timedelta(seconds=300)
        self.batch.run_once()
        self.public.policy = get_public_policy()
        self.now += timedelta(seconds=1)
        result = self.record(delivery, self.event_data(delivery, "CLICK"))
        self.assertEqual(result["result"], "COUNTED")
        self.assertEqual(result["ads_policy_version"], ADS_POLICY_VERSION)
