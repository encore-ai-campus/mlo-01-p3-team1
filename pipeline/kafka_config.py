"""클라이언트/Driver의 비공개 Kafka 접속 설정. 자격증명은 로그/CLI에 출력하지 않음."""
import json
import os
from pathlib import Path


def python_options(prefix='KAFKA_'):
    protocol=os.environ.get(prefix+'SECURITY_PROTOCOL','PLAINTEXT')
    if protocol not in ('PLAINTEXT','SSL','SASL_SSL'):raise ValueError('unsupported_kafka_security_protocol')
    result={'security_protocol':protocol}
    ca=os.environ.get(prefix+'SSL_CAFILE')
    if ca:result['ssl_cafile']=ca
    username=os.environ.get(prefix+'SASL_USERNAME','');password=os.environ.get(prefix+'SASL_PASSWORD','')
    if username or password or protocol=='SASL_SSL':
        if protocol!='SASL_SSL' or not username or not password:raise ValueError('kafka_sasl_tls_configuration_required')
        result.update(sasl_mechanism=os.environ.get(prefix+'SASL_MECHANISM','PLAIN'),
                      sasl_plain_username=username,sasl_plain_password=password)
    return result


def spark_options(name):
    path=os.environ.get(name,'')
    if not path:return {}
    data=json.loads(Path(path).read_text(encoding='utf8'))
    allowed={'kafka.security.protocol','kafka.sasl.mechanism','kafka.sasl.jaas.config',
             'kafka.ssl.truststore.location','kafka.ssl.truststore.password','kafka.ssl.truststore.type',
             'kafka.ssl.keystore.location','kafka.ssl.keystore.password','kafka.ssl.keystore.type',
             'kafka.ssl.key.password','kafka.ssl.endpoint.identification.algorithm'}
    if not isinstance(data,dict) or set(data)-allowed or any(type(v) is not str for v in data.values()):
        raise ValueError('invalid_spark_kafka_options')
    if data.get('kafka.security.protocol') not in ('SSL','SASL_SSL'):raise ValueError('spark_kafka_tls_required')
    if data.get('kafka.ssl.endpoint.identification.algorithm','https')!='https':raise ValueError('kafka_hostname_verification_required')
    data['kafka.ssl.endpoint.identification.algorithm']='https'
    return data
