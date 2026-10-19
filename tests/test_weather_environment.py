"""기상청 호출 없이 로컬 키 파일의 위치·환경 우선순위를 확인합니다."""
from contextlib import contextmanager
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pipeline.weather import collect


class WeatherEnvironmentTests(unittest.TestCase):
    @contextmanager
    def key_file(self, text):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '.env'
            path.write_text(text, encoding='utf-8-sig')
            with patch.object(collect, 'ENV_PATH', path):
                yield Path(directory)

    def test_service_environment_wins_over_file(self):
        with self.key_file('KMA_API_KEY=file-test-key'), patch.dict(os.environ, {'KMA_API_KEY': 'service-test-key'}):
            self.assertEqual(collect.configured_key(), 'service-test-key')
        with self.key_file('KMA_API_KEY=file-test-key'), patch.dict(os.environ, {'KMA_API_KEY': ''}):
            self.assertEqual(collect.configured_key(), '')

    def test_file_is_independent_of_current_directory_and_not_executed(self):
        with self.key_file('OTHER_SETTING=not-loaded\nexport KMA_API_KEY="file-test-key" # local\n') as directory:
            original = Path.cwd()
            with patch.dict(os.environ, {}, clear=True):
                try:
                    os.chdir(directory.parent)
                    self.assertEqual(collect.configured_key(), 'file-test-key')
                    self.assertNotIn('OTHER_SETTING', os.environ)
                    self.assertNotIn('KMA_API_KEY', os.environ)
                finally:
                    os.chdir(original)

    def test_invalid_assignment_does_not_echo_file_content(self):
        with self.key_file('KMA_API_KEY="private-test-marker'), patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, '^invalid_KMA_API_KEY_assignment$'):
                collect.configured_key()

    def test_missing_file_has_no_key(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            with patch.object(collect, 'ENV_PATH', Path(directory) / 'absent.env'):
                self.assertEqual(collect.configured_key(), '')


if __name__ == '__main__':
    unittest.main()
