"""Django test runner로 실제 날씨 provider의 출처·시각·NULL/만료를 검증."""
from datetime import datetime, timedelta
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from backend.recommendation.errors import DomainError
from backend.weather import live
from pipeline.weather.common import KST
from pipeline.weather.live_cache import identity, plan

NOW = datetime(2026, 10, 16, 12, 10, tzinfo=KST)
REGION = 'region:1211051000'


def fixture():
    slots = {}
    for job in plan(NOW):
        params = job['params']
        issued = datetime.strptime(params['tmfc'], '%Y%m%d%H%M').replace(tzinfo=KST)
        target = (datetime.strptime(params['tmef'], '%Y%m%d%H').replace(tzinfo=KST)
                  if 'tmef' in params else issued)
        value = {'PTY': '0.00', 'SKY': '3.00', 'T1H': '22.90'}[job['category']]
        slots[identity(job)] = {'source': job['source'], 'category': job['category'],
            'issued_at': issued.isoformat(), 'target_at': target.isoformat(),
            'received_at': (issued + timedelta(minutes=5)).isoformat(),
            'source_hash': 'unit-test-only', 'values': [value] * 37697}
    return {'schema_version': 1, 'slots': slots, 'updated_at': NOW.isoformat()}


@override_settings(LOCAL_DEMO=True)
class LiveWeatherTests(SimpleTestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / 'cache.json'

    def display(self, data, at=NOW):
        self.path.write_text(json.dumps(data), encoding='utf-8')
        with override_settings(KMA_LOCAL_CACHE_PATH=str(self.path)), patch('requests.get') as network:
            result = live.display(REGION, at)
            network.assert_not_called()
            return result

    def test_received_values_and_source_times_are_preserved(self):
        result = self.display(fixture())
        self.assertFalse(result['is_test'])
        self.assertNotEqual(result['bundle_version'], 'demo-weather-v1')
        self.assertEqual(result['current']['temperature'], 22.9)
        self.assertEqual(result['current']['sky'], 3)
        self.assertEqual(result['weather_code'], 'CLOUDY')
        self.assertEqual(result['current']['observed_at'], '2026-10-16T03:00:00Z')
        self.assertTrue(result['recommendation_ready'])

    def test_stale_measurements_do_not_become_fresh_on_query(self):
        result = self.display(fixture(), NOW + timedelta(hours=3))
        self.assertEqual(result['current']['status'], 'stale')
        self.assertEqual(result['current']['observed_at'], '2026-10-16T03:00:00Z')
        self.assertFalse(result['recommendation_ready'])

    def test_missing_pty_is_not_converted_to_clear(self):
        data = fixture()
        for slot in data['slots'].values():
            if slot['source'] == 'odam' and slot['category'] == 'PTY':
                slot['values'] = ['-99'] * 37697
        result = self.display(data)
        self.assertIsNone(result['current']['pty'])
        self.assertFalse(result['recommendation_ready'])

    def test_missing_cache_fails_without_demo_or_http_fallback(self):
        with override_settings(KMA_LOCAL_CACHE_PATH=str(self.path)), patch('requests.get') as network:
            with self.assertRaises(DomainError):
                live.display(REGION, NOW)
            network.assert_not_called()

    def test_partial_forecast_preserves_actual_current_display_but_blocks_recommendation(self):
        data = fixture()
        remove = next(key for key, slot in data['slots'].items()
                      if slot['source'] == 'vsrt' and slot['category'] == 'T1H')
        del data['slots'][remove]
        result = self.display(data)
        self.assertEqual(result['current']['temperature'], 22.9)
        self.assertFalse(result['is_test'])
        self.assertFalse(result['recommendation_ready'])

    def test_current_hour_sky_is_collected_separately_after_forecast_rollover(self):
        jobs = plan(NOW.replace(minute=55))
        current = [job for job in jobs if job['category'] == 'SKY' and job['params'].get('tmef') == '2026101612']
        self.assertEqual(len(current), 1)
        self.assertEqual(current[0]['params']['tmfc'], '202610161130')
