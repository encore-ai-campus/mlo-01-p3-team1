#!/usr/bin/env python3
"""Render service configuration into a staging directory; never print secrets."""
import argparse
import json
from pathlib import Path
from config import ZK_TLS_PORT

BASE = '/opt/music-cluster'
CONF = '/etc/music-cluster'
DATA = '/var/lib/music-cluster'
JAVA = '/usr/lib/jvm/java-21-openjdk-amd64'


def unit(description, user, command, env=(), after='network-online.target', extra='', restart='on-failure'):
    environment = ''.join(f'Environment="{line}"\n' for line in env)
    return (f'[Unit]\nDescription={description}\nWants=network-online.target\nAfter={after}\n'
            f'[Service]\nType=simple\nUser={user}\nGroup={user}\nUMask=0027\n'
            f'{environment}ExecStart={command}\nRestart={restart}\nRestartSec=10\n'
            'TimeoutStopSec=120\nKillMode=control-group\nLimitNOFILE=65536\n'
            f'NoNewPrivileges=true\nPrivateTmp=true\n{extra}'
            '[Install]\nWantedBy=multi-user.target\n')


def kafka(c):
    n, e, d = c['node'], c['env'], c['derived']
    secret = f'{CONF}/kafka'
    tls = f'{secret}/tls'
    jaas = ('org.apache.kafka.common.security.plain.PlainLoginModule required '
            f'username="broker" password="{e["KAFKA_BROKER_PASSWORD"]}" '
            f'user_broker="{e["KAFKA_BROKER_PASSWORD"]}" '
            f'user_admin="{e["KAFKA_ADMIN_PASSWORD"]}" '
            f'user_pipeline="{e["KAFKA_PIPELINE_PASSWORD"]}";')
    props = {
        'process.roles': 'broker,controller', 'node.id': n['id'],
        # Static quorum is deliberate for this fixed three-node topology.
        'controller.quorum.voters': d['kraft_voters'],
        'listeners': f'BROKER://{n["address"]}:9092,CONTROLLER://{n["address"]}:9093',
        'advertised.listeners': f'BROKER://{n["address"]}:9092',
        'listener.security.protocol.map': 'BROKER:SASL_SSL,CONTROLLER:SASL_SSL',
        'controller.listener.names': 'CONTROLLER', 'inter.broker.listener.name': 'BROKER',
        'sasl.enabled.mechanisms': 'PLAIN', 'sasl.mechanism.inter.broker.protocol': 'PLAIN',
        'sasl.mechanism.controller.protocol': 'PLAIN',
        'listener.name.broker.plain.sasl.jaas.config': jaas,
        'listener.name.controller.plain.sasl.jaas.config': jaas,
        'ssl.keystore.type': 'PKCS12', 'ssl.keystore.location': f'{tls}/node.p12',
        'ssl.keystore.password': e['TLS_STORE_PASSWORD'], 'ssl.key.password': e['TLS_STORE_PASSWORD'],
        'ssl.truststore.type': 'PKCS12', 'ssl.truststore.location': f'{tls}/trust.p12',
        'ssl.truststore.password': e['TLS_STORE_PASSWORD'], 'ssl.endpoint.identification.algorithm': 'HTTPS',
        'authorizer.class.name': 'org.apache.kafka.metadata.authorizer.StandardAuthorizer',
        'super.users': 'User:broker;User:admin', 'allow.everyone.if.no.acl.found': 'false',
        'log.dirs': f'{DATA}/kafka/data', 'metadata.log.dir': f'{DATA}/kafka/metadata',
        'default.replication.factor': 3, 'min.insync.replicas': 2,
        'offsets.topic.replication.factor': 3, 'transaction.state.log.replication.factor': 3,
        'transaction.state.log.min.isr': 2, 'unclean.leader.election.enable': 'false',
        'auto.create.topics.enable': 'false', 'num.partitions': 3,
        'log.retention.hours': 168, 'log.segment.bytes': 1073741824,
    }
    client = {
        'security.protocol': 'SASL_SSL', 'sasl.mechanism': 'PLAIN',
        'sasl.jaas.config': 'org.apache.kafka.common.security.plain.PlainLoginModule required '
                            f'username="admin" password="{e["KAFKA_ADMIN_PASSWORD"]}";',
        'ssl.truststore.type': 'PKCS12', 'ssl.truststore.location': f'{tls}/trust.p12',
        'ssl.truststore.password': e['TLS_STORE_PASSWORD'], 'ssl.endpoint.identification.algorithm': 'HTTPS',
        'acks': 'all', 'enable.idempotence': 'true',
    }
    properties = lambda p: ''.join(f'{k}={v}\n' for k, v in p.items())
    return {'server.properties': properties(props), 'admin.properties': properties(client)}, {
        'music-kafka.service': unit('Music cluster Kafka KRaft', 'kafka',
            f'{BASE}/kafka/bin/kafka-server-start.sh {secret}/server.properties',
            (f'JAVA_HOME={JAVA}', f'LOG_DIR={DATA}/kafka/log',
             f'KAFKA_HEAP_OPTS=-Xms{n.get("heap", "2g")} -Xmx{n.get("heap", "2g")}'))}


