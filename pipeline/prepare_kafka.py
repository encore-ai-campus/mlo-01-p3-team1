"""Create only a missing, explicitly configured Kafka topic; never resize/delete."""
import os
from pipeline.kafka_config import python_options


def ensure_topic(prefix):
    from kafka.admin import KafkaAdminClient, NewTopic
    from kafka.errors import TopicAlreadyExistsError
    bootstrap=os.environ.get(prefix+'BOOTSTRAP','');topic=os.environ.get(prefix+'TOPIC','')
    if not bootstrap or not topic:raise RuntimeError('kafka_topic_configuration_required')
    admin=KafkaAdminClient(bootstrap_servers=bootstrap,request_timeout_ms=10000,
                           api_version_auto_timeout_ms=5000,**python_options(prefix))
    try:
        if topic in admin.list_topics():return {'created':False}
        try:
            partitions=int(os.environ.get(prefix+'TOPIC_PARTITIONS') or '0')
            replication=int(os.environ.get(prefix+'REPLICATION_FACTOR') or '0')
        except ValueError:raise RuntimeError('kafka_topic_counts_invalid') from None
        if partitions<1 or replication<1:raise RuntimeError('kafka_topic_counts_required_for_creation')
        try:admin.create_topics([NewTopic(topic,num_partitions=partitions,replication_factor=replication)])
        except TopicAlreadyExistsError:return {'created':False}
        return {'created':True}
    finally:admin.close()
