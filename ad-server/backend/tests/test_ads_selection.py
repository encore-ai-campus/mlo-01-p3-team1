from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta, timezone
from itertools import permutations
from unittest import TestCase

from bson import Int64

from domains.ads.errors import ValidationError
from domains.ads.selection import (
    AdCandidate,
    RotationCursor,
    display_valid_until,
    select_ad,
)


class AdSelectionTests(TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 15, 1, tzinfo=UTC)
        self.cursor = RotationCursor("top")
        self.candidate = AdCandidate(
            ad_id="ad-a",
            placement="top",
            starts_at=self.now,
            ends_at=self.now + timedelta(hours=1),
            priority=1,
            paused=False,
            asset_available=True,
            budget_eligible=True,
            is_test=False,
        )

    def select(self, candidates, **overrides):
        options = {
            "placement": "top",
            "now": self.now,
            "cursor": self.cursor,
            "is_test": False,
        }
        return select_ad(candidates, **(options | overrides))

    def test_inclusive_start_and_exclusive_end_at_millisecond_precision(self):
        before = self.now - timedelta(milliseconds=1)
        self.assertIsNone(self.select([self.candidate], now=before).selected)
        self.assertEqual(self.select([self.candidate]).selected, self.candidate)
        end = self.candidate.ends_at
        self.assertEqual(
            self.select([self.candidate], now=end - timedelta(milliseconds=1)).selected,
            self.candidate,
        )
        self.assertIsNone(self.select([self.candidate], now=end).selected)
        self.assertIsNone(
            self.select([self.candidate], now=end + timedelta(microseconds=999)).selected
        )

    def test_priority_preserves_valid_bson_int64_values(self):
        candidate = replace(self.candidate, priority=Int64(2**31))
        self.assertEqual(self.select([candidate]).selected, candidate)

    def test_timezone_and_submillisecond_inputs_are_normalized_to_mongodb_precision(self):
        offset = timezone(timedelta(hours=9))
        candidate = replace(
            self.candidate,
            starts_at=self.now.astimezone(offset) + timedelta(microseconds=999),
            ends_at=self.candidate.ends_at.astimezone(offset) + timedelta(microseconds=999),
        )
        self.assertEqual(candidate.starts_at, self.now)
        self.assertEqual(candidate.ends_at, self.candidate.ends_at)
        self.assertIs(candidate.starts_at.tzinfo, UTC)
        self.assertEqual(self.select([candidate]).selected, candidate)

    def test_ineligible_candidates_never_override_an_eligible_lower_priority(self):
        for overrides in (
            {"placement": "bottom"},
            {"starts_at": self.now + timedelta(milliseconds=1)},
            {"ends_at": self.now, "starts_at": self.now - timedelta(hours=1)},
            {"paused": True},
            {"asset_available": False},
            {"budget_eligible": False},
            {"is_test": True},
        ):
            with self.subTest(overrides=overrides):
                blocked = replace(self.candidate, ad_id="blocked", priority=100, **overrides)
                decision = self.select([blocked, self.candidate])
                self.assertEqual(decision.selected, self.candidate)
                self.assertEqual(decision.next_cursor, RotationCursor("top", "ad-a"))

    def test_highest_priority_including_negative_values_is_selected(self):
        low = replace(self.candidate, ad_id="ad-a", priority=-2)
        high = replace(self.candidate, ad_id="ad-z", priority=-1)
        self.assertEqual(self.select([low, high]).selected, high)
        self.assertEqual(
            self.select([low, high], cursor=RotationCursor("top", "ad-z")).selected, high
        )

    def test_tied_priority_is_independent_of_input_order_and_uses_codepoint_sort(self):
        candidates = [replace(self.candidate, ad_id=ad_id) for ad_id in ("가", "a", "Z")]
        for ordering in permutations(candidates):
            with self.subTest(ordering=[candidate.ad_id for candidate in ordering]):
                self.assertEqual(self.select(ordering).selected.ad_id, "Z")
                self.assertEqual(
                    self.select(ordering, cursor=RotationCursor("top", "Z")).selected.ad_id,
                    "a",
                )
                self.assertEqual(
                    self.select(ordering, cursor=RotationCursor("top", "a")).selected.ad_id,
                    "가",
                )

    def test_removed_previous_id_uses_successor_and_wraps_when_no_greater_id(self):
        candidates = [self.candidate, replace(self.candidate, ad_id="ad-c")]
        successor = self.select(candidates, cursor=RotationCursor("top", "ad-b"))
        wrapped = self.select(candidates, cursor=RotationCursor("top", "ad-z"))
        self.assertEqual(successor.selected.ad_id, "ad-c")
        self.assertEqual(wrapped.selected.ad_id, "ad-a")
        self.assertTrue(successor.cursor_changed)
        self.assertTrue(wrapped.cursor_changed)

    def test_top_and_bottom_cursors_are_independent(self):
        candidates = [
            self.candidate,
            replace(self.candidate, ad_id="ad-b"),
            replace(self.candidate, ad_id="bottom-a", placement="bottom"),
            replace(self.candidate, ad_id="bottom-b", placement="bottom"),
        ]
        top = self.select(candidates, cursor=RotationCursor("top", "ad-a"))
        bottom = self.select(
            candidates, placement="bottom", cursor=RotationCursor("bottom", "bottom-b")
        )
        self.assertEqual(top.next_cursor, RotationCursor("top", "ad-b"))
        self.assertEqual(bottom.next_cursor, RotationCursor("bottom", "bottom-a"))
        with self.assertRaises(ValidationError):
            self.select(candidates, placement="bottom")

    def test_no_eligible_candidate_preserves_existing_cursor(self):
        cursor = RotationCursor("top", "previous")
        for candidates in ([], [replace(self.candidate, budget_eligible=False)]):
            with self.subTest(candidates=candidates):
                decision = self.select(candidates, cursor=cursor)
                self.assertIsNone(decision.selected)
                self.assertIs(decision.next_cursor, cursor)
                self.assertFalse(decision.cursor_changed)

    def test_calculation_without_advance_preserves_cursor_and_inputs(self):
        cursor = RotationCursor("top", "ad-a")
        candidates = [self.candidate, replace(self.candidate, ad_id="ad-b")]
        first = self.select(candidates, cursor=cursor, advance_cursor=False)
        second = self.select(candidates, cursor=cursor, advance_cursor=False)
        self.assertEqual(first, second)
        self.assertEqual(first.selected.ad_id, "ad-b")
        self.assertIs(first.next_cursor, cursor)
        self.assertFalse(first.cursor_changed)
        self.assertEqual(cursor.last_ad_id, "ad-a")
        self.assertEqual(candidates[0].ad_id, "ad-a")
        with self.assertRaises(FrozenInstanceError):
            self.candidate.priority = 10

    def test_single_candidate_keeps_same_cursor_value_after_wrap(self):
        cursor = RotationCursor("top", "ad-a")
        decision = self.select([self.candidate], cursor=cursor)
        self.assertEqual(decision.selected, self.candidate)
        self.assertEqual(decision.next_cursor, cursor)
        self.assertFalse(decision.cursor_changed)

    def test_server_test_environment_is_explicit_and_isolated(self):
        test_ad = replace(self.candidate, ad_id="test", priority=10, is_test=True)
        self.assertEqual(self.select([self.candidate, test_ad]).selected, self.candidate)
        self.assertEqual(self.select([self.candidate, test_ad], is_test=True).selected, test_ad)
        self.assertIsNone(self.select([self.candidate], is_test=True).selected)

    def test_budget_unknown_and_missing_are_rejected(self):
        with self.assertRaises(ValidationError):
            replace(self.candidate, budget_eligible=None)
        with self.assertRaises(TypeError):
            AdCandidate(
                ad_id="ad-a",
                placement="top",
                starts_at=self.now,
                ends_at=self.candidate.ends_at,
                priority=1,
                paused=False,
                asset_available=True,
                is_test=False,
            )

    def test_candidate_validation_rejects_malformed_server_data(self):
        malformed = [
            {"ad_id": " "},
            {"ad_id": None},
            {"placement": "middle"},
            {"placement": []},
            {"priority": True},
            {"priority": 1.0},
            {"priority": 2**63},
            {"priority": -(2**63) - 1},
            {"starts_at": self.now.replace(tzinfo=None)},
            {"ends_at": "invalid"},
            {"ends_at": self.now},
            {"starts_at": self.now + timedelta(microseconds=999), "ends_at": self.now},
        ]
        for field in ("paused", "asset_available", "budget_eligible", "is_test"):
            malformed.extend({field: value} for value in (None, 0, 1, "false"))
        for values in malformed:
            with self.subTest(values=values), self.assertRaises(ValidationError):
                replace(self.candidate, **values)
        self.assertEqual(replace(self.candidate, priority=-(2**63)).priority, -(2**63))
        self.assertEqual(replace(self.candidate, priority=2**63 - 1).priority, 2**63 - 1)

    def test_selection_rejects_duplicate_ids_and_invalid_parameters(self):
        for candidates in (
            [self.candidate, self.candidate],
            [self.candidate, replace(self.candidate, placement="bottom")],
            [{}],
            None,
        ):
            with self.subTest(candidates=candidates), self.assertRaises(ValidationError):
                self.select(candidates)
        for overrides in (
            {"placement": "unknown"},
            {"cursor": {}},
            {"now": self.now.replace(tzinfo=None)},
            {"is_test": None},
            {"is_test": 0},
            {"advance_cursor": 1},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(ValidationError):
                self.select([self.candidate], **overrides)
        for values in ({"placement": "middle"}, {"placement": "top", "last_ad_id": " "}):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                RotationCursor(**values)


class AdDisplayValidityTests(TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 15, 1, tzinfo=UTC)
        self.end = self.now + timedelta(hours=1)
        self.expiry = self.now + timedelta(minutes=1)

    def test_display_is_limited_to_three_seconds_from_evaluation(self):
        self.assertEqual(
            display_valid_until(self.now, self.end, event_expires_at=self.expiry),
            self.now + timedelta(seconds=3),
        )

    def test_earlier_ad_end_and_event_expiry_cap_display(self):
        boundary = self.now + timedelta(milliseconds=1500)
        self.assertEqual(
            display_valid_until(self.now, boundary, event_expires_at=self.expiry), boundary
        )
        self.assertEqual(
            display_valid_until(self.now, self.end, event_expires_at=boundary), boundary
        )
        three_seconds = self.now + timedelta(seconds=3)
        self.assertEqual(
            display_valid_until(self.now, three_seconds, event_expires_at=self.expiry),
            three_seconds,
        )

    def test_ended_or_expired_display_returns_none(self):
        for boundary in (self.now, self.now - timedelta(milliseconds=1)):
            with self.subTest(boundary=boundary):
                self.assertIsNone(
                    display_valid_until(self.now, boundary, event_expires_at=self.expiry)
                )
                self.assertIsNone(
                    display_valid_until(self.now, self.end, event_expires_at=boundary)
                )

    def test_normalization_and_explicit_timezone_are_required(self):
        offset = timezone(timedelta(hours=9))
        result = display_valid_until(
            self.now.astimezone(offset) + timedelta(microseconds=999),
            self.end.astimezone(offset),
            event_expires_at=self.expiry.astimezone(offset),
        )
        self.assertEqual(result, self.now + timedelta(seconds=3))
        self.assertIs(result.tzinfo, UTC)
        for values in (
            (self.now.replace(tzinfo=None), self.end, self.expiry),
            (self.now, self.end.replace(tzinfo=None), self.expiry),
            (self.now, self.end, self.expiry.replace(tzinfo=None)),
            (self.now, self.end, None),
        ):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                display_valid_until(values[0], values[1], event_expires_at=values[2])
        with self.assertRaises(TypeError):
            display_valid_until(self.now, self.end)

    def test_valid_until_handles_last_datetime_without_overflow(self):
        end = datetime.max.replace(tzinfo=UTC, microsecond=999000)
        evaluated_at = end - timedelta(seconds=1)
        self.assertEqual(display_valid_until(evaluated_at, end, event_expires_at=end), end)