def zookeeper(c):
    n, e = c['node'], c['env']
    servers = [x for x in c['inventory']['nodes'] if 'spark' in x['roles']]
    password = e['ZK_HA_PASSWORD']
    cfg = (f'tickTime=2000\ninitLimit=10\nsyncLimit=5\ndataDir={DATA}/zookeeper/data\n'
           f'dataLogDir={DATA}/zookeeper/log\nsecureClientPort={ZK_TLS_PORT}\nsecureClientPortAddress={n["address"]}\n'
           'serverCnxnFactory=org.apache.zookeeper.server.NettyServerCnxnFactory\n'
           'sslQuorum=true\nportUnification=false\n'
           'leader.closeSocketAsync=true\nlearner.closeSocketAsync=true\n'
           'autopurge.snapRetainCount=3\nautopurge.purgeInterval=24\n'
           'admin.enableServer=false\n4lw.commands.whitelist=srvr,ruok\n'
           'authProvider.1=org.apache.zookeeper.server.auth.SASLAuthenticationProvider\n'
           'sessionRequireClientSASLAuth=true\nquorum.auth.enableSasl=true\n'
           'quorum.auth.learnerRequireSasl=true\nquorum.auth.serverRequireSasl=true\n'
           'quorum.auth.learner.loginContext=QuorumLearner\nquorum.auth.server.loginContext=QuorumServer\n'
           'quorum.cnxn.threads.size=6\n' +
           ''.join(f'server.{x["zk_id"]}={x["address"]}:2888:3888\n' for x in servers))
    for prefix in ('ssl.', 'ssl.quorum.'):
        for key, value in {
            'keyStore.location': f'{CONF}/zookeeper/tls/node.p12',
            'trustStore.location': f'{CONF}/zookeeper/tls/trust.p12',
            'keyStore.passwordPath': f'{CONF}/zookeeper/tls/store.password',
            'trustStore.passwordPath': f'{CONF}/zookeeper/tls/store.password',
            'keyStore.type': 'PKCS12', 'trustStore.type': 'PKCS12',
            'clientAuth': 'need', 'hostnameVerification': 'true',
            # Netty server engines do not supply the client's peer host.
            # Authenticate client certificates by the CA; verify server names
            # on clients and both quorum peer addresses on SSLSockets.
            'clientHostnameVerification': 'true' if prefix == 'ssl.quorum.' else 'false',
            'protocol': 'TLSv1.3',
            'enabledProtocols': 'TLSv1.3,TLSv1.2',
        }.items():
            cfg += prefix + key + '=' + value + '\n'
    jaas = (f'Server {{ org.apache.zookeeper.server.auth.DigestLoginModule required user_cluster="{password}"; }};\n'
            f'QuorumServer {{ org.apache.zookeeper.server.auth.DigestLoginModule required user_cluster="{password}"; }};\n'
            f'QuorumLearner {{ org.apache.zookeeper.server.auth.DigestLoginModule required username="cluster" password="{password}"; }};\n')
    return {'zoo.cfg': cfg, 'jaas.conf': jaas}, {'music-zookeeper.service': unit(
        'Music cluster ZooKeeper ensemble', 'zookeeper',
        f'{JAVA}/bin/java -Xms256m -Xmx512m -Dzookeeper.fips-mode=false '
        f'-Djava.security.auth.login.config={CONF}/zookeeper/jaas.conf '
        f'-Dzookeeper.log.dir={DATA}/zookeeper/log -cp {BASE}/zookeeper/conf:{BASE}/zookeeper/lib/* '
        f'org.apache.zookeeper.server.quorum.QuorumPeerMain {CONF}/zookeeper/zoo.cfg')}


