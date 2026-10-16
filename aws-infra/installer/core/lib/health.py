#!/usr/bin/env python3
"""Health checks and isolated smoke data; credentials are never printed."""
import argparse
import base64
import json
from pathlib import Path
import re
import socket
import ssl
import subprocess
import sys
import time
import uuid
from urllib.request import Request, urlopen
from config import ZK_TLS_PORT

BASE = '/opt/music-cluster'
CONF = '/etc/music-cluster'


def api(url, context=None, user=None, password=None, method='GET', body=None):
    headers = {'Content-Type': 'application/json'}
    if user:
        token = base64.b64encode(f'{user}:{password}'.encode()).decode()
        headers['Authorization'] = 'Basic ' + token
    request = Request(url, data=json.dumps(body).encode() if body is not None else None, headers=headers, method=method)
    with urlopen(request, timeout=30, context=context) as r:
        return json.load(r)


def es_client(c):
    ctx = ssl.create_default_context(cafile=CONF + '/elasticsearch/tls/ca.crt')
    def call(path, method='GET', body=None):
        return api(c['derived']['es_urls'][0] + path, ctx, 'cluster_admin', c['env']['ES_ADMIN_PASSWORD'], method, body)
    return call


def es(c, finalize=False, smoke=False):
    call = es_client(c)
    h = call('/_cluster/health?wait_for_status=green&wait_for_nodes=3&timeout=60s')
    if h.get('timed_out') or h['status'] != 'green' or h['number_of_nodes'] != 3:
        raise ValueError('ES requires three nodes and green cluster health')
    observed = {n['name'] for n in call('/_nodes')['nodes'].values()}
    expected = {n['name'] for n in c['inventory']['nodes'] if 'es' in n['roles']}
    if observed != expected: raise ValueError('ES cluster membership differs from inventory')
    if finalize:
        identity = call('/')['cluster_uuid']
        if identity == '_na_': raise ValueError('ES has no committed cluster UUID')
        marker = Path('/var/lib/music-cluster/state/es-initialized.json')
        if marker.exists() and json.loads(marker.read_text())['cluster_uuid'] != identity:
            raise ValueError('ES cluster UUID changed unexpectedly')
        path = Path(CONF + '/elasticsearch/elasticsearch.yml')
        # Finalize each ES guest only after all nodes belong to the intended cluster.
        text = ''.join(line for line in path.read_text().splitlines(True) if not line.startswith('cluster.initial_master_nodes:'))
        path.write_text(text)
        marker.write_text(json.dumps({'cluster_uuid': identity}) + '\n')
        marker.chmod(0o600)
    if smoke:
        index = 'cluster-smoke-' + uuid.uuid4().hex
        token = uuid.uuid4().hex
        try:
            call('/' + index + '/_doc/probe?refresh=wait_for', 'PUT', {'token': token})
            if call('/' + index + '/_doc/probe')['_source']['token'] != token:
                raise ValueError('ES write/read mismatch')
        finally:
            call('/' + index, 'DELETE')
    print('[PASS] ES membership/green' + (' and write/read' if smoke else ''))


def zk_mode(address, *, tls=True, port=None, tls_directory=None):
    port = port if port is not None else (ZK_TLS_PORT if tls else 2181)
    context = None
    if tls:
        material = Path(tls_directory or (CONF + '/spark/tls'))
        context = ssl.create_default_context(cafile=str(material / 'ca.crt'))
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(str(material / 'node.crt'), str(material / 'node.key'))
    connection = socket.create_connection((address, port), timeout=5)
    if context is not None:
        try:
            connection = context.wrap_socket(connection, server_hostname=address)
        except Exception:
            connection.close()
            raise
    with connection as s:
        s.sendall(b'srvr')
        chunks = []
        while True:
            data = s.recv(4096)
            if not data: break
            chunks.append(data)
    mode = re.search(r'Mode: (leader|follower)', b''.join(chunks).decode())
    if not mode: raise ValueError('ZooKeeper is not a voting leader/follower')
    return mode.group(1)


