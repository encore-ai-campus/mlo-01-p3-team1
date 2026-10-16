"""Kafka → Spark 격자 선택·정규화 → MongoDB. ES는 별도 발행."""
import json
import os
from datetime import datetime, timezone
from importlib.resources import files
from weather.pipeline.common import normalize_event
from weather.pipeline.mongo_current import collection, write_grid
from weather.pipeline.collection_logs import append, flush_if_configured


def write_batch(batch, batch_id, grid_broadcast):
    """Kafka value 열의 JSON을 정제·격자별 묶기 → Driver에서 MongoDB 저장.

    batch는 Spark DataFrame, grid_broadcast.value는 {(nx, ny): 지역 정보} 매핑.
    저장 실패는 호출자에게 전달해 Spark가 같은 배치를 재처리할 수 있게 함.
    """
    store = collection('write')

    def normalize_message(message):
        event = json.loads(message.value)
        return normalize_event(event, grid_broadcast.value)

    def attach_grid_key(row):
        return (row['nx'], row['ny']), row

    # Executor: 메시지 정제 후 같은 격자의 행을 묶음.
    normalized_rows = batch.rdd.flatMap(normalize_message)
    keyed_rows = normalized_rows.map(attach_grid_key)
    grouped_rows = keyed_rows.groupByKey().mapValues(list)

    # Driver: 격자별 저장. Executor에 DB 연결 객체를 전달하지 않음.
    row_count = 0
    grid_count = 0
    changed_count = 0
    request_ids = set()
    for (nx, ny), rows in grouped_rows.toLocalIterator():
        changed = write_grid(store, nx, ny, rows)
        if changed:
            changed_count += 1
        grid_count += 1
        row_count += len(rows)
        request_ids.update(row['request_id'] for row in rows if row.get('request_id'))

    log_path = os.environ.get('WEATHER_PROCESS_LOG_PATH', '')
    if log_path:
        append(log_path, dict(
            stage='mongo_projection', ok=True, batch_id=batch_id,
            normalized_rows=row_count, grids=grid_count,
            request_ids=sorted(request_ids),
            requested_at=datetime.now(timezone.utc).isoformat(),
        ))
        flush_if_configured(log_path)
    print(json.dumps(dict(
        batch_id=batch_id, normalized_rows=row_count, grids=grid_count,
        changed_grids=changed_count, sink='mongodb_latest',
    )), flush=True)


def main():
    from pyspark.sql import SparkSession

    required_settings = (
        'KAFKA_BOOTSTRAP', 'WEATHER_MONGODB_WRITE_URI', 'WEATHER_MONGODB_DATABASE',
        'WEATHER_MONGODB_COLLECTION', 'CHECKPOINT_PATH',
    )
    for name in required_settings:
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
