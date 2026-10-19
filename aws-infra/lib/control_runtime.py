"""EC2 fencing, live adapter composition and foreground process supervision."""
from dataclasses import dataclass
import os
from pathlib import Path
import signal
import subprocess
import threading
import time

from control_fencing import FencingError


class Ec2Fence:
    def __init__(self, aws, candidate, controls, account_id, region, require_lease,
                 timeout=600, interval=3, monotonic=time.monotonic, sleep=time.sleep):
        self.aws, self.candidate, self.controls = aws, candidate, controls
        self.account_id, self.region, self.require_lease = account_id, region, require_lease
        self.timeout, self.interval, self.monotonic, self.sleep = timeout, interval, monotonic, sleep
        if set(controls) != {'control-a', 'control-b'} or len({n['instance_id'] for n in controls.values()}) != 2:
            raise FencingError('Exact, distinct Control A/B identities are required')
        if (controls[candidate.node]['instance_id'] != candidate.instance_id or
            any(n.get('generation') != candidate.generation for n in controls.values())):
            raise FencingError('Candidate is outside the approved Control pair')

    def _identity(self, owner):
        if owner.namespace != self.candidate.namespace or owner.node == self.candidate.node or owner.instance_id == self.candidate.instance_id:
            raise FencingError('Refusing foreign/self EC2 fencing')
        expected = self.controls[owner.node]
        if expected['instance_id'] != owner.instance_id:
            raise FencingError('Previous owner is not the approved peer instance')
        result = self.aws.call('ec2', 'describe-instances', '--instance-ids', owner.instance_id)
        reservations = result.get('Reservations', [])
        if len(reservations) != 1 or reservations[0].get('OwnerId') != self.account_id:
            raise FencingError('Previous Control account is not confirmed')
        instances = reservations[0].get('Instances', [])
        if len(instances) != 1:
            raise FencingError('Previous Control instance is not uniquely observed')
        node = instances[0]
        tags = {t['Key']: t['Value'] for t in node.get('Tags', [])}
        wanted = {'Project': owner.project, 'Environment': owner.environment,
                  'Node': owner.node, 'Role': 'control'}
        terminated = node.get('State', {}).get('Name') == 'terminated'
        # Current EC2s have no Generation tag. Exact instance/ENI IDs come from
        # the reviewed generation mapping; never invent a tag requirement or
        # broaden the stop ARN to a mutable tag wildcard.
        network_ok = ((node.get('PrivateIpAddress') == expected['private_ip'] and node.get('VpcId') == expected['vpc_id'] and
            any(e.get('NetworkInterfaceId') == expected['eni_id'] for e in node.get('NetworkInterfaces', []))) or terminated)
        if (node.get('InstanceId') != owner.instance_id or any(tags.get(k) != v for k, v in wanted.items()) or
            not network_ok or (not terminated and node.get('RootDeviceType') != 'ebs') or
            node.get('Placement', {}).get('AvailabilityZone', '')[:-1] != self.region):
            raise FencingError('Previous Control tags/IP/VPC/root volume/region differ')
        return node['State']['Name']

    def stop_and_confirm_old_instance(self, old):
        self.require_lease()
        state = self._identity(old)
        if state == 'running':
            self.require_lease()
            # Never force-stop, terminate, reboot or start an instance here.
            self.aws.call('ec2', 'stop-instances', '--instance-ids', old.instance_id)
        elif state not in ('stopping', 'stopped', 'terminated'):
            raise FencingError('Previous Control is not in a fenceable state')
        deadline = self.monotonic() + self.timeout
        while True:
            self.require_lease()
            state = self._identity(old)
            if state in ('stopped', 'terminated'):
                self.require_lease()
                return True
            if state not in ('running', 'stopping') or self.monotonic() >= deadline:
                raise FencingError('Old Control stop is uncertain; promotion remains blocked')
            self.sleep(self.interval)


class LiveBackend:
    def __init__(self, coordinator, ec2, spark):
        self.coordinator, self.ec2, self.spark = coordinator, ec2, spark

    def lease_is_current(self, lease):
        return self.coordinator.lease_is_current(lease)

    def previous_owner(self, lease):
        return self.coordinator.previous_owner(lease)

    def stop_and_confirm_old_instance(self, old):
        return self.ec2.stop_and_confirm_old_instance(old)

    def old_spark_work_is_gone(self, old):
        return self.spark.confirm_idle(old)

    def publish_owner_if_current(self, lease):
        # Also reject untracked work during first activation. This conservative
        # implementation requires a globally idle cluster before promotion.
        if self.spark.confirm_idle(lease.owner) is not True:
            return False
        return self.coordinator.publish_owner_if_current(lease)


