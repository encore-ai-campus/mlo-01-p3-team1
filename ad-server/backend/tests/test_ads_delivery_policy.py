"""공유 사용자·DB 없이 배달 마감과 당시 소재 자격만 검증합니다."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta

from django.test import SimpleTestCase

from domains.ads.delivery_policy import (
    delivery_deadlines,
    occurrence_eligible,
    open_delivery_eligible,
)
from domains.ads.errors import ValidationError


class DeliveryDeadlinesTests(SimpleTestCase):
    def setUp(self):
        self.issued_at = datetime(2026, 10, 15, 5, tzinfo=UTC)
        self.ends_at = self.issued_at + timedelta(hours=3)

    def test_default_display_is_thirty_minutes_and_report_has_five_more(self):
        display, report = delivery_deadlines(self.issued_at, self.ends_at)
        self.assertEqual(display, self.issued_at + timedelta(minutes=30))
        self.assertEqual(report, self.issued_at + timedelta(minutes=35))
        self.assertEqual(self.ends_at, self.issued_at + timedelta(hours=3))

    def test_campaign_end_shortens_display_but_retains_reporting_grace(self):
        end = self.issued_at + timedelta(seconds=45)
        display, report = delivery_deadlines(self.issued_at, end)
        self.assertEqual(display, end)
        self.assertEqual(report, end + timedelta(seconds=300))

    def test_next_kst_midnight_caps_display_and_report_crosses_into_next_day(self):
        issued_at = datetime(2026, 10, 15, 14, 50, tzinfo=UTC)
        display, report = delivery_deadlines(
            issued_at, issued_at + timedelta(hours=2), cap_at_midnight=True
        )
        self.assertEqual(display, datetime(2026, 10, 15, 15, tzinfo=UTC))
        self.assertEqual(report, datetime(2026, 10, 15, 15, 5, tzinfo=UTC))

    def test_unconfirmed_midnight_cap_is_not_enabled_by_default(self):
        issued_at = datetime(2026, 10, 15, 14, 50, tzinfo=UTC)
        display, report = delivery_deadlines(issued_at, issued_at + timedelta(hours=2))
        self.assertEqual(display, issued_at + timedelta(minutes=30))
        self.assertEqual(report, issued_at + timedelta(minutes=35))

    def test_midnight_cap_rejects_non_boolean_configuration(self):
        for value in (None, 0, 1, "true"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                delivery_deadlines(self.issued_at, self.ends_at, cap_at_midnight=value)

    def test_issue_exactly_at_kst_midnight_uses_the_following_midnight(self):
        issued_at = datetime(2026, 10, 15, 15, tzinfo=UTC)
        display, report = delivery_deadlines(
            issued_at, issued_at + timedelta(hours=1), cap_at_midnight=True
        )
        self.assertEqual(display, issued_at + timedelta(minutes=30))
        self.assertEqual(report, issued_at + timedelta(minutes=35))

    def test_offset_input_and_millisecond_precision_are_normalized_to_utc(self):
        display, report = delivery_deadlines(
            "2026-10-15T14:00:00.123456+09:00", "2026-10-15T16:00:00+09:00"
        )
        self.assertEqual(display, datetime(2026, 10, 15, 5, 30, 0, 123000, tzinfo=UTC))
        self.assertEqual(report.microsecond, 123000)
        self.assertEqual(report.utcoffset(), timedelta(0))

    def test_custom_positive_ttl_still_has_separate_report_grace(self):
        display, report = delivery_deadlines(self.issued_at, self.ends_at, ttl_seconds=60)
        self.assertEqual(display, self.issued_at + timedelta(seconds=60))
        self.assertEqual(report, self.issued_at + timedelta(seconds=360))

    def test_ttl_exactly_reaching_midnight_keeps_reporting_grace(self):
        issued_at = datetime(2026, 10, 15, 14, 30, tzinfo=UTC)
        display, report = delivery_deadlines(
            issued_at, issued_at + timedelta(hours=2), cap_at_midnight=True
        )
        self.assertEqual(display, datetime(2026, 10, 15, 15, tzinfo=UTC))
        self.assertEqual(report, datetime(2026, 10, 15, 15, 5, tzinfo=UTC))

    def test_campaign_end_must_be_strictly_after_issue(self):
        for end in (self.issued_at, self.issued_at - timedelta(milliseconds=1)):
            with self.subTest(end=end), self.assertRaises(ValidationError):
                delivery_deadlines(self.issued_at, end)

    def test_millisecond_normalization_cannot_create_a_zero_length_display(self):
        issued_at = self.issued_at.replace(microsecond=100)
        end = self.issued_at.replace(microsecond=999)
        with self.assertRaises(ValidationError):
            delivery_deadlines(issued_at, end)

    def test_naive_or_invalid_times_are_rejected(self):
        for issued_at, end in (
            (self.issued_at.replace(tzinfo=None), self.ends_at),
            (self.issued_at, self.ends_at.replace(tzinfo=None)),
            ("invalid", self.ends_at),
            (self.issued_at, None),
        ):
            with self.subTest(issued_at=issued_at, end=end), self.assertRaises(ValidationError):
                delivery_deadlines(issued_at, end)

    def test_ttl_rejects_booleans_nonintegers_and_nonpositive_values(self):
        for ttl in (True, False, 0, -1, 1.0, "1800", None):
            with self.subTest(ttl=ttl), self.assertRaises(ValidationError):
                delivery_deadlines(self.issued_at, self.ends_at, ttl_seconds=ttl)

    def test_unrepresentable_ttl_is_a_domain_validation_error(self):
        with self.assertRaises(ValidationError):
            delivery_deadlines(self.issued_at, self.ends_at, ttl_seconds=10**30)

    def test_unrepresentable_next_midnight_is_a_domain_validation_error(self):
        issued_at = datetime(9999, 12, 31, 14, 59, tzinfo=UTC)
        with self.assertRaises(ValidationError):
            delivery_deadlines(issued_at, issued_at + timedelta(seconds=30), cap_at_midnight=True)


class DeliveryCreativePolicyTests(SimpleTestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 15, tzinfo=UTC)
        self.delivery = {"creative_version": "original", "placement": "top"}

    def test_current_matching_creative_and_placement_are_eligible(self):
        self.assertTrue(open_delivery_eligible(self.delivery, dict(self.delivery), self.now))

    def test_current_creative_replacement_or_placement_change_invalidates_old_delivery(self):
        for changed in (
            {"creative_version": "replacement", "placement": "top"},
            {"creative_version": "original", "placement": "bottom"},
        ):
            with self.subTest(changed=changed):
                self.assertFalse(open_delivery_eligible(self.delivery, changed, self.now))

    def test_pre_edit_occurrence_uses_the_old_historical_snapshot(self):
        historical = dict(self.delivery)
        current = {**self.delivery, "creative_version": "replacement"}
        self.assertFalse(open_delivery_eligible(self.delivery, current, self.now))
        self.assertTrue(
            occurrence_eligible(self.delivery, historical, self.now - timedelta(seconds=1))
        )
        self.assertFalse(occurrence_eligible(self.delivery, current, self.now))

    def test_missing_invalid_or_blank_creative_references_are_ineligible(self):
        for source in (
            None,
            [],
            {},
            {"creative_version": "", "placement": "top"},
            {"creative_version": True, "placement": "top"},
        ):
            with self.subTest(source=source):
                self.assertFalse(open_delivery_eligible(source, source, self.now))
                self.assertFalse(occurrence_eligible(self.delivery, source, self.now))

    def test_helpers_leave_period_state_and_budget_checks_to_the_service(self):
        snapshot = {**self.delivery, "paused": True, "ends_at": self.now - timedelta(days=1)}
        self.assertTrue(open_delivery_eligible(self.delivery, snapshot, self.now))
        self.assertTrue(occurrence_eligible(self.delivery, snapshot, self.now))

    def test_creative_checks_do_not_mutate_delivery_or_ad(self):
        ad = dict(self.delivery)
        before = deepcopy((self.delivery, ad))
        open_delivery_eligible(self.delivery, ad, self.now)
        occurrence_eligible(self.delivery, ad, self.now)
        self.assertEqual((self.delivery, ad), before)
