import copy
from datetime import datetime, timezone
import unittest
from unittest.mock import patch
import dashboard_guest_v1 as dashboard
import guest_behavior_export as exporter
from guest_behavior_elastic_plan import EVENT_PROPERTIES


class GuestBehaviorTests(unittest.TestCase):
    def test_numeric_terms_do_not_use_string_missing(self):
        for field in ['hour_kst', 'weekday_kst']:
            spec = dashboard.group_chart('t', 'd', field)
            terms = spec['data']['url']['body']['aggs']['rows']['terms']
            self.assertNotIn('missing', terms)
            self.assertEqual(terms['order'], {'_key': 'asc'})

    def test_export_is_allowlist_and_mapping_compatible(self):
        row = {'event_id': 'private-event', 'event_type': 'TRACK_REACTION_CHANGED',
               'occurred_at': datetime(2026, 10, 18, 23, tzinfo=timezone.utc),
               'source_playlist_id': 'private-playlist', 'track_id': 'private-track',
               'payload': {'owner_id': 'private-owner', 'cookie': 'secret',
                           'new_value': 'LIKE', 'previous_value': 'DISLIKE',
                           'track_snapshot': {'track_name': '<song>', 'genre_group_codes': ['JAZZ']},
                           'context_snapshot': {'options': {'weather_influence_mode': 'ON'}}}}
        value = exporter.normalize_event(row)
        self.assertEqual(value['action'], 'LIKE')
        self.assertEqual(value['hour_kst'], 8)
        self.assertEqual(value['transition'], 'DISLIKE_TO_LIKE')
        self.assertTrue(set(value) <= set(EVENT_PROPERTIES))
        serialized = str(value)
        for private in ['private-event', 'private-playlist', 'private-track', 'private-owner', 'secret']:
            self.assertNotIn(private, serialized)

    def test_cleared_rating_does_not_contribute_current_mean(self):
        rows = [{'target_kind': 'PLAYLIST', 'value': None, 'last_event_id': 'a', 'playlist_id': 'p'},
                {'target_kind': 'PLAYLIST', 'value': 4, 'last_event_id': 'b', 'playlist_id': 'q'}]
        value = exporter.normalize_current_state(rows, {'a': {}, 'b': {'is_test': False, 'payload': {}}})
        self.assertEqual(value['current_rating_count'], 1)
        self.assertEqual(value['current_rating_mean'], 4)

    def test_collision_preflight_does_not_write_partial_dashboard(self):
        class Client:
            def get(self, kind, key):
                return {'version': 'x'} if kind == 'dashboard' else None
            def request(self, *args):
                raise AssertionError('must not write before checking every identity')
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(RuntimeError, 'not_owned_or_changed'):
                dashboard.publish(Client(), folder, dry_run=False)


if __name__ == '__main__':
    unittest.main()
