"""이동한 날씨 모듈의 자원·Spark 배포 패키지를 외부 서비스 없이 검증합니다."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

from pipeline.weather import service_view
from pipeline.weather.submit_spark import build_package
from pipeline.weather.weather_normalize import normalize_value


class WeatherLayoutTests(unittest.TestCase):
    def test_resources_and_zero_missing_semantics_survive_move(self):
        config = service_view.config()
        self.assertIn('forecast_max_age_minutes', config)
        zero = normalize_value('RN1', '0', 'odam', 'observation')
        missing = normalize_value('RN1', '-99', 'odam', 'observation')
        self.assertEqual((zero['status'], zero['value']), ('valid', 0))
        self.assertEqual((missing['status'], missing['value']), ('missing', None))

    def test_spark_archive_can_import_weather_without_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = build_package(Path(directory) / 'weather.zip')
            with zipfile.ZipFile(archive) as package:
                names = package.namelist()
                self.assertIn('pipeline/__init__.py', names)
                self.assertIn('pipeline/weather/spark_job.py', names)
                self.assertIn('pipeline/weather/mapping.json', names)
                self.assertIn('pipeline/weather/mapping_postgres.sql', names)
                self.assertTrue(all(name.startswith('pipeline/') for name in names))
                self.assertFalse(any('.env' in name or 'runtime/' in name or 'backend/' in name for name in names))
            code = '''import json, sys
sys.path.insert(0, sys.argv[1])
from importlib.resources import files
from pipeline.weather.service_view import config
mapping = json.loads(files('pipeline.weather').joinpath('mapping.json').read_text(encoding='utf-8'))
assert mapping['grids']
assert config()['forecast_max_age_minutes'] > 0
print('weather-archive-ok')
'''
            result = subprocess.run([sys.executable, '-I', '-c', code, str(archive)],
                                    cwd=directory, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), 'weather-archive-ok')


if __name__ == '__main__':
    unittest.main()
