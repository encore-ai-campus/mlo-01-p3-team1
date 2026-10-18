"""Spark driver에서 동일한 PostgreSQL 원본/정제 함수를 사용합니다. Kafka consumer와 택일."""
import json
import os
from pipeline.feedback.process import setup,apply_record
from pipeline.kafka_config import spark_options


def main():
    setup()
    from pyspark.sql import SparkSession
    required=['FEEDBACK_KAFKA_BOOTSTRAP','FEEDBACK_KAFKA_TOPIC','FEEDBACK_CHECKPOINT_PATH']
    if not all(os.environ.get(k) for k in required):raise RuntimeError('feedback_spark_configuration_required')
    spark=(SparkSession.builder.appName('feedback-postgresql')
           .config('spark.redaction.regex','(?i)secret|password|token|access[.]key|jaas').getOrCreate())
    reader=(spark.readStream.format('kafka').option('kafka.bootstrap.servers',os.environ[required[0]])
            .option('subscribe',os.environ[required[1]]).option('startingOffsets','earliest'))
    for key,value in spark_options('FEEDBACK_KAFKA_OPTIONS_FILE').items():reader=reader.option(key,value)
    rows=reader.load().selectExpr('CAST(value AS STRING) AS value','topic','partition','offset')
    def save(batch,batch_id):
        for row in batch.toLocalIterator():apply_record(json.loads(row.value),row.topic,row.partition,row.offset)
    query=(rows.writeStream.foreachBatch(save).option('checkpointLocation',os.environ[required[2]]).start())
    try:query.awaitTermination()
    finally:spark.stop()


if __name__=='__main__':main()
