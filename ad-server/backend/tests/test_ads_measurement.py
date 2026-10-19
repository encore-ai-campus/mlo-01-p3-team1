from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from unittest import TestCase

from domains.ads.errors import DomainError, IdempotencyConflict, NotFound, ValidationError
from domains.ads.measurement import (
    ADS_POLICY_VERSION,
    DeliveryContext,
    MeasurementEvent,
    RecordedEvent,
    estimate_tokens,
    judge_event,
    repeat_key,
    validate_event_input,
)
from domains.ads.public_policy import AdsPublicPolicy


class MeasurementRulesTests(TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 15, 1, tzinfo=UTC)
        self.delivery = DeliveryContext(
            delivery_id="delivery-1",
            owner_guest_id="shared-guest-1",
            ad_id="ad-1",
            creative_version="creative-1",
            placement="top",
            issued_at=self.now - timedelta(minutes=1),
            starts_at=self.now - timedelta(hours=1),
            ends_at=self.now + timedelta(hours=1),
            stopped_at=None,
            is_test=False,
        )
        self.event = MeasurementEvent("event-1", "delivery-1", "VIEWABLE_IMPRESSION", self.now)

    def judge(self, event=None, **overrides):
        event = event or self.event
        received = (
            overrides["received_at"]
            if "received_at" in overrides
            else event.occurred_at + timedelta(milliseconds=100)
        )
        arguments = {
            "delivery": self.delivery,
            "owner_guest_id": self.delivery.owner_guest_id,
            "received_at": received,
            "processed_at": received,
            "delivery_valid": True,
            "occurrence_eligible": True,
            "measurement_available": True,
            "delivery_type_consumed": False,
            "last_accepted_at": None,
        }
        arguments.update(overrides)
        return judge_event(event, **arguments)

    def test_requests_cannot_supply_trusted_server_fields(self):
        body = {
            "event_id": "event-1",
            "delivery_id": "delivery-1",
            "event_type": "CLICK",
            "occurred_at": "2026-10-15T01:00:00.000Z",
        }
        for forbidden in (
            "owner_guest_id",
            "ad_id",
            "placement",
            "creative_version",
            "counted",
            "estimated_tokens",
            "is_test",
            "target_tag_codes",
            "ads_policy_version",
        ):
            with self.subTest(field=forbidden), self.assertRaises(ValidationError):
                validate_event_input({**body, forbidden: True})

    def test_malformed_missing_and_unsupported_event_inputs_are_rejected(self):
        body = {
            "event_id": "event-1",
            "delivery_id": "delivery-1",
            "event_type": "CLICK",
            "occurred_at": self.now,
        }
        variants = [None, [], {key: value for key, value in body.items() if key != "event_id"}]
        for field, value in (
            ("event_id", True),
            ("delivery_id", " "),
            ("event_type", "RENDER"),
            ("event_type", []),
            ("occurred_at", "2026-10-15T01:00:00"),
        ):
            variants.append({**body, field: value})
        for variant in variants:
            with self.subTest(input=variant), self.assertRaises(ValidationError):
                validate_event_input(variant)

    def test_timezone_equivalent_requests_have_the_same_canonical_hash(self):
        local = replace(self.event, occurred_at="2026-10-15T10:00:00.000900+09:00")
        self.assertEqual(local.request_hash, self.event.request_hash)
        self.assertEqual(local.occurred_at, self.now)

    def test_first_valid_report_consumes_type_and_advances_server_window(self):
        outcome = self.judge()
        self.assertEqual(outcome.decision.result, "COUNTED")
        self.assertEqual(outcome.decision.estimated_tokens, 8)
        self.assertTrue(outcome.consume_delivery_type)
        self.assertEqual(outcome.new_accepted_at, outcome.decision.processed_at)
        self.assertEqual(outcome.decision.accepted_at, outcome.new_accepted_at)

    def test_early_click_is_only_15_and_does_not_imply_an_impression(self):
        click = self.judge(replace(self.event, event_type="CLICK"))
        self.assertEqual(click.decision.estimated_tokens, 15)
        self.assertEqual(click.decision.event_type, "CLICK")
        for placement, expected in (("top", 23), ("bottom", 20)):
            delivery = replace(self.delivery, placement=placement)
            impression = self.judge(delivery=delivery)
            click = self.judge(replace(self.event, event_type="CLICK"), delivery=delivery)
            self.assertEqual(
                impression.decision.estimated_tokens + click.decision.estimated_tokens, expected
            )

    def test_non_counted_reports_have_no_estimated_usage(self):
        for placement in ("top", "bottom"):
            for event_type in ("VIEWABLE_IMPRESSION", "CLICK"):
                self.assertEqual(estimate_tokens(placement, event_type, counted=False), 0)
        with self.assertRaises(ValidationError):
            estimate_tokens("top", "CLICK", counted=1)

    def test_second_report_for_a_consumed_delivery_type_is_duplicate(self):
        duplicate = self.judge(replace(self.event, event_id="event-2"), delivery_type_consumed=True)
        self.assertEqual(duplicate.decision.result, "DELIVERY_DUPLICATE")
        self.assertEqual(duplicate.decision.estimated_tokens, 0)
        self.assertFalse(duplicate.consume_delivery_type)
        self.assertIsNone(duplicate.new_accepted_at)

    def test_repeat_windows_allow_exact_60_and_300_second_boundaries(self):
        for event_type, seconds in (("VIEWABLE_IMPRESSION", 60), ("CLICK", 300)):
            event = replace(self.event, event_type=event_type)
            processed = self.now + timedelta(milliseconds=100)
            for offset in (-1, 0, 1):
                age = timedelta(seconds=seconds, milliseconds=offset)
                outcome = self.judge(event, last_accepted_at=processed - age)
                with self.subTest(event_type=event_type, offset=offset):
                    self.assertEqual(outcome.decision.counted, offset >= 0)
                    self.assertTrue(outcome.consume_delivery_type)
                    if offset < 0:
                        self.assertEqual(outcome.decision.result, "REPEAT_SUPPRESSED")
                        self.assertIsNone(outcome.new_accepted_at)

    def test_repeat_window_uses_processing_time_not_client_occurrence_time(self):
        received = self.now + timedelta(seconds=50)
        processed = self.now + timedelta(seconds=60)
        outcome = self.judge(
            received_at=received, processed_at=processed, last_accepted_at=self.now
        )
        self.assertTrue(outcome.decision.counted)
        self.assertEqual(outcome.decision.accepted_at, processed)

    def test_suppressed_delivery_remains_consumed_after_window_finishes(self):
        first = self.judge(last_accepted_at=self.now)
        self.assertEqual(first.decision.result, "REPEAT_SUPPRESSED")
        replay = self.judge(
            received_at=self.now + timedelta(seconds=61),
            processed_at=self.now + timedelta(seconds=61),
            recorded_event=RecordedEvent(self.event, self.delivery.owner_guest_id, first.decision),
        )
        self.assertEqual(replay.decision, first.decision)
        self.assertTrue(replay.replayed)
        self.assertFalse(replay.consume_delivery_type)
        self.assertIsNone(replay.new_accepted_at)
        new_id = self.judge(
            replace(self.event, event_id="later-id"),
            delivery_type_consumed=True,
            last_accepted_at=None,
        )
        self.assertEqual(new_id.decision.result, "DELIVERY_DUPLICATE")

    def test_replay_keeps_first_times_and_cost_after_expiry_or_stop(self):
        first = self.judge()
        recorded = RecordedEvent(self.event, self.delivery.owner_guest_id, first.decision)
        replay = self.judge(
            delivery=replace(self.delivery, stopped_at=self.now),
            received_at=self.now + timedelta(hours=2),
            processed_at=self.now + timedelta(hours=2),
            delivery_valid=False,
            occurrence_eligible=False,
            delivery_type_consumed=True,
            recorded_event=recorded,
        )
        self.assertEqual(replay.decision.as_response(), first.decision.as_response())
        self.assertFalse(replay.consume_delivery_type)
        self.assertIsNone(replay.new_accepted_at)

    def test_same_event_id_with_different_body_is_conflict(self):
        first = self.judge()
        record = RecordedEvent(self.event, self.delivery.owner_guest_id, first.decision)
        for changed in (
            replace(self.event, event_type="CLICK"),
            replace(self.event, delivery_id="another-delivery"),
            replace(self.event, occurred_at=self.now + timedelta(milliseconds=1)),
        ):
            with self.subTest(event=changed), self.assertRaises(IdempotencyConflict):
                self.judge(changed, recorded_event=record)

    def test_another_guest_cannot_replay_someones_event(self):
        record = RecordedEvent(self.event, self.delivery.owner_guest_id, self.judge().decision)
        with self.assertRaises(NotFound):
            self.judge(owner_guest_id="another-guest", recorded_event=record)

    def test_wrong_original_event_record_is_rejected(self):
        record = RecordedEvent(self.event, self.delivery.owner_guest_id, self.judge().decision)
        with self.assertRaises(ValidationError):
            self.judge(replace(self.event, event_id="another-id"), recorded_event=record)

    def test_wrong_guest_or_delivery_is_not_found(self):
        with self.assertRaises(NotFound):
            self.judge(owner_guest_id="another-guest")
        with self.assertRaises(NotFound):
            self.judge(replace(self.event, delivery_id="another-delivery"))

    def test_receive_delay_includes_300_seconds_and_excludes_next_millisecond(self):
        for delay_ms, expected in ((300_000, "COUNTED"), (300_001, "LATE_EVENT")):
            received = self.now + timedelta(milliseconds=delay_ms)
            outcome = self.judge(received_at=received, processed_at=received)
            with self.subTest(delay_ms=delay_ms):
                self.assertEqual(outcome.decision.result, expected)
                self.assertEqual(outcome.consume_delivery_type, expected == "COUNTED")

    def test_future_report_is_excluded_and_does_not_consume_type(self):
        outcome = self.judge(
            received_at=self.now - timedelta(milliseconds=1), processed_at=self.now
        )
        self.assertEqual(outcome.decision.result, "DELIVERY_INVALID")
        self.assertFalse(outcome.consume_delivery_type)
        self.assertIsNone(outcome.new_accepted_at)

    def test_extreme_future_utc_date_does_not_overflow_kst_conversion(self):
        event = replace(self.event, occurred_at="9999-12-31T23:59:59.999Z")
        outcome = self.judge(event, received_at=self.now, processed_at=self.now)
        self.assertEqual(outcome.decision.result, "DELIVERY_INVALID")
        self.assertIsNone(outcome.decision.metric_date_kst)
        self.assertFalse(outcome.consume_delivery_type)
        self.assertEqual(outcome.decision.estimated_tokens, 0)

    def test_report_before_delivery_issue_is_excluded(self):
        event = replace(self.event, occurred_at=self.delivery.issued_at - timedelta(milliseconds=1))
        self.assertEqual(self.judge(event).decision.result, "DELIVERY_INVALID")

    def test_ad_start_is_included_and_end_is_excluded(self):
        delivery = replace(self.delivery, issued_at=self.now - timedelta(hours=2))
        for at, expected in (
            (delivery.starts_at - timedelta(milliseconds=1), False),
            (delivery.starts_at, True),
            (delivery.ends_at - timedelta(milliseconds=1), True),
            (delivery.ends_at, False),
        ):
            with self.subTest(at=at):
                self.assertEqual(
                    self.judge(
                        replace(self.event, occurred_at=at), delivery=delivery
                    ).decision.counted,
                    expected,
                )

    def test_stop_before_event_is_excluded_but_earlier_delayed_event_is_valid(self):
        stopped = self.now + timedelta(seconds=10)
        delivery = replace(self.delivery, stopped_at=stopped)
        for delta_ms, expected in (
            (-1, "COUNTED"),
            (0, "DELIVERY_INVALID"),
            (1, "DELIVERY_INVALID"),
        ):
            event = replace(self.event, occurred_at=stopped + timedelta(milliseconds=delta_ms))
            with self.subTest(delta_ms=delta_ms):
                self.assertEqual(
                    self.judge(
                        event,
                        delivery=delivery,
                        received_at=stopped + timedelta(seconds=30),
                        processed_at=stopped + timedelta(seconds=31),
                    ).decision.result,
                    expected,
                )

    def test_valid_occurrence_can_be_received_after_the_ad_ends(self):
        event = replace(self.event, occurred_at=self.delivery.ends_at - timedelta(milliseconds=1))
        received = self.delivery.ends_at + timedelta(seconds=20)
        outcome = self.judge(event, received_at=received, processed_at=received)
        self.assertTrue(outcome.decision.counted)

    def test_legacy_delivery_has_no_implicit_display_deadline(self):
        self.assertIsNone(self.delivery.display_expires_at)
        event = replace(self.event, occurred_at=self.delivery.issued_at + timedelta(minutes=31))
        self.assertEqual(self.judge(event).decision.result, "COUNTED")

    def test_display_deadline_normalizes_to_utc_and_must_follow_issue_time(self):
        delivery = replace(self.delivery, display_expires_at="2026-10-15T10:01:00+09:00")
        self.assertEqual(delivery.display_expires_at, self.now + timedelta(minutes=1))
        self.assertEqual(delivery.display_expires_at.tzinfo, UTC)
        for deadline in (
            self.delivery.issued_at,
            self.delivery.issued_at - timedelta(milliseconds=1),
            "2026-10-15T01:01:00",
            True,
        ):
            with self.subTest(deadline=deadline), self.assertRaises(ValidationError):
                replace(self.delivery, display_expires_at=deadline)

    def test_display_deadline_is_exclusive_for_event_occurrence(self):
        deadline = self.now + timedelta(minutes=1)
        delivery = replace(self.delivery, display_expires_at=deadline)
        for offset_ms, expected in (
            (-1, "COUNTED"),
            (0, "DELIVERY_INVALID"),
            (1, "DELIVERY_INVALID"),
        ):
            event = replace(self.event, occurred_at=deadline + timedelta(milliseconds=offset_ms))
            with self.subTest(offset_ms=offset_ms):
                outcome = self.judge(event, delivery=delivery)
                self.assertEqual(outcome.decision.result, expected)
                self.assertEqual(outcome.consume_delivery_type, expected == "COUNTED")
                if expected != "COUNTED":
                    self.assertEqual(outcome.decision.estimated_tokens, 0)
                    self.assertIsNone(outcome.new_accepted_at)

    def test_before_display_deadline_can_arrive_after_display_and_within_delay_limit(self):
        deadline = self.now + timedelta(minutes=1)
        delivery = replace(self.delivery, display_expires_at=deadline)
        event = replace(self.event, occurred_at=deadline - timedelta(milliseconds=1))
        received = event.occurred_at + timedelta(seconds=300)
        outcome = self.judge(event, delivery=delivery, received_at=received, processed_at=received)
        self.assertEqual(outcome.decision.result, "COUNTED")
        expired_report = self.judge(
            event,
            delivery=delivery,
            received_at=received,
            processed_at=received,
            delivery_valid=False,
        )
        self.assertEqual(expired_report.decision.result, "DELIVERY_INVALID")

    def test_saved_first_decision_is_not_recomputed_when_display_deadline_changes(self):
        first = self.judge(
            delivery=replace(self.delivery, display_expires_at=self.now + timedelta(minutes=1))
        )
        replay = self.judge(
            delivery=replace(self.delivery, display_expires_at=self.now),
            recorded_event=RecordedEvent(self.event, self.delivery.owner_guest_id, first.decision),
            received_at=self.now + timedelta(hours=1),
            processed_at=self.now + timedelta(hours=1),
            delivery_valid=False,
        )
        self.assertEqual(replay.decision, first.decision)
        self.assertTrue(replay.replayed)
        self.assertFalse(replay.consume_delivery_type)

    def test_split_deadline_policy_defaults_to_legacy_and_requires_strict_bool(self):
        arguments = {
            "version": "FIXTURE/deadline/v1",
            "delivery_ttl_seconds": 1800,
            "budget_eligible": lambda *args: True,
            "open_delivery_eligible": lambda *args: True,
            "occurrence_eligible": lambda *args: True,
        }
        self.assertFalse(AdsPublicPolicy(**arguments).split_deadlines)
        self.assertTrue(AdsPublicPolicy(**arguments, split_deadlines=True).split_deadlines)
        for flag in (None, 0, 1, "true", []):
            with self.subTest(flag=flag), self.assertRaises(DomainError):
                AdsPublicPolicy(**arguments, split_deadlines=flag)

    def test_delivery_expiry_and_unknown_creative_policy_are_explicit_server_inputs(self):
        for field in ("delivery_valid", "occurrence_eligible"):
            with self.subTest(field=field):
                excluded = self.judge(**{field: False})
                self.assertEqual(excluded.decision.result, "DELIVERY_INVALID")
                self.assertFalse(excluded.consume_delivery_type)
                with self.assertRaises(ValidationError):
                    self.judge(**{field: None})

    def test_unavailable_context_and_test_delivery_do_not_count_operational_usage(self):
        for arguments in (
            {"measurement_available": False},
            {"delivery": replace(self.delivery, is_test=True)},
        ):
            with self.subTest(arguments=arguments):
                outcome = self.judge(**arguments)
                self.assertEqual(outcome.decision.result, "MEASUREMENT_UNAVAILABLE")
                self.assertEqual(outcome.decision.estimated_tokens, 0)
                self.assertFalse(outcome.consume_delivery_type)

    def test_repeat_key_keeps_same_ad_across_new_delivery_and_creative_versions(self):
        key = repeat_key(self.delivery, "CLICK")
        changed = replace(self.delivery, delivery_id="delivery-2", creative_version="creative-2")
        self.assertEqual(repeat_key(changed, "CLICK"), key)
        for field, value in (
            ("ad_id", "ad-2"),
            ("owner_guest_id", "guest-2"),
            ("placement", "bottom"),
        ):
            self.assertNotEqual(repeat_key(replace(changed, **{field: value}), "CLICK"), key)
        self.assertNotEqual(repeat_key(changed, "VIEWABLE_IMPRESSION"), key)

    def test_kst_day_uses_occurrence_even_when_receive_crosses_midnight(self):
        for occurred, expected in (
            (datetime(2026, 10, 15, 14, 59, 59, 999000, tzinfo=UTC), date(2026, 10, 15)),
            (datetime(2026, 10, 15, 15, tzinfo=UTC), date(2026, 10, 16)),
        ):
            delivery = replace(
                self.delivery,
                issued_at=occurred - timedelta(minutes=1),
                starts_at=occurred - timedelta(hours=1),
                ends_at=occurred + timedelta(hours=1),
            )
            outcome = self.judge(
                replace(self.event, occurred_at=occurred),
                delivery=delivery,
                received_at=occurred + timedelta(seconds=1),
                processed_at=occurred + timedelta(seconds=2),
            )
            self.assertEqual(outcome.decision.metric_date_kst, expected)

    def test_invalid_processing_and_repeat_server_times_are_rejected(self):
        with self.assertRaises(ValidationError):
            self.judge(processed_at=self.now)
        with self.assertRaises(ValidationError):
            self.judge(last_accepted_at=self.now + timedelta(hours=1))

    def test_invalid_report_leaves_delivery_type_available_for_a_new_valid_event(self):
        invalid = self.judge(delivery_valid=False)
        self.assertFalse(invalid.consume_delivery_type)
        valid = self.judge(
            replace(self.event, event_id="new-valid"),
            delivery_type_consumed=invalid.consume_delivery_type,
        )
        self.assertTrue(valid.decision.counted)

    def test_response_matches_existing_ads_contract_without_internal_refs_or_usage(self):
        response = self.judge().decision.as_response()
        self.assertEqual(
            set(response),
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
        self.assertEqual(response["ads_policy_version"], ADS_POLICY_VERSION)
        self.assertEqual(response["occurred_at"], "2026-10-15T01:00:00.000Z")
        self.assertEqual(response["received_at"], "2026-10-15T01:00:00.100Z")