def spark(c):
    n, e, d = c['node'], c['env'], c['derived']
    defaults = {
        'spark.master': d['spark_master'], 'spark.authenticate': 'true',
        'spark.authenticate.secret': e['SPARK_AUTH_SECRET'], 'spark.network.crypto.enabled': 'true',
        'spark.network.crypto.authEngineVersion': 2, 'spark.authenticate.enableSaslEncryption': 'true',
        'spark.deploy.recoveryMode': 'ZOOKEEPER', 'spark.deploy.zookeeper.url': d['zk_connect'],
        'spark.deploy.zookeeper.dir': '/music-cluster/' + e['ENVIRONMENT'] + '/spark',
        'spark.deploy.defaultCores': 3, 'spark.cores.max': 3, 'spark.executor.cores': 1,
        'spark.executor.memory': '1g', 'spark.driver.memory': '1g',
        'spark.driver.host': n['address'], 'spark.driver.bindAddress': n['address'],
        'spark.driver.port': 39000, 'spark.driver.blockManager.port': 39050,
        'spark.blockManager.port': 39100, 'spark.port.maxRetries': 32,
        'spark.ui.bindAddress': '127.0.0.1',
        'spark.master.rest.enabled': 'false',
        'spark.pyspark.python': f'{BASE}/python/bin/python3.14',
        'spark.pyspark.driver.python': f'{BASE}/python/bin/python3.14',
        'spark.redaction.regex': '(?i)secret|password|token|access[.]?key|sasl[.]jaas',
    }
    jvm = ('-Dspark.authenticate=true -Dspark.authenticate.secret=' + e['SPARK_AUTH_SECRET'] +
           ' -Dzookeeper.fips-mode=false'
           ' -Dspark.network.crypto.enabled=true -Dspark.network.crypto.authEngineVersion=2'
           ' -Dspark.deploy.recoveryMode=ZOOKEEPER -Dspark.deploy.zookeeper.url=' + d['zk_connect'] +
           ' -Dspark.deploy.zookeeper.dir=/music-cluster/' + e['ENVIRONMENT'] + '/spark'
           f' -Djava.security.auth.login.config={CONF}/spark/zk-client-jaas.conf')
    zk_tls = {
        'zookeeper.client.secure': 'true',
        'zookeeper.clientCnxnSocket': 'org.apache.zookeeper.ClientCnxnSocketNetty',
        'zookeeper.ssl.keyStore.location': f'{CONF}/spark/tls/node.p12',
        'zookeeper.ssl.trustStore.location': f'{CONF}/spark/tls/trust.p12',
        'zookeeper.ssl.keyStore.passwordPath': f'{CONF}/spark/tls/store.password',
        'zookeeper.ssl.trustStore.passwordPath': f'{CONF}/spark/tls/store.password',
        'zookeeper.ssl.keyStore.type': 'PKCS12', 'zookeeper.ssl.trustStore.type': 'PKCS12',
        'zookeeper.ssl.hostnameVerification': 'true',
        'zookeeper.ssl.protocol': 'TLSv1.3', 'zookeeper.ssl.enabledProtocols': 'TLSv1.3,TLSv1.2',
    }
    jvm += ''.join(f' -D{key}={value}' for key, value in zk_tls.items())
    env = (f'JAVA_HOME={JAVA}', f'SPARK_CONF_DIR={CONF}/spark',
            f'SPARK_WORKER_DIR={DATA}/spark/work', f'SPARK_LOCAL_DIRS={DATA}/spark/local',
           f'SPARK_LOG_DIR={DATA}/spark/log',
            'SPARK_DAEMON_MEMORY=512m')
    configs = {
        'spark-defaults.conf': ''.join(f'{k} {v}\n' for k, v in defaults.items()),
        'daemon.env': f'SPARK_DAEMON_JAVA_OPTS="{jvm}"\n',
        'zk-client-jaas.conf': 'Client { org.apache.zookeeper.server.auth.DigestLoginModule required '
                               f'username="cluster" password="{e["ZK_HA_PASSWORD"]}"; }};\n',
        'pipeline.json': json.dumps({'derived': d, 'env': {k: v for k, v in e.items() if k in
                          ('KAFKA_PIPELINE_PASSWORD', 'ES_WRITER_PASSWORD', 'TLS_STORE_PASSWORD',
                           'AWS_REGION', 'S3_BUCKET', 'S3_CHECKPOINT_PREFIX', 'ENVIRONMENT')}}, indent=2) + '\n',
    }
    units = {
        'music-spark-master.service': unit('Music cluster Spark Master', 'spark',
            f'{BASE}/spark/bin/spark-class org.apache.spark.deploy.master.Master --host {n["address"]} --port 7077 --webui-port 8080',
            env, 'network-online.target music-zookeeper.service', extra=f'EnvironmentFile={CONF}/spark/daemon.env\n', restart='always'),
        'music-spark-worker.service': unit('Music cluster Spark Worker', 'spark',
            f'{BASE}/spark/bin/spark-class org.apache.spark.deploy.worker.Worker --host {n["address"]} --port 7078 '
            f'--webui-port 8081 --cores {n["worker_cores"]} --memory {n["worker_memory"]} {d["spark_master"]}', env,
            extra=f'EnvironmentFile={CONF}/spark/daemon.env\n'),
    }
    return configs, units


