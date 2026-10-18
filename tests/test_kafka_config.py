import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from pipeline.kafka_config import python_options,spark_options


class KafkaConfigurationTests(unittest.TestCase):
    def test_python_sasl_requires_tls_and_complete_identity(self):
        with patch.dict(os.environ,{'KAFKA_SECURITY_PROTOCOL':'SASL_SSL','KAFKA_SASL_USERNAME':'test-user','KAFKA_SASL_PASSWORD':'test-only'}):
            options=python_options();self.assertEqual(options['security_protocol'],'SASL_SSL')
            self.assertEqual(options['sasl_plain_username'],'test-user')
        with patch.dict(os.environ,{'KAFKA_SECURITY_PROTOCOL':'PLAINTEXT','KAFKA_SASL_USERNAME':'test-user','KAFKA_SASL_PASSWORD':'test-only'}):
            with self.assertRaises(ValueError):python_options()

    def test_spark_allows_only_private_security_options_and_hostname_verification(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            path=Path(directory)/'kafka.json'
            with patch.dict(os.environ,{'TEST_KAFKA_OPTIONS_FILE':str(path)}):
                path.write_text(json.dumps({'kafka.security.protocol':'SASL_SSL','kafka.sasl.jaas.config':'test-only'}))
                self.assertEqual(spark_options('TEST_KAFKA_OPTIONS_FILE')['kafka.ssl.endpoint.identification.algorithm'],'https')
                path.write_text(json.dumps({'kafka.security.protocol':'SASL_SSL','kafka.ssl.endpoint.identification.algorithm':''}))
                with self.assertRaises(ValueError):spark_options('TEST_KAFKA_OPTIONS_FILE')
                path.write_text(json.dumps({'kafka.security.protocol':'SSL','subscribe':'different-topic'}))
                with self.assertRaises(ValueError):spark_options('TEST_KAFKA_OPTIONS_FILE')
