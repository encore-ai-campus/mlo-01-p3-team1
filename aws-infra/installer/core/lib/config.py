#!/usr/bin/env python3
"""Stage-aware data-only configuration and per-node runtime rendering."""
import argparse
import base64
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
NAME = re.compile(r'[a-z][a-z0-9-]{0,47}\Z')
ROLES = {'kafka', 'spark', 'es', 'control', 'app'}
ZK_TLS_PORT = 2281
STAGES = ('preflight', 'common', 'kafka', 'zookeeper', 'spark', 'es', 'control', 'health', 'smoke', 'connectors', 'pipeline', 'ha', 'all')
SECRET_KEYS = ('KAFKA_BROKER_PASSWORD', 'KAFKA_ADMIN_PASSWORD', 'KAFKA_PIPELINE_PASSWORD', 'SPARK_AUTH_SECRET', 'ZK_HA_PASSWORD', 'ES_ADMIN_PASSWORD', 'ES_WRITER_PASSWORD', 'TLS_STORE_PASSWORD')


def load_env(path):
    result = {}
    for number, line in enumerate(Path(path).read_text(encoding='utf-8').splitlines(), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        key, sep, value = line.partition('=')
        if not sep or not re.fullmatch(r'[A-Z][A-Z0-9_]*', key) or key in result:
            raise ValueError(f'Invalid/duplicate env key at line {number}')
        if any(x in value for x in ('\x00', '\r', '\n')):
            raise ValueError(f'Invalid value: {key}')
        result[key] = value
    return result


def private_ip(value):
    try:
        ip = ipaddress.ip_address(value)
        return ip.version == 4 and any(ip in ipaddress.ip_network(x) for x in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))
    except ValueError:
        return False


def memory_mib(value):
    if not isinstance(value, str) or not re.fullmatch(r'[1-9][0-9]*[gm]', value):
        raise ValueError('Memory must use integer g or m units')
    return int(value[:-1]) * (1024 if value[-1] == 'g' else 1)


