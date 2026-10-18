import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from pipeline.weather.submit_spark import connector_arguments, runtime_arguments


class ConnectorLockTests(unittest.TestCase):
    def test_only_reviewed_fleet_jars_can_be_used_without_maven(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);jars=root/'jars';jars.mkdir()
            entries=[]
            for name in ['spark-core_2.13-4.1.3.jar','spark-sql-kafka-0-10_2.13-4.1.3.jar']:
                (jars/name).write_bytes(name.encode())
                entries.append({'filename':name,'sha256':hashlib.sha256(name.encode()).hexdigest()})
            lock=root/'lock.json';lock.write_text(json.dumps({'schema_version':2,'spark_version':'4.1.3','hadoop_version':'3.4.2',
                'coordinates':['org.apache.spark:spark-sql-kafka-0-10_2.13:4.1.3'],'distribution_jars':entries[:1],'jars':entries[1:]}))
            with patch.dict(os.environ,{'SPARK_HOME':str(root),'SPARK_CONNECTOR_LOCK':str(lock),'SPARK_KAFKA_PACKAGE':''}):
                self.assertEqual(connector_arguments(),[])
                (jars/'unreviewed.jar').write_bytes(b'bad')
                with self.assertRaisesRegex(RuntimeError,'unreviewed'):connector_arguments()
                (jars/'unreviewed.jar').unlink()
                (jars/entries[1]['filename']).write_bytes(b'tampered')
                with self.assertRaisesRegex(RuntimeError,'checksum'):connector_arguments()

    def test_missing_lock_is_not_resolved_from_network(self):
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaisesRegex(RuntimeError,'required'):connector_arguments()

    def test_missing_or_unauthenticated_runtime_cannot_fall_back_to_spark_defaults(self):
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'SPARK_CONF_DIR':folder}):
            with self.assertRaisesRegex(RuntimeError,'unreadable'):runtime_arguments()
            path=Path(folder)/'spark-defaults.conf'
            path.write_text('spark.authenticate false\n')
            with self.assertRaisesRegex(RuntimeError,'authenticated'):runtime_arguments()
            path.write_text('spark.authenticate true\nspark.authenticate.secret test-only\nspark.network.crypto.enabled true\n')
            self.assertEqual(runtime_arguments(),['--properties-file',str(path)])
