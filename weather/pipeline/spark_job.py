"""Kafka → Spark 격자 선택·정규화 → MongoDB. ES는 별도 발행."""
import json
import os
from datetime import datetime, timezone
from importlib.resources import files
from pyspark.sql import SparkSession
from weather.pipeline.mongo_current import write_batch
from weather.pipeline.collection_logs import append, flush_if_configured

def main():
    for name in ('KAFKA_BOOTSTRAP', 'WEATHER_MONGODB_WRITE_URI', 'WEATHER_MONGODB_DATABASE', 'WEATHER_MONGODB_COLLECTION', 'CHECKPOINT_PATH'):
        if not os.environ.get(name):
            raise RuntimeError(name + '_missing')
    mapping = json.loads(files('weather.pipeline').joinpath('mapping.json').read_text(encoding='utf-8'))
    spark = SparkSession.builder.appName('weather-stream').getOrCreate()
    spark.sparkContext.setLogLevel('WARN')
    grids = spark.sparkContext.broadcast({
        (g['nx'], g['ny']): g for g in mapping['grids'] + mapping.get('admin_grids', [])
    })
    stream = (spark.readStream.format('kafka')
        .option('kafka.bootstrap.servers', os.environ['KAFKA_BOOTSTRAP'])
        .option('subscribe', os.environ.get('KAFKA_TOPIC', 'weather.v1'))
        .option('startingOffsets', 'earliest')
        .option('maxOffsetsPerTrigger', 1000)
        .load().selectExpr('CAST(value AS STRING) AS value'))

    def save(batch, batch_id):
        try:
            write_batch(batch, batch_id, grids)
        except Exception as error:
            path = os.environ.get('WEATHER_PROCESS_LOG_PATH', '')
            if path:
                append(path, dict(stage='mongo_projection', ok=False, batch_id=batch_id,
                    error_type=type(error).__name__, requested_at=datetime.now(timezone.utc).isoformat()))
                flush_if_configured(path)
            raise

    writer = (stream.writeStream.foreachBatch(save)
        .option('checkpointLocation', os.environ['CHECKPOINT_PATH']))
    # microbatch는 기존 마이크로배치. available_now는 현재 대기 자료 처리 후 종료.
    # 팀의 주기 배치/상시 실행 선택과 외부 스케줄은 별도 확정.
    mode = os.environ.get('WEATHER_SPARK_MODE', 'microbatch')
    if mode == 'available_now':
        writer = writer.trigger(availableNow=True)
    elif mode == 'microbatch':
        writer = writer.trigger(processingTime=os.environ.get('WEATHER_SPARK_INTERVAL', '15 seconds'))
    else:
        raise ValueError('invalid_weather_spark_mode')
    query = writer.start()
    try:
        query.awaitTermination()
    finally:
        spark.stop()

if __name__ == '__main__':
    main()