def load(env_path, inventory_path, strict=True, stage='all'):
    env = load_env(env_path)
    inventory = json.loads(Path(inventory_path).read_text(encoding='utf-8'))
    mode = env.get('ENVIRONMENT')
    if mode not in ('local', 'aws') or inventory.get('environment') != mode:
        raise ValueError('Environment mismatch; expected local or aws')
    if stage not in STAGES:
        raise ValueError('Unknown stage')
    names, addresses = set(), set()
    for node in inventory['nodes']:
        name, roles = node['name'], node['roles']
        if not NAME.fullmatch(name) or name in names:
            raise ValueError(f'Invalid/duplicate node name: {name}')
        names.add(name)
        if not roles or not set(roles) <= ROLES or len(set(roles)) != len(roles) or len(set(roles) & {'kafka', 'spark', 'es'}) > 1:
            raise ValueError(f'Invalid roles: {name}')
        if not private_ip(node['address']) or node['address'] in addresses:
            raise ValueError(f'Invalid/duplicate private IPv4: {name}')
        addresses.add(node['address'])
        ssh = node.get('ssh', {})
        if mode == 'local' and (not re.fullmatch(r'[a-z_][a-z0-9_-]*', ssh.get('user', '')) or not re.fullmatch(r'[A-Za-z0-9._-]+', ssh.get('host', node['address']))):
            raise ValueError(f'Valid SSH host/user required: {name}')
        domain = node.get('physical_host' if mode == 'local' else 'az', '')
        if not isinstance(domain, str) or not NAME.fullmatch(domain):
            raise ValueError(f'Failure domain required: {name}')
        for key in ('cpu', 'memory_mib', 'min_free_disk_gib'):
            if type(node.get(key)) is not int or node[key] < 1:
                raise ValueError(f'Positive integer {key} required: {name}')
        if 'kafka' in roles and memory_mib(node.get('heap', '2g')) > node['memory_mib'] // 2:
            raise ValueError(f'Kafka heap exceeds RAM budget: {name}')
        if 'spark' in roles:
            if type(node.get('worker_cores')) is not int or not 1 <= node['worker_cores'] <= node['cpu']:
                raise ValueError(f'Invalid worker_cores: {name}')
            reserve = node.get('reserved_memory_mib', 0)
            if type(reserve) is not int or reserve < 1536 or memory_mib(node['worker_memory']) + reserve > node['memory_mib']:
                raise ValueError(f'Worker memory exceeds reserved budget: {name}')
        if 'es' in roles and memory_mib(node['es_heap']) > node['memory_mib'] // 2:
            raise ValueError(f'ES heap exceeds half of RAM: {name}')
    groups = {r: [n for n in inventory['nodes'] if r in n['roles']] for r in ROLES}
    if len(groups['kafka']) != 3 or sorted(n.get('id', -1) for n in groups['kafka']) != [1, 2, 3]:
        raise ValueError('Kafka contract: 3 broker+controller nodes, IDs 1,2,3')
    for role in ('kafka', 'spark', 'es'):
        field = 'physical_host' if mode == 'local' else 'az'
        if len(groups[role]) != 3 or len({n[field] for n in groups[role]}) != 3:
            raise ValueError(f'Spread three {role} nodes over three failure domains')
    if sorted(n.get('zk_id', -1) for n in groups['spark']) != [1, 2, 3]:
        raise ValueError('ZooKeeper IDs must be 1,2,3 on Spark nodes')
    controls = groups['control']
    if controls:
        field = 'physical_host' if mode == 'local' else 'az'
        if len(controls) != 2 or controls[0][field] == controls[1][field]:
            raise ValueError('Two Controls in different failure domains required')
        if mode == 'local' and any('spark' not in n['roles'] for n in controls):
            raise ValueError('Local Controls must share Spark VMs')
        if mode == 'aws' and any(set(n['roles']) & {'kafka', 'spark', 'es'} for n in controls):
            raise ValueError('AWS Controls must be separate EC2s')
    if strict:
        required = set()
        if stage == 'common':
            required.add('KAFKA_CLUSTER_ID')
        if stage in ('kafka', 'health', 'smoke', 'all', 'pipeline', 'ha'):
            required.update(('KAFKA_CLUSTER_ID', 'KAFKA_BROKER_PASSWORD', 'KAFKA_ADMIN_PASSWORD', 'KAFKA_PIPELINE_PASSWORD', 'TLS_STORE_PASSWORD'))
        if stage in ('spark', 'zookeeper', 'smoke', 'all', 'pipeline', 'ha'):
            required.update(('SPARK_AUTH_SECRET', 'ZK_HA_PASSWORD', 'TLS_STORE_PASSWORD'))
        if stage in ('es', 'health', 'smoke', 'all', 'pipeline', 'ha'):
            required.update(('ES_ADMIN_PASSWORD', 'ES_WRITER_PASSWORD'))
        for key in required:
            value = env.get(key, '')
            pattern = r'[A-Za-z0-9_-]{22}' if key == 'KAFKA_CLUSTER_ID' else r'[A-Za-z0-9_-]{24,}'
            if not re.fullmatch(pattern, value) or value.startswith(('REPLACE', 'CHANGE')):
                raise ValueError(f'Initialize runtime identity/secret: {key}')
        if stage in ('pipeline', 'ha'):
            region, bucket, prefix = (env.get(k, '') for k in ('AWS_REGION', 'S3_BUCKET', 'S3_CHECKPOINT_PREFIX'))
            if not re.fullmatch(r'[a-z]{2}(?:-[a-z]+)+-\d', region) or not re.fullmatch(r'[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]', bucket) or bucket.startswith('REPLACE'):
                raise ValueError('Fill valid S3 region/bucket')
            if not re.fullmatch(r'[A-Za-z0-9/_-]+', prefix) or '..' in prefix or mode not in prefix.split('/'):
                raise ValueError('Checkpoint prefix must contain the environment as a path component')
        if stage == 'ha':
            raise ValueError('HA activation requires supplied and tested application lifecycle and fencing configuration')
    return {'env': env, 'inventory': inventory, 'groups': groups}


