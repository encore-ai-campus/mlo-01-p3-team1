"""공개 서비스 결과·소유·원자성을 검증하며 운영 정책이나 DB 실행을 뜻하지 않습니다."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from itertools import count
from unittest.mock import patch

from django.test import SimpleTestCase

from domains.ads.errors import (
    DatabaseUnavailable,
    IdempotencyConflict,
    NotFound,
    ValidationError,
)
from domains.ads.public_service import AdsPublicService
from domains.ads.service import AdsService, canonical_hash
from domains.ads.validation import utc_datetime
from tests.public_fixtures import MemoryPublicRepository, fixture_public_policy
from tests.test_ads_domain import image_bytes


class AdsPublicServiceTests(SimpleTestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 15, 14, 59, tzinfo=UTC)
        self.identifiers = count(1)
        self.repository = MemoryPublicRepository(is_test=False)
        self.manager = AdsService(
            self.repository, clock=lambda: self.now, id_factory=self.identifier, is_test=False
        )
        self.actor = {"identity_source": "common-auth", "account_id": "external-admin"}
        asset = self.manager.upload_asset(
            image_bytes(), actor=self.actor, idempotency_key="asset", request_id="admin-asset"
        )
        self.asset_id = asset.body["asset_id"]
        self.policy = fixture_public_policy()
        self.service = self.make_service()
        self.ad = self.create_ad()

    def identifier(self):
        return f"fixture-{next(self.identifiers):05d}"

    def make_service(self, **overrides):
        return AdsPublicService(
            self.repository,
            policy=overrides.get("policy", self.policy),
            signing_key="fixed-fixture-signing-key-only",
            public_base_url="https://ads.example.test",
            is_test=overrides.get("is_test", False),
            clock=lambda: self.now,
            id_factory=self.identifier,
        )

    def create_ad(self, **overrides):
        data = {
            "title": "카페 광고",
            "asset_id": self.asset_id,
            "link_url": "https://example.test/cafe",
            "placement": "top",
            "starts_at": self.now,
            "ends_at": self.now + timedelta(hours=1),
            "priority": 1,
            **overrides,
        }
        return self.manager.create_ad(
            data, actor=self.actor, idempotency_key=self.identifier(), request_id="admin-create"
        ).body

    def provide(self, placement="top", **overrides):
        options = {
            "owner_guest_id": "guest-one",
            "measurement_available": True,
            "request_id": "public-request",
            **overrides,
        }
        return self.service.provide(placement, **options)

    def event(self, response, event_type="VIEWABLE_IMPRESSION", **overrides):
        data = {
            "event_id": self.identifier(),
            "delivery_id": response["ad"]["delivery_id"],
            "event_type": event_type,
            "occurred_at": self.now,
            **overrides,
        }
        result = self.service.record_event(
            data,
            owner_guest_id="guest-one",
            measurement_available=True,
            delivery_token=response["ad"]["delivery_token"],
            request_id="event-request",
        )
        return data, result

    def stop(self):
        current = self.repository.ads[self.ad["ad_id"]]
        return self.manager.stop_ad(
            current["_id"],
            {"version": current["version"]},
            actor=self.actor,
            idempotency_key=self.identifier(),
            request_id="admin-stop",
        )

    def usage_entry(self, event_id):
        return next(item for item in self.repository.usage.values() if item["event_id"] == event_id)

    def test_highest_priority_ad_is_served_with_server_image_and_delivery(self):
        leader = self.create_ad(priority=10)
        response = self.provide()
        self.assertEqual(response["ad"]["ad_id"], leader["ad_id"])
        self.assertEqual(response["ad"]["creative_version"], leader["creative_version"])
        self.assertTrue(response["ad"]["image_url"].startswith("https://ads.example.test/"))
        self.assertNotIn("asset_id", response["ad"])
        self.assertTrue(response["measurement_available"])
        self.assertEqual(utc_datetime(response["valid_until"]), self.now + timedelta(seconds=3))
        stored = self.repository.deliveries[response["ad"]["delivery_id"]]
        self.assertEqual(stored["owner_guest_id"], "guest-one")
        self.assertEqual(stored["event_expires_at"], self.now + timedelta(seconds=900))
        self.assertEqual(stored["policy_version"], "FIXTURE/public/v1")

    def test_tie_rotation_is_separate_for_top_and_bottom(self):
        second_top = self.create_ad()
        first_bottom = self.create_ad(placement="bottom")
        second_bottom = self.create_ad(placement="bottom")
        results = [self.provide(), self.provide("bottom"), self.provide(), self.provide("bottom")]
        self.assertEqual(
            [item["ad"]["ad_id"] for item in results],
            [self.ad["ad_id"], first_bottom["ad_id"], second_top["ad_id"], second_bottom["ad_id"]],
        )
        self.assertEqual(self.provide()["ad"]["ad_id"], self.ad["ad_id"])

    def test_unavailable_budget_returns_empty_without_advancing_rotation(self):
        self.service = self.make_service(
            policy=fixture_public_policy(budget_eligible=lambda repository, ad, now: False)
        )
        self.assertIsNone(self.provide()["ad"])
        self.assertFalse(self.repository.rotations)
        self.assertFalse(self.repository.deliveries)

    def test_request_key_replay_keeps_original_response_and_cursor(self):
        original = self.provide(idempotency_key="same-display")
        before = self.repository.snapshot()
        self.now += timedelta(seconds=10)
        replay = self.provide(idempotency_key="same-display")
        self.assertEqual(replay, original)
        self.assertEqual(self.repository.snapshot(), before)

    def test_parallel_request_key_creates_one_delivery(self):
        with ThreadPoolExecutor(max_workers=4) as executor:
            responses = list(
                executor.map(
                    lambda _: self.provide(idempotency_key="same-concurrent-display"), range(4)
                )
            )
        self.assertTrue(all(response == responses[0] for response in responses))
        self.assertEqual(len(self.repository.deliveries), 1)
        self.assertEqual(self.repository.rotations["top"]["revision"], 1)

    def test_reconfirm_keeps_same_delivery_and_does_not_move_cursor(self):
        response = self.provide()
        self.create_ad(priority=99)
        cursor = deepcopy(self.repository.rotations)
        self.now += timedelta(seconds=2)
        confirmed = self.provide(
            delivery_id=response["ad"]["delivery_id"],
            delivery_token=response["ad"]["delivery_token"],
        )
        self.assertEqual(confirmed["ad"], response["ad"])
        self.assertEqual(self.repository.rotations, cursor)
        self.assertEqual(utc_datetime(confirmed["valid_until"]), self.now + timedelta(seconds=3))
        self.assertEqual(len(self.repository.deliveries), 1)

    def test_reconfirm_does_not_extend_event_expiration(self):
        response = self.provide()
        delivery = self.repository.deliveries[response["ad"]["delivery_id"]]
        expiration = delivery["event_expires_at"]
        self.now = expiration - timedelta(milliseconds=500)
        confirmed = self.provide(
            delivery_id=response["ad"]["delivery_id"],
            delivery_token=response["ad"]["delivery_token"],
        )
        self.assertEqual(utc_datetime(confirmed["valid_until"]), expiration)
        self.now = expiration
        self.assertIsNone(
            self.provide(
                delivery_id=response["ad"]["delivery_id"],
                delivery_token=response["ad"]["delivery_token"],
            )["ad"]
        )
        self.assertEqual(delivery["event_expires_at"], expiration)

    def test_stopped_ad_is_removed_on_reconfirm_without_replacement(self):
        response = self.provide()
        self.create_ad()
        self.now += timedelta(seconds=1)
        self.stop()
        confirmed = self.provide(
            delivery_id=response["ad"]["delivery_id"],
            delivery_token=response["ad"]["delivery_token"],
        )
        self.assertIsNone(confirmed["ad"])
        self.assertEqual(len(self.repository.deliveries), 1)

    def test_wrong_owner_or_tampered_delivery_proof_is_hidden(self):
        response = self.provide()
        for overrides in (
            {"owner_guest_id": "guest-two"},
            {"delivery_token": "tampered"},
            {"delivery_token": None},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(NotFound):
                self.provide(
                    **{
                        "delivery_id": response["ad"]["delivery_id"],
                        "delivery_token": response["ad"]["delivery_token"],
                        **overrides,
                    }
                )

    def test_cookie_unavailable_can_display_without_inventing_a_guest(self):
        response = self.provide(owner_guest_id=None, measurement_available=False)
        self.assertIsNotNone(response["ad"])
        self.assertFalse(response["measurement_available"])
        self.assertIsNone(
            self.repository.deliveries[response["ad"]["delivery_id"]]["owner_guest_id"]
        )
        result = self.service.record_event(
            {
                "event_id": "no-cookie",
                "delivery_id": response["ad"]["delivery_id"],
                "event_type": "CLICK",
                "occurred_at": self.now,
            },
            owner_guest_id=None,
            measurement_available=False,
            delivery_token=response["ad"]["delivery_token"],
            request_id="no-cookie-request",
        )
        self.assertEqual(result["result"], "MEASUREMENT_UNAVAILABLE")
        self.assertFalse(result["counted"])
        self.assertFalse(self.repository.windows)
        self.assertFalse(self.repository.usage)

    def test_unknown_body_fields_cannot_supply_accounting_decisions(self):
        response = self.provide()
        with self.assertRaises(ValidationError):
            self.event(response, estimated_tokens=100, counted=True, guest_id="forged")
        self.assertFalse(self.repository.events)

    def test_counted_event_saves_claim_window_usage_and_pending_log_together(self):
        response = self.provide()
        data, result = self.event(response)
        self.assertEqual(result["result"], "COUNTED")
        self.assertEqual(
            set(result),
            {
                "event_id",
                "delivery_id",
                "event_type",
                "result",
                "counted",
                "occurred_at",
                "received_at",
                "processed_at",
                "ads_policy_version",
            },
        )
        delivery = self.repository.deliveries[data["delivery_id"]]
        self.assertEqual(delivery["claims"][data["event_type"]]["event_id"], data["event_id"])
        self.assertEqual(len(self.repository.windows), 1)
        self.assertEqual(len(self.repository.usage), 1)
        self.assertEqual(self.usage_entry(data["event_id"])["estimated_tokens"], 8)
        stored = self.repository.events[data["event_id"]]
        self.assertEqual(stored["log_relay"]["status"], "PENDING")
        self.assertEqual(
            stored["log_relay"]["payload_hash"], canonical_hash(stored["log_relay"]["payload"])
        )
        self.assertNotIn(response["ad"]["delivery_token"], str(stored["log_relay"]))
        self.assertNotIn("image_bytes", str(stored["log_relay"]))

    def test_bottom_impression_and_click_record_distinct_expected_tokens(self):
        self.create_ad(placement="bottom")
        response = self.provide("bottom")
        impression, _ = self.event(response)
        click, result = self.event(response, "CLICK")
        self.assertEqual(result["result"], "COUNTED")
        self.assertEqual(self.usage_entry(impression["event_id"])["estimated_tokens"], 5)
        self.assertEqual(self.usage_entry(click["event_id"])["estimated_tokens"], 15)

    def test_replay_retains_first_decision_after_stop_and_expiration(self):
        response = self.provide()
        data, first = self.event(response)
        self.now += timedelta(seconds=1)
        self.stop()
        self.now += timedelta(hours=2)
        before = self.repository.snapshot()
        replay = self.service.record_event(
            data,
            owner_guest_id="guest-one",
            measurement_available=True,
            delivery_token=response["ad"]["delivery_token"],
            request_id="retry-request",
        )
        self.assertEqual(replay, first)
        self.assertEqual(self.repository.snapshot(), before)

    def test_same_event_id_changed_input_conflicts_without_new_mutations(self):
        response = self.provide()
        data, _ = self.event(response)
        before = self.repository.snapshot()
        with self.assertRaises(IdempotencyConflict):
            self.event(response, "CLICK", event_id=data["event_id"])
        self.assertEqual(self.repository.snapshot(), before)

    def test_event_owner_and_proof_are_checked_even_when_event_id_exists(self):
        response = self.provide()
        data, _ = self.event(response)
        before = self.repository.snapshot()
        for overrides in (
            {"owner_guest_id": "guest-two"},
            {"delivery_token": "tampered"},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(NotFound):
                self.service.record_event(
                    data,
                    **{
                        "owner_guest_id": "guest-one",
                        "measurement_available": True,
                        "delivery_token": response["ad"]["delivery_token"],
                        "request_id": "foreign-replay",
                        **overrides,
                    },
                )
        self.assertEqual(self.repository.snapshot(), before)

    def test_new_event_id_for_consumed_delivery_type_is_duplicate(self):
        response = self.provide()
        self.event(response)
        _, repeated = self.event(response)
        self.assertEqual(repeated["result"], "DELIVERY_DUPLICATE")
        self.assertFalse(repeated["counted"])
        self.assertEqual(len(self.repository.events), 2)
        self.assertEqual(len(self.repository.usage), 1)

    def test_parallel_first_events_count_delivery_type_once(self):
        response = self.provide()
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(lambda _: self.event(response)[1], range(2)))
        self.assertCountEqual(
            [item["result"] for item in outcomes], ["COUNTED", "DELIVERY_DUPLICATE"]
        )
        self.assertEqual(len(self.repository.usage), 1)

    def test_suppression_consumes_new_delivery_but_keeps_repeat_window(self):
        self.event(self.provide())
        accepted_window = deepcopy(self.repository.windows)
        self.now += timedelta(seconds=10)
        response = self.provide()
        _, suppressed = self.event(response)
        self.assertEqual(suppressed["result"], "REPEAT_SUPPRESSED")
        self.assertEqual(self.repository.windows, accepted_window)
        self.assertEqual(len(self.repository.usage), 1)
        _, again = self.event(response)
        self.assertEqual(again["result"], "DELIVERY_DUPLICATE")

    def test_exact_impression_repeat_boundary_is_counted(self):
        self.event(self.provide())
        self.now += timedelta(seconds=60)
        _, result = self.event(self.provide())
        self.assertEqual(result["result"], "COUNTED")
        self.assertEqual(len(self.repository.usage), 2)

    def test_exact_click_repeat_boundary_is_counted(self):
        self.event(self.provide(), "CLICK")
        self.now += timedelta(seconds=299)
        _, suppressed = self.event(self.provide(), "CLICK")
        self.assertEqual(suppressed["result"], "REPEAT_SUPPRESSED")
        self.now += timedelta(seconds=1)
        _, result = self.event(self.provide(), "CLICK")
        self.assertEqual(result["result"], "COUNTED")

    def test_delayed_event_before_stop_uses_historical_ad(self):
        response = self.provide()
        occurred_at = self.now + timedelta(seconds=1)
        self.now += timedelta(seconds=2)
        self.stop()
        self.now += timedelta(seconds=3)
        _, result = self.event(response, occurred_at=occurred_at)
        self.assertEqual(result["result"], "COUNTED")

    def test_event_at_stop_is_invalid_without_consuming_delivery(self):
        response = self.provide()
        self.now += timedelta(seconds=2)
        self.stop()
        _, result = self.event(response)
        self.assertEqual(result["result"], "DELIVERY_INVALID")
        self.assertFalse(self.repository.deliveries[response["ad"]["delivery_id"]]["claims"])
        self.assertFalse(self.repository.usage)

    def test_more_than_300_seconds_delay_is_recorded_without_counting(self):
        response = self.provide()
        occurred_at = self.now
        self.now += timedelta(seconds=301)
        _, result = self.event(response, occurred_at=occurred_at)
        self.assertEqual(result["result"], "LATE_EVENT")
        self.assertFalse(self.repository.windows)
        self.assertFalse(self.repository.usage)

    def test_metric_day_uses_occurrence_kst_instead_of_receive_day(self):
        response = self.provide()
        occurred_at = self.now
        self.now += timedelta(minutes=2)
        data, result = self.event(response, occurred_at=occurred_at)
        self.assertEqual(result["result"], "COUNTED")
        self.assertEqual(self.usage_entry(data["event_id"])["metric_date_kst"], "2026-10-15")

    def test_event_or_usage_failure_rolls_back_all_eight_states(self):
        response = self.provide()
        for failure in ("fail_event", "fail_usage"):
            before = self.repository.snapshot()
            setattr(self.repository, failure, True)
            with self.subTest(failure=failure), self.assertRaises(DatabaseUnavailable):
                self.event(response)
            setattr(self.repository, failure, False)
            self.assertEqual(self.repository.snapshot(), before)
        _, result = self.event(response)
        self.assertEqual(result["result"], "COUNTED")

    def test_failed_delivery_insert_does_not_advance_rotation(self):
        self.repository.fail_delivery = True
        before = self.repository.snapshot()
        with self.assertRaises(DatabaseUnavailable):
            self.provide()
        self.assertEqual(self.repository.snapshot(), before)

    def test_image_requires_delivery_proof_and_active_current_ad(self):
        response = self.provide()
        delivery_id = response["ad"]["delivery_id"]
        token = response["ad"]["delivery_token"]
        data, mime_type = self.service.read_image(delivery_id, delivery_token=token)
        self.assertEqual(data, image_bytes())
        self.assertEqual(mime_type, "image/png")
        with self.assertRaises(NotFound):
            self.service.read_image(delivery_id, delivery_token="tampered")
        self.now += timedelta(seconds=1)
        self.stop()
        with self.assertRaises(NotFound):
            self.service.read_image(delivery_id, delivery_token=token)

    def test_response_mutation_cannot_change_stored_replay(self):
        response = self.provide(idempotency_key="immutable-request")
        original = deepcopy(response)
        response["ad"]["title"] = "외부 응답 변이"
        self.assertEqual(self.provide(idempotency_key="immutable-request"), original)

    def test_stop_waiting_for_lock_does_not_backdate_historical_validity(self):
        issued_at = self.now
        response = self.provide()
        original_replace = self.repository.replace_ad

        def delayed_lock(*args, **kwargs):
            result = original_replace(*args, **kwargs)
            self.now = issued_at + timedelta(seconds=10)
            return result

        self.now = issued_at + timedelta(seconds=2)
        with patch.object(self.repository, "replace_ad", side_effect=delayed_lock):
            stopped = self.stop()
        self.assertEqual(
            utc_datetime(stopped.body["stopped_at"]), issued_at + timedelta(seconds=10)
        )
        self.now = issued_at + timedelta(seconds=12)
        _, result = self.event(response, occurred_at=issued_at + timedelta(seconds=5))
        self.assertEqual(result["result"], "COUNTED")

    def test_reconfirmation_caps_display_at_shortened_current_end(self):
        response = self.provide()
        self.now += timedelta(seconds=1)
        current = self.repository.ads[self.ad["ad_id"]]
        new_end = self.now + timedelta(milliseconds=500)
        body = {
            name: current[name]
            for name in (
                "title",
                "asset_id",
                "link_url",
                "placement",
                "starts_at",
                "ends_at",
                "priority",
            )
        }
        self.manager.update_ad(
            current["_id"],
            {**body, "ends_at": new_end, "version": current["version"]},
            actor=self.actor,
            idempotency_key="shorten-period",
            request_id="shorten-request",
        )
        checked = self.provide(
            delivery_id=response["ad"]["delivery_id"],
            delivery_token=response["ad"]["delivery_token"],
        )
        self.assertEqual(utc_datetime(checked["valid_until"]), new_end)

    def test_split_delivery_expiry_allows_delayed_report_after_midnight(self):
        self.service = self.make_service(
            policy=replace(
                self.policy, delivery_ttl_seconds=1800, split_deadlines=True, cap_at_midnight=True
            )
        )
        response = self.provide()
        stored = self.repository.deliveries[response["ad"]["delivery_id"]]
        midnight = datetime(2026, 10, 15, 15, tzinfo=UTC)
        self.assertEqual(stored["display_expires_at"], midnight)
        self.assertEqual(stored["event_expires_at"], midnight + timedelta(seconds=300))
        self.now = midnight + timedelta(seconds=2)
        _, result = self.event(response, occurred_at=midnight - timedelta(seconds=1))
        self.assertEqual(result["result"], "COUNTED")
        self.assertEqual(self.usage_entry(result["event_id"])["metric_date_kst"], "2026-10-15")
        checked = self.provide(
            delivery_id=response["ad"]["delivery_id"],
            delivery_token=response["ad"]["delivery_token"],
        )
        self.assertIsNone(checked["ad"])

    def test_split_delivery_rejects_new_occurrence_at_display_expiry(self):
        self.service = self.make_service(
            policy=replace(
                self.policy, delivery_ttl_seconds=1800, split_deadlines=True, cap_at_midnight=True
            )
        )
        response = self.provide()
        deadline = self.repository.deliveries[response["ad"]["delivery_id"]]["display_expires_at"]
        self.now = deadline + timedelta(seconds=1)
        _, result = self.event(response, occurred_at=deadline)
        self.assertEqual(result["result"], "DELIVERY_INVALID")
        self.assertFalse(self.repository.usage)

    def test_split_delivery_exact_receive_delay_is_still_allowed(self):
        self.service = self.make_service(
            policy=replace(
                self.policy, delivery_ttl_seconds=1800, split_deadlines=True, cap_at_midnight=True
            )
        )
        response = self.provide()
        deadline = self.repository.deliveries[response["ad"]["delivery_id"]]["display_expires_at"]
        occurred = deadline - timedelta(milliseconds=1)
        self.now = occurred + timedelta(seconds=300)
        _, result = self.event(response, occurred_at=occurred)
        self.assertEqual(result["result"], "COUNTED")

    def test_split_delivery_display_deadline_is_part_of_proof(self):
        self.service = self.make_service(policy=replace(self.policy, split_deadlines=True))
        response = self.provide()
        stored = self.repository.deliveries[response["ad"]["delivery_id"]]
        stored["display_expires_at"] += timedelta(seconds=1)
        with self.assertRaises(NotFound):
            self.event(response)

    def test_measurement_lock_wait_uses_actual_decision_time_for_repeat_window(self):
        issued = self.now
        response = self.provide()
        self.now = issued + timedelta(seconds=2)
        original_lock = self.repository.lock_ad

        def wait_for_lock(ad):
            original_lock(ad)
            self.now = issued + timedelta(seconds=10)

        with patch.object(self.repository, "lock_ad", side_effect=wait_for_lock):
            data, first = self.event(response, occurred_at=issued + timedelta(seconds=1))
        self.assertEqual(utc_datetime(first["processed_at"]), issued + timedelta(seconds=10))
        self.now = issued + timedelta(seconds=62)
        _, second = self.event(self.provide())
        self.assertEqual(second["result"], "REPEAT_SUPPRESSED")
