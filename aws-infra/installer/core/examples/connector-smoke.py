"""Run with spark-submit after frozen JAR installation and Kafka catalog creation."""
import argparse
import json
from pathlib import Path
from pyspark.sql import SparkSession

p = argparse.ArgumentParser()
p.add_argument('mode', choices=('kafka', 's3a', 'elasticsearch'))
p.add_argument('--topic', default='weather.v1')
a = p.parse_args()
if a.mode == 'elasticsearch':
    raise SystemExit('BLOCKED: Spark 4.1 ES connector release/server compatibility is not verified')
c = json.loads(Path('/etc/music-cluster/spark/pipeline.json').read_text())
e, d = c['env'], c['derived']
spark = SparkSession.builder.appName('music-connector-smoke-' + a.mode).getOrCreate()
try:
    if a.mode == 'kafka':
        # Read-only against an explicitly selected existing topic; no test records pollute weather data.
        reader = spark.read.format('kafka')
        options = {'kafka.bootstrap.servers': d['kafka_bootstrap'], 'subscribe': a.topic,
                   'startingOffsets': 'earliest', 'endingOffsets': 'latest',
                   'kafka.security.protocol': 'SASL_SSL', 'kafka.sasl.mechanism': 'PLAIN',
                   'kafka.sasl.jaas.config': 'org.apache.kafka.common.security.plain.PlainLoginModule required '
                                             f'username="pipeline" password="{e["KAFKA_PIPELINE_PASSWORD"]}";',
                   'kafka.ssl.truststore.type': 'PKCS12',
                   'kafka.ssl.truststore.location': '/etc/music-cluster/spark/tls/trust.p12',
                   'kafka.ssl.truststore.password': e['TLS_STORE_PASSWORD']}
        for key, value in options.items(): reader = reader.option(key, value)
        reader.load().select('topic', 'partition', 'offset').limit(10).collect()
        print('[PASS] Spark Kafka connector metadata and bounded read')
    else:
        from uuid import uuid4
        region, bucket, prefix = e.get('AWS_REGION', ''), e.get('S3_BUCKET', ''), e.get('S3_CHECKPOINT_PREFIX', '')
        if not region or not bucket or region.startswith('REPLACE') or bucket.startswith('REPLACE') or e['ENVIRONMENT'] not in prefix.split('/'):
            raise ValueError('Fill environment-separated S3 settings and provision credentials to Driver and Workers')
        spark.sparkContext._jsc.hadoopConfiguration().set('fs.s3a.endpoint.region', region)
        path = 's3a://' + bucket + '/' + prefix.strip('/') + '/_smoke/' + uuid4().hex
        jvm = spark.sparkContext._jvm
        target = jvm.org.apache.hadoop.fs.Path(path)
        fs = target.getFileSystem(spark.sparkContext._jsc.hadoopConfiguration())
        try:
            spark.range(100, numPartitions=3).write.mode('error').parquet(path)
            assert spark.read.parquet(path).count() == 100
            print('[PASS] Spark S3A distributed write/read')
        finally:
            fs.delete(target, True)
        print('This probe does not claim Structured Streaming checkpoint recovery or Driver HA has passed.')
finally:
    spark.stop()
