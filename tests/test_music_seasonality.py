import unittest

from music_playback.seasonality import screen_track


def track(title, album="Studio Album", artist="Example Artist", track_id="one"):
    return {"track_id": track_id, "track_name": title, "album_name": album, "artists": artist}


class OccasionScreenTests(unittest.TestCase):
    def test_explicit_title_excludes_and_preserves_source(self):
        row = track("Merry Christmas", "Christmas Dinner 2022", "Bryan Adams")
        before = dict(row)
        result = screen_track(row)
        self.assertEqual((result.occasion_status, result.decision_source), ("SEASONAL_EVENT", "APPROVED_RULE"))
        self.assertEqual(result.occasion_codes, ("CHRISTMAS",))
        self.assertEqual(row, before)

    def test_compilation_album_only_holds_rather_than_labels_song(self):
        result = screen_track(track("God Only Knows", "Christmas Songs 2022", "The Beach Boys"))
        self.assertEqual(result.occasion_status, "REVIEW_REQUIRED")
        self.assertIn("EVENT_ALBUM_ONLY", result.reasons)

    def test_ambiguous_carol_title_is_not_automatically_approved(self):
        self.assertEqual(screen_track(track("Joy To The World", artist="Three Dog Night")).occasion_status, "REVIEW_REQUIRED")
        self.assertEqual(screen_track(track("Joy To The World - Remastered 1999", artist="Nat King Cole")).occasion_status, "SEASONAL_EVENT")

    def test_snow_winter_holiday_and_artist_names_do_not_exclude(self):
        for row in [track("Snow"), track("Winter"), track("Holiday"),
                    track("The Four Seasons - Winter in F Minor", artist="Antonio Vivaldi"),
                    track("Autumn In New York", artist="Billie Holiday"),
                    track("A Song", artist="Santa"), track("Carol", artist="Noel")]:
            with self.subTest(row=row):
                self.assertEqual(screen_track(row).occasion_status, "GENERAL")

    def test_word_boundaries_and_unicode(self):
        self.assertEqual(screen_track(track("Christmasland")).occasion_status, "GENERAL")
        for name in ("크리스마스 선물", "Ｍｅｒｒｙ　Ｃｈｒｉｓｔｍａｓ", "Feliz Navidad", "Weihnachtslieder"):
            self.assertEqual(screen_track(track(name)).occasion_status, "SEASONAL_EVENT")

    def test_missing_metadata_is_unscreened_not_general(self):
        self.assertEqual(screen_track(track("A Song", album="")).occasion_status, "UNSCREENED")

    def test_human_override_requires_matching_source_and_evidence(self):
        row = track("Joy To The World", artist="Three Dog Night")
        override = {"occasion_status": "GENERAL", "reviewer": "reviewer-1", "evidence": "recording inspected",
                    "reviewed_at": "2026-10-16T00:00:00Z", "source_dataset_sha256": "abc"}
        decision = screen_track(row, override, "abc")
        self.assertEqual((decision.occasion_status, decision.decision_source), ("GENERAL", "HUMAN_REVIEW"))
        with self.assertRaises(ValueError):
            screen_track(row, override, "changed-source")

    def test_decision_versions_are_reproducible_and_capture_changes(self):
        row = track("A Song")
        self.assertEqual(screen_track(row), screen_track(row))
        self.assertNotEqual(screen_track(row).occasion_decision_version,
                            screen_track(track("A Christmas Song")).occasion_decision_version)


if __name__ == "__main__":
    unittest.main()
