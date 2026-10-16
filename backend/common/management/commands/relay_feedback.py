import json
import os
import time
from django.core.management.base import BaseCommand, CommandError
from backend.common.events import relay_once
from pipeline.kafka_config import python_options


class Command(BaseCommand):
    help = '업무 트랜잭션의 outbox를 Kafka에 발행. ACK 후 SENT, 실패/중단은 동일 event_id 재시도.'

    def add_arguments(self,parser):
        parser.add_argument('--watch',action='store_true')

    def handle(self,*args,**options):
        bootstrap=os.environ.get('FEEDBACK_KAFKA_BOOTSTRAP','')
        topic=os.environ.get('FEEDBACK_KAFKA_TOPIC','')
        if not bootstrap or not topic:raise CommandError('feedback_kafka_configuration_required')
        from kafka import KafkaProducer
        producer=KafkaProducer(bootstrap_servers=bootstrap,acks='all',retries=3,**python_options('FEEDBACK_KAFKA_'),
                               value_serializer=lambda value:json.dumps(value,ensure_ascii=False).encode())
        def publish(event_id,envelope):
            producer.send(topic,key=event_id.encode(),value=envelope).get(timeout=15)
        try:
            while True:
                processed=relay_once(publish)
                if not options['watch'] and not processed:break
                if not processed:time.sleep(1)
        except KeyboardInterrupt:pass
        finally:producer.close(timeout=10)
