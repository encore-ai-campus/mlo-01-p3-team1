#!/usr/bin/env python3
"""Read-only, bounded local Spark observation for a custom SSM document.

No command, URL, filename or shell fragment comes from a document parameter.
The expected identity is fixed by the reviewed document; only a nonce varies.
"""
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.request import Request, build_opener, ProxyHandler


def identity():
    opener = build_opener(ProxyHandler({}))
    base = 'http://169.254.169.254/latest/'
    with opener.open(Request(base + 'api/token', method='PUT',
        headers={'X-aws-ec2-metadata-token-ttl-seconds': '60'}), timeout=5) as response:
        token = response.read().decode()
    with opener.open(Request(base + 'dynamic/instance-identity/document',
        headers={'X-aws-ec2-metadata-token': token}), timeout=5) as response:
        return json.load(response)


def local_json(address, port):
    opener = build_opener(ProxyHandler({}))
    with opener.open('http://' + address + ':' + str(port) + '/json/', timeout=5) as response:
        raw = response.read(262145)
    if len(raw) > 262144:
        raise ValueError('Spark observation exceeds the bounded response size')
    return json.loads(raw)


def collect(expected, nonce, fetch=identity, http=local_json,
            marker=Path('/var/lib/music-cluster/.aws-volume-identity.json'), proc=Path('/proc'), clock=time.time):
    if not re.fullmatch(r'[0-9a-f]{32}', nonce):
        raise ValueError('A fresh observation nonce is required')
    actual = fetch()
    fields = {'accountId': 'account_id', 'instanceId': 'instance_id', 'privateIp': 'private_ip', 'region': 'region'}
    if any(actual.get(k) != expected[v] for k, v in fields.items()):
        raise ValueError('Spark EC2 IMDS identity differs from the observer document')
    wanted = {k: expected[k] for k in ('project', 'environment', 'generation', 'node')}
    if json.loads(marker.read_text()) != wanted or not re.fullmatch(r'spark-0[1-3]', expected['node']):
        raise ValueError('Mounted Spark data generation differs')
    master = http(expected['private_ip'], 8080)
    worker = http(expected['private_ip'], 8081)
    master_keys = ('url', 'status', 'activeapps', 'activedrivers', 'aliveworkers', 'workers', 'coresused', 'memoryused')
    worker_keys = ('id', 'masterurl', 'executors', 'coresused', 'memoryused', 'resourcesused')
    if not set(master_keys) <= master.keys() or not set(worker_keys) <= worker.keys():
        raise ValueError('Unsupported Spark JSON schema; missing fields are not idle')
    counts = {'executor': 0, 'driver': 0, 'python_worker': 0}
    for path in proc.glob('[0-9]*/cmdline'):
        try:
            command = path.read_bytes().replace(b'\x00', b' ').decode(errors='replace')
        except FileNotFoundError:
            continue  # process exited during this bounded observation
        # Permission/IO errors are deliberately not translated to an empty list.
        for kind, names in {
            'executor': ('CoarseGrainedExecutorBackend',),
            'driver': ('org.apache.spark.deploy.worker.DriverWrapper', 'org.apache.spark.deploy.SparkSubmit'),
            'python_worker': ('pyspark.worker', 'pyspark.daemon'),
        }.items():
            counts[kind] += int(any(name in command for name in names))
    return {'schema': 1, **expected, 'nonce': nonce, 'observed_at': clock(),
            'master': {k: master[k] for k in master_keys}, 'worker': {k: worker[k] for k in worker_keys},
            'workload_process_counts': counts}


if __name__ == '__main__':
    if sys.platform != 'linux' or os.geteuid() != 0:
        raise SystemExit('Read-only Spark observer requires SSM Linux root')
    # Expected JSON is emitted as a fixed literal by CloudFormation. It is not
    # accepted as an arbitrary document command/path parameter.
    print(json.dumps(collect(json.loads(sys.argv[1]), sys.argv[2])))