def elasticsearch(c):
    n, e = c['node'], c['env']
    nodes = [x for x in c['inventory']['nodes'] if 'es' in x['roles']]
    # JSON strings/lists are valid YAML scalars and avoid YAML injection.
    cfg = {
        'cluster.name': 'music-cluster-' + e['ENVIRONMENT'], 'node.name': n['name'],
        'node.roles': ['master', 'data', 'ingest'], 'network.host': n['address'],
        'http.port': 9200, 'transport.port': 9300,
        'discovery.seed_hosts': [x['address'] + ':9300' for x in nodes],
        'path.data': DATA + '/elasticsearch/data', 'path.logs': DATA + '/elasticsearch/log',
        'node.attr.failure_domain': n.get('physical_host', n.get('az')),
        'cluster.routing.allocation.awareness.attributes': 'failure_domain',
        'xpack.security.enabled': True, 'xpack.security.enrollment.enabled': False,
        'xpack.security.authc.realms.file.cluster_file.order': 0,
        'xpack.security.transport.ssl.enabled': True,
        'xpack.security.transport.ssl.verification_mode': 'full',
        'xpack.security.transport.ssl.client_authentication': 'required',
        'xpack.security.transport.ssl.key': 'tls/node.key',
        'xpack.security.transport.ssl.certificate': 'tls/node.crt',
        'xpack.security.transport.ssl.certificate_authorities': ['tls/ca.crt'],
        'xpack.security.http.ssl.enabled': True, 'xpack.security.http.ssl.key': 'tls/node.key',
        'xpack.security.http.ssl.certificate': 'tls/node.crt',
        'xpack.security.http.ssl.certificate_authorities': ['tls/ca.crt'],
    }
    if c.get('es_bootstrap'):
        cfg['cluster.initial_master_nodes'] = [x['name'] for x in nodes]
    roles = 'pipeline_writer:\n  cluster: [monitor]\n  indices:\n    - names: ["weather-*", "feedback-*", "pipeline-logs-*", "cluster-smoke-*"]\n      privileges: [read, write, create_index, view_index_metadata]\n'
    files = {'elasticsearch.yml': ''.join(f'{k}: {json.dumps(v)}\n' for k, v in cfg.items()),
             'jvm.options.d/heap.options': f'-Xms{n["es_heap"]}\n-Xmx{n["es_heap"]}\n', 'roles.yml': roles}
    return files, {'music-elasticsearch.service': unit('Music cluster Elasticsearch', 'elasticsearch',
        f'{BASE}/elasticsearch/bin/elasticsearch', (f'ES_PATH_CONF={CONF}/elasticsearch',),
        extra='LimitNPROC=4096\nLimitMEMLOCK=infinity\n')}


RENDERERS = {'kafka': kafka, 'zookeeper': zookeeper, 'spark': spark, 'elasticsearch': elasticsearch}


def render(c, role, output):
    files, units = RENDERERS[role](c)
    output = Path(output)
    for name, text in {**{f'config/{k}': v for k, v in files.items()}, **{f'units/{k}': v for k, v in units.items()}}.items():
        p = output / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding='utf-8')
        p.chmod(0o600)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('runtime'); p.add_argument('role', choices=RENDERERS); p.add_argument('output')
    p.add_argument('--bootstrap-es', action='store_true')
    a = p.parse_args()
    c = json.loads(Path(a.runtime).read_text())
    c['es_bootstrap'] = a.bootstrap_es
    render(c, a.role, a.output)
