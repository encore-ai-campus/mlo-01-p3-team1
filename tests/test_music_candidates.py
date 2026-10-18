from fractions import Fraction
import unittest

from music_playback.candidates import choose_playlist, filter_general
from music_playback.seasonality import screen_track


def candidate(key, duration, score="100", speed="slow"):
    return {"track_id": key, "duration_ms": str(duration), "weather_score_exact": score,
            "speed": speed, "occasion_status": "GENERAL", "track_name": "A Song", "album_name": "Album", "artists": "Artist"}


class GeneralCandidateTests(unittest.TestCase):
    def choose(self, rows, **kwargs):
        return choose_playlist(rows, ["slow"], target=100, minimum=90, maximum=110, **kwargs)

    def test_exact_time_has_priority_over_earlier_feasible(self):
        rows, summary = self.choose([candidate("a", 95), candidate("b", 60), candidate("c", 40)])
        self.assertEqual({row["track_id"] for row in rows}, {"b", "c"})
        self.assertTrue(summary["exact_target_achieved"])

    def test_above_target_has_priority_over_below(self):
        rows, _ = self.choose([candidate("a", 99), candidate("b", 101)])
        self.assertEqual([row["track_id"] for row in rows], ["b"])

    def test_boundaries_accepted_and_outside_is_shortage(self):
        for value in (90, 100, 110):
            rows, _ = self.choose([candidate("a", value)])
            self.assertEqual(sum(int(row["duration_ms"]) for row in rows), value)
        for value in (89, 111):
            rows, summary = self.choose([candidate("a", value)])
            self.assertEqual(rows, [])
            self.assertEqual(summary["status"], "CANDIDATE_SHORTAGE")
            self.assertFalse(summary["automatic_shortening"])

    def test_held_track_never_reenters_to_fill_duration(self):
        rows = [candidate("a", 50), candidate("b", 50)]
        decisions = {"a": screen_track(rows[0]), "b": screen_track({**rows[1], "track_name": "Merry Christmas"})}
        filtered = filter_general(rows, decisions)
        result, summary = self.choose(filtered)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(result, [])
        self.assertFalse(summary["held_tracks_restored"])

    def test_missing_decision_and_duplicate_ids_fail_closed(self):
        row = candidate("a", 100)
        with self.assertRaises(ValueError):
            filter_general([row], {})
        decision = screen_track(row)
        with self.assertRaises(ValueError):
            filter_general([row, row], {"a": decision})

    def test_speed_and_exact_score_values_preserved(self):
        row = candidate("a", 100, "751/10")
        rows, summary = self.choose([row, candidate("b", 100, speed="fast")])
        self.assertEqual(rows, [row])
        self.assertEqual(Fraction(summary["quality_time_weighted_exact"]), Fraction(751, 10))
        self.assertEqual(summary["quality_optimality"], "NOT_PROVEN")

    def test_non_general_cannot_be_passed_directly_to_solver(self):
        with self.assertRaises(ValueError):
            self.choose([{**candidate("a", 100), "occasion_status": "REVIEW_REQUIRED"}])


if __name__ == "__main__":
    unittest.main()
