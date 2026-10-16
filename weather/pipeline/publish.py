"""메모리 이벤트 전송. 전체 ACK 후 성공 처리."""
from weather.pipeline.common import encode

def send_events(producer, events, topic):
    """메모리 이벤트 전송. 전체 ACK 후에만 요청 성공 처리."""
    for event in events:
        key = (event['source'] + ':' + event['category']).encode()
        producer.send(topic, key=key, value=encode(event)).get(timeout=30)
    producer.flush(timeout=30)
