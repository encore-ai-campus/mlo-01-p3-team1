"""Strict live SSM/Spark observations. Historical receipts cannot authorize HA."""
from concurrent.futures import ThreadPoolExecutor
import json
import time
import uuid

from control_fencing import FencingError


class SsmSparkSource:
    def __init__(self, aws_for_node, require_lease, timeout=75, interval=1, clock=time.time, monotonic=time.monotonic, sleep=time.sleep):
        self.aws_for_node, self.require_lease = aws_for_node, require_lease
        self.timeout, self.interval, self.clock, self.monotonic, self.sleep = timeout, interval, clock, monotonic, sleep

    def observe(self, node):
        aws = self.aws_for_node(node)
        nonce = uuid.uuid4().hex
        self.require_lease()
        command = aws.call('ssm', 'send-command', '--instance-ids', node['instance_id'],
            '--document-name', node['observer_document'], '--document-version', node['observer_document_version'],
            '--document-hash', node['observer_document_hash'], '--document-hash-type', 'Sha256',
            '--parameters', json.dumps({'ObservationNonce': [nonce]}), '--timeout-seconds', '60')['Command']
        command_id = command['CommandId']
        deadline = self.monotonic() + self.timeout
        while True:
            self.require_lease()
            values = aws.call('ssm', 'list-command-invocations', '--command-id', command_id,
                '--instance-id', node['instance_id'], '--details')['CommandInvocations']
            if len(values) > 1:
                raise FencingError('Ambiguous live SSM observation')
            if values:
                value = values[0]
                if value['CommandId'] != command_id or value['InstanceId'] != node['instance_id']:
                    raise FencingError('Live SSM command/instance identity differs')
                if value['Status'] == 'Success':
                    plugins = value['CommandPlugins']
                    if len(plugins) != 1 or plugins[0]['Status'] != 'Success':
                        raise FencingError('All observer document steps must succeed')
                    detail = aws.call('ssm', 'get-command-invocation', '--command-id', command_id,
                        '--instance-id', node['instance_id'], '--plugin-name', plugins[0]['Name'])
                    if (detail.get('CommandId') != command_id or detail.get('InstanceId') != node['instance_id'] or
                        detail.get('Status') != 'Success' or detail.get('ResponseCode') != 0):
                        raise FencingError('Spark observer did not complete successfully')
                    snapshot = json.loads(detail['StandardOutputContent'])
                    if snapshot.get('nonce') != nonce:
                        raise FencingError('Stale/replayed Spark observation')
                    self.require_lease()
                    return snapshot
                if value['Status'] not in ('Pending', 'InProgress', 'Delayed'):
                    raise FencingError('Live Spark observation failed; never resubmit an unknown command')
            if self.monotonic() >= deadline:
                raise FencingError('Live Spark observation timed out; promotion blocked')
            self.sleep(self.interval)


class SparkIdleObserver:
    """Conservative policy: every Master/Worker must be observed globally idle.

    It intentionally refuses promotion while another query is active. Selective
    concurrent-query fencing requires a separate immutable app ownership contract.
    """
    def __init__(self, members, source, namespace, max_age=90, clock=time.time):
        self.members, self.source, self.namespace = members, source, namespace
        self.max_age, self.clock = max_age, clock
        if (len(members) != 3 or {n['node'] for n in members} != {'spark-01', 'spark-02', 'spark-03'} or
            len({n['instance_id'] for n in members}) != 3 or len({n['private_ip'] for n in members}) != 3):
            raise FencingError('Exactly three distinct configured Spark nodes are required')

    def confirm_idle(self, owner):
        if owner.namespace != self.namespace:
            raise FencingError('Spark observation owner namespace differs')
        with ThreadPoolExecutor(max_workers=3) as pool:
            snapshots = list(pool.map(self.source.observe, self.members))
        by_host = {}
        for expected, snapshot in zip(self.members, snapshots):
            fields = ('project', 'environment', 'generation', 'node', 'instance_id', 'account_id', 'private_ip', 'region')
            if snapshot.get('schema') != 1 or any(snapshot.get(k) != expected[k] for k in fields):
                raise FencingError('Spark observation membership/generation differs')
            observed = snapshot.get('observed_at')
            if type(observed) not in (int, float) or not 0 <= self.clock() - observed <= self.max_age:
                raise FencingError('Spark observation is stale or from the future')
            master, worker = snapshot['master'], snapshot['worker']
            if master['url'] != 'spark://' + expected['private_ip'] + ':7077':
                raise FencingError('Master identity differs')
            for field in ('activeapps', 'activedrivers'):
                if not isinstance(master.get(field), list) or master[field]:
                    raise FencingError('Active/unknown Spark applications or Drivers remain')
            if not isinstance(worker.get('executors'), list) or worker['executors']:
                raise FencingError('Active/unknown Worker executors remain')
            for data in (master, worker):
                if any(type(data.get(k)) is not int or data[k] != 0 for k in ('coresused', 'memoryused')):
                    raise FencingError('Spark allocated resources remain or cannot be observed')
            if worker.get('resourcesused') != {}:
                raise FencingError('Worker custom resource state is not empty')
            counts = snapshot.get('workload_process_counts')
            if (not isinstance(counts, dict) or set(counts) != {'executor', 'driver', 'python_worker'} or
                any(type(v) is not int or v != 0 for v in counts.values())):
                raise FencingError('Orphan/unknown Spark workload processes remain')
            by_host[expected['private_ip']] = snapshot
        masters = [s['master'] for s in snapshots]
        if sorted(m['status'] for m in masters) != ['ALIVE', 'STANDBY', 'STANDBY']:
            raise FencingError('No unique Spark Master leader observed')
        active = next(m for m in masters if m['status'] == 'ALIVE')
        if active.get('aliveworkers') != 3 or not isinstance(active.get('workers'), list) or len(active['workers']) != 3:
            raise FencingError('All three registered Workers must be alive')
        if {w.get('host') for w in active['workers']} != set(by_host):
            raise FencingError('Registered Worker membership differs')
        for worker in active['workers']:
            local = by_host[worker['host']]['worker']
            if worker.get('state') != 'ALIVE' or local.get('id') != worker.get('id') or local.get('masterurl') != active['url']:
                raise FencingError('Master/Worker live membership disagrees')
        return True
