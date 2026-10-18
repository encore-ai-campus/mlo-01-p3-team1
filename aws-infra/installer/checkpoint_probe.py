"""Sequential synthetic S3A checkpoint/restart probe, not a fencing test.

Run explicitly with the verified Spark runtime and reviewed Kafka/S3A lock.
Requires AWS identity/disk checks and workload exclusion in the SSM launcher.
Retains its unique test prefix as evidence; never resets or deletes checkpoints.
"""
import argparse
import json
import importlib.util
import platform
from pathlib import Path
from integration_scope import checkpoint_paths


def probe(spark, paths):
    jvm = spark.sparkContext._jvm
    conf = spark.sparkContext._jsc.hadoopConfiguration()
    def target(uri):
        path = jvm.org.apache.hadoop.fs.Path(uri)
        return path, path.getFileSystem(conf)
    for uri in paths.values():
        path, fs = target(uri)
        if fs.exists(path): raise ValueError('Test prefix already exists; preserve evidence and choose a reviewed new run ID')
    def add_input(name, first):
        path, fs = target(paths['input'] + '/' + name + '.json')
        stream = fs.create(path, False)
        writer = jvm.java.io.OutputStreamWriter(stream, 'UTF-8')
        try:
            for value in range(first, first + 9): writer.write(json.dumps({'id': value}) + '\n')
        finally: writer.close()
    def consume():
        query = (spark.readStream.schema('id LONG').json(paths['input']).writeStream
                 .format('parquet').option('checkpointLocation', paths['checkpoint'])
                 .option('path', paths['output']).trigger(availableNow=True).start())
        try:
            if not query.awaitTermination(180): raise ValueError('Checkpoint probe did not finish in time')
            if query.exception() is not None: raise ValueError('Checkpoint stream failed')
            return str(query.id), str(query.runId)
        finally:
            if query.isActive: query.stop()
    add_input('first', 0);query_id, first_run = consume()
    add_input('second', 9);resumed_id, second_run = consume()
    if resumed_id != query_id or second_run == first_run:
        raise ValueError('Streaming query identity did not resume from its checkpoint')
    ids = [r.id for r in spark.read.parquet(paths['output']).select('id').limit(19).collect()]
    if len(ids) != 18 or set(ids) != set(range(18)):
        raise ValueError('Checkpoint restart duplicated or lost synthetic rows')
    return {'synthetic_rows': 18, 'same_query_id': True, 'new_run_id': True,
            'checkpoint_reused_without_reset': True, 'concurrent_writer_fencing_verified': False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runtime', required=True);p.add_argument('--run-id', required=True)
    args = p.parse_args();runtime = json.loads(Path(args.runtime).read_text())
    paths = checkpoint_paths(runtime, args.run_id)
    if platform.system() != 'Linux' or runtime['node']['role'] != 'spark':
        raise ValueError('Explicit Spark EC2 probe required')
    spec = importlib.util.spec_from_file_location('probe_aws_identity', Path(__file__).with_name('aws-identity.py'))
    identity = importlib.util.module_from_spec(spec);spec.loader.exec_module(identity)
    identity.verify(runtime, identity.identity)
    from pyspark.sql import SparkSession
    spark = SparkSession.builder.appName('infra-checkpoint-probe-' + args.run_id).getOrCreate()
    try:
        spark.sparkContext._jsc.hadoopConfiguration().set('fs.s3a.endpoint.region', runtime['env']['AWS_REGION'])
        print(json.dumps(probe(spark, paths)))
    finally: spark.stop()


if __name__ == '__main__': main()
