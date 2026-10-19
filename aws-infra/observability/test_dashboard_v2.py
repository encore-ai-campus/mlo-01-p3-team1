"""Protect other editors and prevent accidental overlapping dashboard panels."""
import json
from pathlib import Path
import tempfile
import unittest

import dashboard_v2 as dashboard


class NoWriteClient:
    def __init__(self, version):
        self.version = version
        self.writes = []

    def get(self, kind, identity):
        return {'version': self.version, 'attributes': {}, 'references': []}

    def request(self, *args):
        self.writes.append(args)
        raise AssertionError('concurrent edit must be detected before mutation')


class DashboardEditorSafety(unittest.TestCase):
    def test_live_dashboard_edit_aborts_before_any_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            (state/'dashboard-before.json').write_text(json.dumps({'version': 'reviewed-version'}))
            client = NoWriteClient('another-editors-version')
            with self.assertRaisesRegex(RuntimeError, 'existing_dashboard_changed_by_another_editor'):
                dashboard.publish(client, state, preview=False)
            self.assertEqual(client.writes, [])

    def test_owned_visualization_edit_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            key = 'visualization/'+dashboard.PREFIX+'hero'
            (state/'v2-published-ledger.json').write_text(json.dumps({key: {'version': 'our-last-version'}}))
            client = NoWriteClient('someone-elses-version')
            with self.assertRaisesRegex(RuntimeError, 'object_changed_by_another_editor'):
                dashboard.publish(client, state, preview=True)
            self.assertEqual(client.writes, [])

    def test_no_grid_overlap_or_offscreen_cards(self):
        panels = dashboard.definitions()
        for i, panel in enumerate(panels):
            a = panel['grid']
            self.assertGreater(a['w'], 0)
            self.assertGreater(a['h'], 0)
            self.assertLessEqual(a['x']+a['w'], 48)
            for other in panels[i+1:]:
                b = other['grid']
                overlap = (a['x'] < b['x']+b['w'] and a['x']+a['w'] > b['x']
                           and a['y'] < b['y']+b['h'] and a['y']+a['h'] > b['y'])
                self.assertFalse(overlap, panel['key']+' overlaps '+other['key'])

    def test_server_error_top_ten_uses_selected_time_range(self):
        panel = next(p for p in dashboard.definitions() if p['key'] == 'service-state')
        self.assertEqual(panel['title'], '서버별 오류 TOP 10')
        spec = panel['spec']
        self.assertEqual(spec['data']['url']['index'], 'ops-mlo-*')
        body = spec['data']['url']['body']
        self.assertEqual(body['aggs']['rows']['terms'],
                         {'field': 'host.name', 'size': 10, 'order': {'_count': 'desc'}})
        self.assertIn({'terms': {'log.level': dashboard.ERRORS}},
                      body['query']['bool']['filter'])
        self.assertIn({'range': {'@timestamp': {'%timefilter%': True}}},
                      body['query']['bool']['filter'])
        self.assertEqual(spec['layer'][0]['encoding']['y']['axis']['labelAngle'], 0)


if __name__ == '__main__':
    unittest.main()