def zookeeper(c):
    nodes = [n for n in c['inventory']['nodes'] if 'spark' in n['roles']]
    modes = [zk_mode(n['address'], tls_directory=CONF + '/zookeeper/tls') for n in nodes]
    if modes.count('leader') != 1 or modes.count('follower') != 2:
        raise ValueError('ZooKeeper ensemble membership is incomplete')
    print('[PASS] ZooKeeper verified client TLS, one leader and two followers')


def spark(c):
    nodes = [n for n in c['inventory']['nodes'] if 'spark' in n['roles']]
    masters = [api('http://' + n['address'] + ':8080/json/') for n in nodes]
    live = [m for m in masters if m['status'] == 'ALIVE']
    if len(live) != 1 or sum(m['status'] == 'STANDBY' for m in masters) != 2:
        raise ValueError('Spark must have one active and two standby Masters')
    workers = {w['host'] for w in live[0]['workers'] if w['state'] == 'ALIVE'}
    if workers != {n['address'] for n in nodes}:
        raise ValueError('Spark requires all three Workers registered')
    zookeeper(c)
    print('[PASS] Spark active/standby Masters, three Workers and ZooKeeper quorum')


def kafka_command(c, script, *args, stdin=None):
    cmd = ['runuser', '-u', 'kafka', '--', 'env', 'LOG_DIR=/var/lib/music-cluster/kafka/log',
           'JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64', BASE + '/kafka/bin/' + script,
           '--bootstrap-server', c['derived']['kafka_bootstrap']]
    if script == 'kafka-console-producer.sh': flag = '--producer.config'
    elif script == 'kafka-console-consumer.sh': flag = '--consumer.config'
    else: flag = '--command-config'
    cmd += [flag, CONF + '/kafka/admin.properties', *args]
    r = subprocess.run(cmd, input=stdin, text=True, capture_output=True, timeout=90)
    if r.returncode:
        # JVM errors can echo properties; keep raw private service logs out of summaries.
        raise ValueError('Kafka CLI failed: ' + script + '; inspect the private service journal')
    return r.stdout


def kafka(c, smoke=False, catalog=False):
    output = kafka_command(c, 'kafka-metadata-quorum.sh', 'describe', '--status')
    fields = dict(re.findall(r'^([A-Za-z]+):\s*(.+)$', output, re.M))
    if fields.get('ClusterId') != c['env']['KAFKA_CLUSTER_ID'] or fields.get('LeaderId') not in ('1', '2', '3'):
        raise ValueError('Kafka cluster ID or quorum leader mismatch')
    voters = fields.get('CurrentVoters', '')
    ids = set(map(int, re.findall(r'"id"\s*:\s*(\d+)', voters))) if 'id' in voters else set(map(int, re.findall(r'\d+', voters)))
    if ids != {1, 2, 3}: raise ValueError('Kafka quorum does not contain all three voters')
    brokers = kafka_command(c, 'kafka-broker-api-versions.sh')
    if set(map(int, re.findall(r'\(id:\s*(\d+)', brokers))) != {1, 2, 3}:
        raise ValueError('Kafka broker membership is incomplete')
    if catalog:
        for topic in ('weather.v1', 'feedback.v1'):
            kafka_command(c, 'kafka-topics.sh', '--create', '--if-not-exists', '--topic', topic,
                          '--partitions', '3', '--replication-factor', '3', '--config', 'min.insync.replicas=2')
            description = kafka_command(c, 'kafka-topics.sh', '--describe', '--topic', topic)
            if not re.search(r'ReplicationFactor:\s*3\b', description) or not re.search(r'PartitionCount:\s*3\b', description) or 'min.insync.replicas=2' not in description:
                raise ValueError('Existing topic partition/replication/ISR contract differs; no automatic destructive correction')
            kafka_command(c, 'kafka-acls.sh', '--add', '--allow-principal', 'User:pipeline', '--operation', 'Read',
                          '--operation', 'Write', '--operation', 'Describe', '--topic', topic)
        kafka_command(c, 'kafka-acls.sh', '--add', '--allow-principal', 'User:pipeline', '--operation', 'Read', '--group', '*')
        kafka_command(c, 'kafka-acls.sh', '--add', '--allow-principal', 'User:pipeline', '--operation', 'Describe', '--cluster')
        kafka_command(c, 'kafka-acls.sh', '--add', '--allow-principal', 'User:pipeline', '--operation', 'IdempotentWrite', '--cluster')
    if smoke:
        topic, token = 'cluster-smoke-' + uuid.uuid4().hex, uuid.uuid4().hex
        try:
            kafka_command(c, 'kafka-topics.sh', '--create', '--topic', topic, '--partitions', '3', '--replication-factor', '3', '--config', 'min.insync.replicas=2')
            kafka_command(c, 'kafka-console-producer.sh', '--topic', topic, stdin=token + '\n')
            result = kafka_command(c, 'kafka-console-consumer.sh', '--topic', topic, '--from-beginning', '--group', topic, '--max-messages', '1', '--timeout-ms', '30000')
            if result.strip() != token: raise ValueError('Kafka produce/consume mismatch')
        finally:
            kafka_command(c, 'kafka-topics.sh', '--delete', '--topic', topic)
    print('[PASS] Kafka quorum and three brokers' + (' and produce/consume' if smoke else ''))