def runtime(config, name):
    node = next(n for n in config['inventory']['nodes'] if n['name'] == name)
    g, e = config['groups'], config['env']
    keys = {'ENVIRONMENT', 'KAFKA_CLUSTER_ID', 'AWS_REGION', 'S3_BUCKET', 'S3_CHECKPOINT_PREFIX'}
    if 'kafka' in node['roles']:
        keys.update(('KAFKA_BROKER_PASSWORD', 'KAFKA_ADMIN_PASSWORD', 'KAFKA_PIPELINE_PASSWORD', 'TLS_STORE_PASSWORD'))
    if set(node['roles']) & {'spark', 'control'}:
        keys.update(('SPARK_AUTH_SECRET', 'ZK_HA_PASSWORD', 'TLS_STORE_PASSWORD', 'KAFKA_PIPELINE_PASSWORD', 'ES_WRITER_PASSWORD'))
    if 'es' in node['roles']:
        keys.update(('ES_ADMIN_PASSWORD', 'ES_WRITER_PASSWORD'))
    return {'node': node, 'inventory': config['inventory'], 'env': {k: e[k] for k in keys if k in e}, 'versions': json.loads((ROOT / 'versions.json').read_text()), 'derived': {
        'kafka_bootstrap': ','.join(f"{n['address']}:9092" for n in g['kafka']),
        'kraft_voters': ','.join(f"{n['id']}@{n['address']}:9093" for n in g['kafka']),
        'spark_master': 'spark://' + ','.join(f"{n['address']}:7077" for n in g['spark']),
        'zk_connect': ','.join(f"{n['address']}:{ZK_TLS_PORT}" for n in g['spark']),
        'es_urls': [f"https://{n['address']}:9200" for n in g['es']]}}


def write_private(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        stream.write(text)


def init(output):
    out = Path(output)
    if out.exists() or out.with_suffix('.inventory.json').exists():
        raise ValueError('Configuration exists; refusing overwrite')
    env = load_env(ROOT / 'config/local.env.example')
    env['KAFKA_CLUSTER_ID'] = base64.urlsafe_b64encode(secrets.token_bytes(16)).decode().rstrip('=')
    for key in SECRET_KEYS:
        env[key] = secrets.token_urlsafe(32)
    write_private(out, '# Literal data; do not source this file.\n' + ''.join(f'{k}={v}\n' for k, v in env.items()))
    write_private(out.with_suffix('.inventory.json'), (ROOT / 'config/local.inventory.json').read_text())
    print('Private local configuration created; values are not printed.')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='action', required=True)
    s = sub.add_parser('init'); s.add_argument('--output', required=True)
    for action in ('validate', 'plan', 'render'):
        s = sub.add_parser(action)
        s.add_argument('--env', required=True); s.add_argument('--inventory', required=True)
        s.add_argument('--stage', choices=STAGES, default='preflight')
        if action == 'render':
            s.add_argument('--node', required=True); s.add_argument('--output', required=True)
    s = sub.add_parser('get'); s.add_argument('runtime'); s.add_argument('path')
    a = p.parse_args()
    if a.action == 'init': init(a.output)
    elif a.action == 'get':
        value = json.loads(Path(a.runtime).read_text())
        for part in a.path.split('.'): value = value[int(part)] if isinstance(value, list) else value[part]
        print(json.dumps(value) if isinstance(value, (list, dict, bool)) else value)
    else:
        c = load(a.env, a.inventory, strict=a.action != 'plan', stage=a.stage)
        if a.action == 'render': write_private(a.output, json.dumps(runtime(c, a.node), indent=2) + '\n')
        elif a.action == 'plan':
            for n in c['inventory']['nodes']: print(f"{n['name']:16} {n['address']:20} {','.join(n['roles'])}")
            print('Plan only: no connections or mutations.')
        else: print(f'Configuration validation PASS: {a.stage} (no secrets printed)')


if __name__ == '__main__':
    try: main()
    except (ValueError, KeyError, TypeError, StopIteration, OSError) as error:
        print(f'[FAIL] {error}', file=sys.stderr); sys.exit(1)
