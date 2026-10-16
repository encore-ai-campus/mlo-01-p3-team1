#!/usr/bin/env python3
"""Immutable identity guards for data-bearing services."""
import json
import hashlib
import os
from pathlib import Path
import sys


def preserve(path, identity):
    path = Path(path)
    if path.exists():
        if json.loads(path.read_text()) != identity:
            raise ValueError('Stored identity differs; refusing to repurpose existing service data')
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as f:
        json.dump(identity, f, sort_keys=True)


def kafka_metadata(path, cluster_id, node_id):
    values = {}
    for line in Path(path).read_text().splitlines():
        if '=' in line and not line.startswith('#'):
            key, value = line.split('=', 1); values[key] = value
    if values.get('cluster.id') != cluster_id or values.get('node.id') != str(node_id):
        raise ValueError('Kafka disk cluster/node identity mismatch; never reformat this disk')


if __name__ == '__main__':
    try:
        c = json.loads(Path(sys.argv[1]).read_text())
        n, e = c['node'], c['env']
        if sys.argv[2] == 'identity':
            identity = {'node': n['name'], 'environment': e['ENVIRONMENT']}
            if 'kafka' in n['roles']:
                identity.update(cluster_id=e['KAFKA_CLUSTER_ID'], node_id=n['id'])
            preserve(sys.argv[3], identity)
        elif sys.argv[2] == 'kafka':
            kafka_metadata(sys.argv[3], e['KAFKA_CLUSTER_ID'], n['id'])
        elif sys.argv[2] == 'secrets':
            role = sys.argv[4]
            fields = {
                'kafka': ('KAFKA_BROKER_PASSWORD', 'KAFKA_ADMIN_PASSWORD', 'KAFKA_PIPELINE_PASSWORD', 'TLS_STORE_PASSWORD'),
                'zookeeper': ('ZK_HA_PASSWORD',),
                'spark': ('SPARK_AUTH_SECRET', 'ZK_HA_PASSWORD', 'TLS_STORE_PASSWORD', 'KAFKA_PIPELINE_PASSWORD', 'ES_WRITER_PASSWORD'),
                'elasticsearch': ('ES_ADMIN_PASSWORD', 'ES_WRITER_PASSWORD'),
            }[role]
            fingerprint = hashlib.sha256(json.dumps({k: e[k] for k in fields}, sort_keys=True).encode()).hexdigest()
            preserve(sys.argv[3], {'role': role, 'secret_fingerprint': fingerprint})
        else: raise ValueError('Unknown state operation')
    except (OSError, ValueError, KeyError) as error:
        print('[FAIL] ' + str(error), file=sys.stderr); sys.exit(1)
