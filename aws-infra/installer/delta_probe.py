#!/usr/bin/env python3
"""Bounded synthetic S3 Delta acceptance; one foreground Driver at a time."""
from pathlib import Path
import hashlib
import json
import re
import sys
from pyspark.sql import SparkSession


def main():
    cfg = json.loads(Path(sys.argv[1]).read_text());phase = sys.argv[2]
    if phase not in ('batch', 'stream-first', 'stream-resume', 'stream-retry'): raise ValueError('Explicit bounded test phase required')
    if (not re.fullmatch(r'[0-9a-f]{16}', cfg['test_id']) or
        cfg['prefix'] != cfg['root_prefix'].rstrip('/') + '/_infra-tests/delta-' + cfg['test_id'] or
        cfg['root_prefix'].split('/')[:3] != ['aws', cfg['environment'], cfg['generation']]):
        raise ValueError('Only the current generation isolated Delta test prefix is allowed')
    local = Path(cfg['local']);local.mkdir(parents=True, exist_ok=True, mode=0o700)
    result_path = local / (phase + '-proof.json')
    if result_path.exists(): raise ValueError('Phase evidence exists; inspect it instead of resetting/replaying')
    spark = SparkSession.builder.appName('infra-delta-' + cfg['test_id'] + '-' + phase).getOrCreate()
    try:
        spark.sparkContext.setLogLevel('WARN');jvm = spark.sparkContext._jvm;hadoop = spark.sparkContext._jsc.hadoopConfiguration()
        hadoop.set('fs.s3a.endpoint.region', 'ap-northeast-2');hadoop.set('fs.s3a.connection.ssl.enabled', 'true')
        base = 's3a://' + cfg['bucket'] + '/' + cfg['prefix']
        def target(uri):
            path = jvm.org.apache.hadoop.fs.Path(uri);return path, path.getFileSystem(hadoop)
        def exists(uri):
            path, fs = target(uri);return fs.exists(path)
        def put(uri, text):
            path, fs = target(uri)
            if fs.exists(path): raise ValueError('Synthetic input exists; no overwrite/reset')
            writer = jvm.java.io.OutputStreamWriter(fs.create(path, False), 'UTF-8')
            try: writer.write(text)
            finally: writer.close()
        def read(uri):
            path, fs = target(uri);stream = fs.open(path)
            try: return bytes(jvm.org.apache.commons.io.IOUtils.toByteArray(stream))
            finally: stream.close()
        def values(uri):
            rows = spark.read.format('delta').load(uri).select('id', 'score').collect()
            result = {r.id: r.score for r in rows}
            if len(rows) != len(result): raise ValueError('Duplicate synthetic IDs')
            return result
        if phase == 'batch':
            if exists(base): raise ValueError('Use a new isolated test prefix; never reset an old one')
            table = base + '/batch';identifier = 'delta.`' + table + '`'
            spark.range(0, 9).selectExpr('id', 'id * 10 AS score').write.format('delta').save(table)
            spark.range(9, 18).selectExpr('id', 'id * 10 AS score').write.format('delta').mode('append').save(table)
            spark.sql('UPDATE ' + identifier + ' SET score=999 WHERE id=0')
            spark.sql('MERGE INTO ' + identifier + ' AS target USING (SELECT CAST(1 AS BIGINT) AS id, CAST(111 AS BIGINT) AS score UNION ALL SELECT CAST(18 AS BIGINT),CAST(180 AS BIGINT)) AS source ON target.id=source.id WHEN MATCHED THEN UPDATE SET score=source.score WHEN NOT MATCHED THEN INSERT (id,score) VALUES(source.id,source.score)')
            spark.sql('DELETE FROM ' + identifier + ' WHERE id=2')
            expected = {i: i * 10 for i in range(19) if i != 2};expected.update({0: 999, 1: 111})
            if values(table) != expected: raise ValueError('Delta batch transaction mismatch')
            old = {r.id: r.score for r in spark.read.format('delta').option('versionAsOf', 0).load(table).collect()}
            if old != {i: i * 10 for i in range(9)}: raise ValueError('Version-zero snapshot changed')
            versions = [r.version for r in spark.sql('DESCRIBE HISTORY ' + identifier).select('version').collect()]
            if sorted(versions) != list(range(5)): raise ValueError('Expected five committed transaction versions')
            rejected = False
            try: spark.range(99, 100).selectExpr('id', "'invalid' AS unexpected").write.format('delta').mode('append').save(table)
            except Exception as error:
                if type(error).__name__ not in ('AnalysisException', 'CapturedException'): raise
                rejected = True
            if not rejected or values(table) != expected: raise ValueError('Schema mismatch was not safely rejected')
            def host_partition(items):
                import socket, time
                count = sum(1 for _ in items);time.sleep(2);yield (socket.gethostname(), count)
            workers = sorted({r[0] for r in spark.sparkContext.parallelize(range(30), 3).mapPartitions(host_partition).collect()})
            if len(workers) != 3: raise ValueError('All three distributed Worker hosts must execute the probe')
            report = {'phase': phase, 'batch_operations': ['create', 'append', 'update', 'merge', 'delete'], 'versions': 5,
                      'rows': 18, 'unique_rows': 18, 'time_travel_verified': True, 'schema_mismatch_rejected': True, 'worker_hosts': workers}
        else:
            table, inputs, checkpoint = [base + '/stream/' + key for key in ('table', 'input', 'checkpoint')]
            if phase == 'stream-first':
                if exists(base + '/stream'): raise ValueError('Existing streaming scope cannot be initialized')
                put(inputs + '/first.json', ''.join(json.dumps({'id': i, 'score': i * 10}) + '\n' for i in range(9)))
            else:
                if not exists(checkpoint + '/commits/0'): raise ValueError('Durable previous checkpoint required')
                if phase == 'stream-resume': put(inputs + '/second.json', ''.join(json.dumps({'id': i, 'score': i * 10}) + '\n' for i in range(9, 18)))
            old_metadata = read(checkpoint + '/metadata') if exists(checkpoint + '/metadata') else None
            query = (spark.readStream.schema('id LONG,score LONG').json(inputs).repartition(3).writeStream.format('delta')
                     .outputMode('append').option('checkpointLocation', checkpoint).trigger(availableNow=True).start(table))
            if not query.awaitTermination(240) or query.exception() is not None: raise ValueError('Bounded Delta stream failed')
            count = 9 if phase == 'stream-first' else 18
            if values(table) != {i: i * 10 for i in range(count)}: raise ValueError('Streaming rows were duplicated or lost')
            metadata = read(checkpoint + '/metadata')
            if json.loads(metadata)['id'] != str(query.id) or old_metadata is not None and metadata != old_metadata:
                raise ValueError('Checkpoint metadata/query ID changed')
            report = {'phase': phase, 'rows': count, 'unique_rows': count, 'query_id': str(query.id), 'run_id': str(query.runId),
                      'checkpoint_metadata_sha256': hashlib.sha256(metadata).hexdigest(), 'checkpoint_reset': False}
        report.update(application_id=spark.sparkContext.applicationId, spark_version=spark.version, delta_version='4.3.1',
                      s3_log_store='S3SingleDriverLogStore', scope='One Driver at a time; no concurrent multi-Driver or business application guarantee')
        result_path.write_text(json.dumps(report, indent=2) + '\n');result_path.chmod(0o600)
        print(json.dumps({'phase': phase, 'passed': True, 'rows': report['rows']}))
    finally: spark.stop()


if __name__ == '__main__': main()
