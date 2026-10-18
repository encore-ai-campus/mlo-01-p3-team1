import copy
import io
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pipeline import environment
from pipeline.weather import prepare_es
from scripts.runtime import plans, cross_configuration


class RuntimeConfigurationTests(unittest.TestCase):
    def test_cross_service_mismatch_is_detected_without_exposing_secret(self):
        import os
        import scripts.runtime as runtime
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            files={'backend/.env':'C_LOCAL_DEMO=0\nDJANGO_SECRET_KEY=test\nPGHOST=db\nPGDATABASE=cafe\nPGUSER=user\nADS_INTERNAL_SECRET=shared-secret\nES_URL=https://es\nWEATHER_INDEX=current\n',
                   'pipeline/weather/.env':'KMA_API_KEY=test\nKAFKA_BOOTSTRAP=broker\nKAFKA_TOPIC=weather\nES_URL=https://es\nWEATHER_INDEX=current\nSPARK_MASTER=spark://master\nCHECKPOINT_PATH=/checkpoint\nPGHOST=db\nPGDATABASE=cafe\nPGUSER=user\n',
                   'ad-server/backend/.env':'DJANGO_SECRET_KEY=test\nPOSTGRES_HOST=db\nPOSTGRES_DB=cafe\nPOSTGRES_USER=user\nADS_IS_TEST=0\nADS_MONGODB_URI=mongodb://configured\nADS_MONGODB_DATABASE=ads\nADS_COMMON_API_URL=https://common\nADS_INTERNAL_SECRET=shared-secret\n',
                   'frontend/.env.local':'VITE_C_DEMO=0\nVITE_RECOMMENDATION_API_TARGET=https://common\nVITE_ADS_API_TARGET=https://ads\n'}
            for name,text in files.items():
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf8')
            with patch.object(runtime,'ROOT',root),patch.dict(os.environ,{},clear=True):
                self.assertTrue(all(cross_configuration().values()))
                (root/'ad-server/backend/.env').write_text(files['ad-server/backend/.env'].replace('shared-secret','other-secret'),encoding='utf8')
                report=cross_configuration()
                self.assertFalse(report['shared_ads_secret_matches'])
                self.assertNotIn('shared-secret',str(report));self.assertNotIn('other-secret',str(report))

    def test_existing_kafka_topic_is_preserved_without_creation(self):
        from pipeline.prepare_kafka import ensure_topic
        from unittest.mock import MagicMock
        import os
        client=MagicMock();client.list_topics.return_value=['feedback']
        with patch.dict(os.environ,{'FEEDBACK_KAFKA_BOOTSTRAP':'configured','FEEDBACK_KAFKA_TOPIC':'feedback'}),patch('kafka.admin.KafkaAdminClient',return_value=client):
            self.assertEqual(ensure_topic('FEEDBACK_KAFKA_'),{'created':False})
        client.create_topics.assert_not_called();client.close.assert_called_once()

    def test_new_kafka_topic_requires_explicit_counts(self):
        from pipeline.prepare_kafka import ensure_topic
        from unittest.mock import MagicMock
        import os
        client=MagicMock();client.list_topics.return_value=[]
        env={'KAFKA_BOOTSTRAP':'configured','KAFKA_TOPIC':'weather','KAFKA_TOPIC_PARTITIONS':'','KAFKA_REPLICATION_FACTOR':''}
        with patch.dict(os.environ,env),patch('kafka.admin.KafkaAdminClient',return_value=client):
            with self.assertRaisesRegex(RuntimeError,'counts_required'):ensure_topic('KAFKA_')
        client.create_topics.assert_not_called();client.close.assert_called_once()

    def test_env_precedence_allowlist_empty_and_no_expansion(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'.env.example').write_text('PGHOST=\nPGPASSWORD=\nSEARCH_SECONDS=\n',encoding='utf8')
            (root/'.env').write_text('PGHOST=file-host\nPGPASSWORD="$(do-not-run)${SECRET}"\nSEARCH_SECONDS=\nPYTHONPATH=untrusted\n',encoding='utf8')
            target={'PGHOST':'process-host'}
            with patch.dict(environment.SERVICES,{'common':root}):environment.load('common',target)
            self.assertEqual(target,{'PGHOST':'process-host','PGPASSWORD':'$(do-not-run)${SECRET}'})

    def test_malformed_env_reports_line_without_secret(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'.env';path.write_text('INVALID secret-value',encoding='utf8')
            with self.assertRaisesRegex(ValueError,'env_format_line_1') as error:environment.read(path)
            self.assertNotIn('secret-value',str(error.exception))

    def test_plan_uses_interpreter_config_and_explicit_write_flag(self):
        config={'COMMON_PYTHON':'/opt/common python','ADS_PYTHON':'/opt/ads python'}
        dry=plans(config,'prepare');active=plans(config,'prepare',apply=True,music=True)
        self.assertEqual(dry['common'][0][0],'/opt/common python')
        self.assertEqual(dry['ads'][0][0],'/opt/ads python')
        self.assertTrue(all('--apply' not in cmd for cmd,_ in dry.values()))
        self.assertTrue(all('--apply' in cmd for cmd,_ in active.values()))
        self.assertIn('--music',active['common'][0])
        self.assertFalse(any('password' in arg.lower() for cmd,_ in active.values() for arg in cmd))

    def test_existing_weather_index_is_idempotent_and_not_overwritten(self):
        existing={'current':copy.deepcopy(prepare_es.MAPPING)}
        with patch.object(prepare_es,'configuration',return_value=('https://es','current')),patch.object(prepare_es,'request',return_value=existing) as request,redirect_stdout(io.StringIO()):
            prepare_es.ensure_index();prepare_es.ensure_index()
        self.assertEqual([call.args[1] for call in request.call_args_list],['GET','GET'])

    def test_incompatible_weather_index_fails_without_write(self):
        with patch.object(prepare_es,'configuration',return_value=('https://es','current')),patch.object(prepare_es,'request',return_value={'current':{'mappings':{}}}) as request:
            with self.assertRaisesRegex(RuntimeError,'incompatible'):prepare_es.ensure_index()
        request.assert_called_once_with('https://es','GET','/current')


if __name__=='__main__':unittest.main()