@dataclass(frozen=True)
class Workload:
    argv: tuple[str, ...]
    cwd: str

    def __post_init__(self):
        if not self.argv or not all(isinstance(v, str) and '\x00' not in v for v in self.argv):
            raise FencingError('Structured foreground argv is required')
        if not Path(self.argv[0]).is_absolute() or not Path(self.cwd).is_absolute():
            raise FencingError('Absolute executable and working directory are required')
        if Path(self.argv[0]).name in ('sh', 'bash', 'dash', 'zsh', 'fish'):
            raise FencingError('Shell command strings are not a workload contract')
        for index, value in enumerate(self.argv):
            if value == '--deploy-mode' and (index + 1 >= len(self.argv) or self.argv[index + 1] != 'client'):
                raise FencingError('Detached/cluster Spark Drivers are not supported')
        if any(v.startswith('--deploy-mode=') and v != '--deploy-mode=client' for v in self.argv):
            raise FencingError('Detached/cluster Spark Drivers are not supported')


def group_alive(pgid):
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # Unobservable/uncontrollable groups must retain ownership.


def stop_group(process, grace=3, final_wait=3):
    """Kill the entire process group even when its leader already exited."""
    for sig, wait in ((signal.SIGTERM, grace), (signal.SIGKILL, final_wait)):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            pass
        except PermissionError:
            return False
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:
            process.poll()  # reap the leader; a live child group still blocks
            if not group_alive(process.pid):
                return True
            time.sleep(0.05)
    return not group_alive(process.pid)


def supervise(permit, coordinator, backend, workloads, stop=None, poll_interval=0.2, grace=3):
    """A suspension stops local groups immediately and retains persistent owner.

    The systemd service must additionally use KillMode=control-group so children
    cannot escape through daemonization. External/cluster-mode Drivers are refused.
    """
    if not workloads:
        raise FencingError('At least one explicit foreground workload is required')
    stop = stop or threading.Event()
    invalid = threading.Event()
    finished = threading.Event()
    processes = []
    monitor = None
    released = False

    def watch():
        while not finished.wait(poll_interval):
            try:
                permit.assert_current()
            except Exception:
                invalid.set()
                return

    try:
        permit.assert_current()
        for workload in workloads:
            if coordinator.lost.is_set() or invalid.is_set():
                raise FencingError('Lease lost before workload start')
            permit.assert_current()
            env = os.environ.copy()
            env.update(MUSIC_CONTROL_EPOCH=str(permit.lease.owner.epoch),
                       MUSIC_CONTROL_QUERY=permit.lease.owner.query,
                       MUSIC_CONTROL_GENERATION=permit.lease.owner.generation)
            processes.append(subprocess.Popen(list(workload.argv), cwd=workload.cwd, env=env,
                stdin=subprocess.DEVNULL, start_new_session=True, close_fds=True))
        monitor = threading.Thread(target=watch, daemon=True, name='control-lease-watch')
        monitor.start()
        while not stop.wait(poll_interval):
            if coordinator.lost.is_set() or invalid.is_set():
                raise FencingError('Lease suspended/lost; workload termination required')
            if any(p.poll() is not None for p in processes):
                break
    finally:
        # The connection callback's event remains independent of a blocked
        # synchronous ZK observation in the monitoring thread.
        terminated = all([stop_group(p, grace=grace) for p in processes])
        finished.set()
        if monitor is not None:
            monitor.join(timeout=1)
        if terminated and not coordinator.lost.is_set() and not invalid.is_set():
            try:
                permit.assert_current()
                coordinator.release_after_termination(permit.lease, backend.old_spark_work_is_gone)
                released = True
            except Exception:
                # Keep ownership. The peer must physically fence this instance
                # before starting; never turn uncertainty into an empty owner.
                pass
        if not terminated:
            raise FencingError('A workload process group remains; persistent owner retained')
    return {'local_groups_terminated': True, 'owner_released': released,
            'lease_lost': coordinator.lost.is_set() or invalid.is_set()}
