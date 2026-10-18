"""Kafka offset 원본·업무 이벤트 일치·중복 projection을 PostgreSQL에 기록합니다."""
import json
import os
from pipeline.kafka_config import python_options


def setup():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE','backend.cafe.settings')
    import django
    django.setup()


def apply_record(value,topic,partition,offset):
    from backend.common.events import ingest
    return ingest(value,f'{topic}:{partition}:{offset}')


def main():
    setup()
    from kafka import KafkaConsumer
    bootstrap=os.environ.get('FEEDBACK_KAFKA_BOOTSTRAP','')
    topic=os.environ.get('FEEDBACK_KAFKA_TOPIC','')
    group=os.environ.get('FEEDBACK_KAFKA_GROUP','')
    if not all([bootstrap,topic,group]):raise RuntimeError('feedback_consumer_configuration_required')
    consumer=KafkaConsumer(topic,bootstrap_servers=bootstrap,group_id=group,**python_options('FEEDBACK_KAFKA_'),
                           enable_auto_commit=False,auto_offset_reset='earliest',
                           value_deserializer=lambda raw:json.loads(raw.decode('utf-8')))
    try:
        for record in consumer:
            apply_record(record.value,record.topic,record.partition,record.offset)
            consumer.commit()
    finally:consumer.close()


if __name__=='__main__':main()
