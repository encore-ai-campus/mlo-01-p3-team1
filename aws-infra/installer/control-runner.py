#!/usr/bin/env python3
"""Explicit Control bootstrap/inspection/supervision; no automatic activation."""
import argparse
from dataclasses import asdict
import importlib.util
import json
import os
from pathlib import Path
import signal
import sys
import threading
import time

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'fencing' if (ROOT / 'fencing').is_dir() else ROOT.parent / 'lib'))
from control_aws import InstanceAws
from control_coordinator import ZkCoordinator, authenticated_client, provision
from control_fencing import FencingError, Owner, authorize
from control_observation import SparkIdleObserver, SsmSparkSource
from control_runtime import Ec2Fence, LiveBackend, Workload, supervise


def checked_runtime(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
        raise FencingError('Private, non-symlink runtime mode 0600 required')
    if sys.platform != 'linux':
        raise FencingError('Control execution requires its actual Linux EC2 host')
    runtime = json.loads(path.read_text())
    spec = importlib.util.spec_from_file_location('control_identity', ROOT / 'aws-identity.py')
    identity = importlib.util.module_from_spec(spec);spec.loader.exec_module(identity)
    identity.verify(runtime, identity.identity)
    node = runtime['node']
    wanted = {**runtime['aws'], 'node': node['name']}
    if node['role'] != 'control' or json.loads(Path('/var/lib/music-cluster/.aws-volume-identity.json').read_text()) != wanted:
        raise FencingError('Control role/mounted generation differs')
    candidate = Owner(runtime['aws']['project'], runtime['aws']['environment'], runtime['aws']['generation'],
        runtime['fencing']['query'], node['name'], node['instance_id'], 0)
    return runtime, candidate


def run(runtime, candidate, action):
    cfg = runtime['fencing']
    for n in cfg['spark_members']:
        if (not n.get('observer_document_version', '').isdigit() or
            not __import__('re').fullmatch(r'[0-9a-f]{64}', n.get('observer_document_hash', ''))):
            raise FencingError('Actual owner-reviewed SSM document version/hash bindings are required')
    aws = InstanceAws(runtime['env']['AWS_REGION'], cfg['aws_cli'], cfg['aws_cli_version'])
    aws.verify_control(runtime['node']['account_id'], cfg['runtime_role_name'], candidate.instance_id)
    client, acl = authenticated_client(cfg['zk_hosts'], cfg['sasl_password'], cfg['coordinator_password'], cfg['tls'])
    coordinator = ZkCoordinator(client, candidate, acl)
    stop = threading.Event()
    lease = None
    previous_signals = {}
    try:
        client.start(timeout=12)
        if action == 'bootstrap':
            provision(client, candidate, acl)
            return {'coordinator_namespace_validated': True, 'existing_state_reset': False}
        coordinator._state()  # Missing state must never become first boot.
        require = (lambda: coordinator.require_current(lease)) if action == 'supervise' else (lambda: None)
        source = SsmSparkSource(lambda node: aws.observer(node, ':'.join(candidate.namespace[:3]) + ':spark-observe'), require)
        observer = SparkIdleObserver(cfg['spark_members'], source, candidate.namespace)
        if action == 'inspect':
            return {'coordinator_authenticated': True, 'spark_globally_idle': observer.confirm_idle(candidate),
                    'lease_acquired': False, 'workload_started': False}
        workloads = [Workload(tuple(w['argv']), w['cwd']) for w in cfg['workloads']]
        if not workloads:
            raise FencingError('Explicit canary or foreground workload specification required')
        deadline = time.monotonic() + cfg.get('election_wait_seconds', 60)
        while lease is None:
            lease = coordinator.acquire()
            if lease is None:
                if time.monotonic() >= deadline:
                    raise FencingError('Another Control owns the live election; no workload started')
                time.sleep(0.2)
        ec2 = Ec2Fence(aws, candidate, cfg['controls'], runtime['node']['account_id'], runtime['env']['AWS_REGION'], require)
        backend = LiveBackend(coordinator, ec2, observer)
        permit = authorize(lease, backend)
        for kind in (signal.SIGTERM, signal.SIGINT):
            previous_signals[kind] = signal.signal(kind, lambda *_: stop.set())
        return supervise(permit, coordinator, backend, workloads, stop=stop)
    finally:
        for kind, previous in previous_signals.items():
            signal.signal(kind, previous)
        coordinator.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', required=True)
    parser.add_argument('action', choices=('inspect', 'bootstrap', 'supervise'))
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({'action': args.action, 'executed': False,
            'notice': 'supervise can physically stop the exact previous Control; bootstrap writes private ZK coordination state'}))
        return
    runtime, candidate = checked_runtime(args.runtime)
    print(json.dumps(run(runtime, candidate, args.action)))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Detailed configuration and secrets never enter service output.
        sys.exit('[FAIL] Control execution blocked (' + type(error).__name__ + '); ownership retained')