def es_catalog(c):
    call = es_client(c)
    for family in ('weather', 'feedback', 'pipeline-logs'):
        body = {'index_patterns': [family + '-*'], 'priority': 100,
                'template': {'settings': {'number_of_shards': 3, 'number_of_replicas': 1},
                             'mappings': {'properties': {'@timestamp': {'type': 'date'}, 'event_id': {'type': 'keyword'}}}}}
        path = '/_index_template/music-' + family
        try:
            existing = call(path)['index_templates'][0]['index_template']
        except Exception as error:
            from urllib.error import HTTPError
            if not isinstance(error, HTTPError) or error.code != 404: raise
            existing = None
        if existing is not None and canonical_template(existing) != canonical_template(body):
            raise ValueError('Existing ES template differs; review schema changes explicitly')
        if existing is None: call(path, 'PUT', body)
    print('[PASS] ES index templates configured')


def canonical_template(template):
    value = json.loads(json.dumps(template))
    value.setdefault('composed_of', [])
    settings = value.get('template', {}).get('settings', {})
    flat = {}
    def flatten(mapping, prefix=''):
        for key, item in mapping.items():
            if isinstance(item, dict): flatten(item, prefix + key + '.')
            else: flat[(prefix + key).removeprefix('index.')] = str(item)
    flatten(settings)
    value['template']['settings'] = flat
    return value


def main():
    p = argparse.ArgumentParser()
    p.add_argument('runtime'); p.add_argument('action', choices=('health', 'zookeeper-health', 'smoke', 'finalize-es', 'catalog'))
    a = p.parse_args(); c = json.loads(Path(a.runtime).read_text())
    roles = c['node']['roles']
    if a.action == 'zookeeper-health' and 'spark' not in roles:
        raise ValueError('ZooKeeper health must run on a Spark node')
    for role in ('kafka', 'spark', 'es'):
        if role not in roles: continue
        if a.action == 'finalize-es':
            if role == 'es': es(c, finalize=True)
            continue
        if a.action == 'catalog':
            if role == 'kafka': kafka(c, catalog=True)
            if role == 'es': es_catalog(c)
            continue
        deadline = time.monotonic() + 150
        while True:
            try:
                if a.action == 'zookeeper-health': zookeeper(c)
                elif role == 'kafka': kafka(c, smoke=a.action == 'smoke')
                elif role == 'es': es(c, smoke=a.action == 'smoke')
                else: spark(c)
                break
            except (OSError, ValueError, KeyError, subprocess.SubprocessError):
                if a.action == 'smoke' or time.monotonic() >= deadline: raise
                time.sleep(5)


if __name__ == '__main__':
    try: main()
    except Exception as error:
        # No HTTP bodies or command output: they may contain runtime secrets.
        message = str(error) if isinstance(error, ValueError) else type(error).__name__
        print('[FAIL] ' + message, file=sys.stderr); sys.exit(1)
