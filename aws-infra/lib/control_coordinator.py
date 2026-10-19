"""Authenticated ZooKeeper election and versioned persistent Control ownership.

Connection suspension is terminal for this client, even if its session reconnects.
No path, epoch, owner or checkpoint is automatically reset on retry.
"""
from dataclasses import asdict, replace
import json
import re
import threading
import uuid

from control_fencing import FencingError, Lease, Owner


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def coordinator_path(owner):
    return '/music-cluster/aws/control/' + '/'.join(owner.namespace)


def authenticated_client(hosts, sasl_password, coordinator_password, tls):
    """TLS verifies the server name; SASL is required by the existing ensemble.

    The additional digest identity owns a separate ACL. Spark's SASL identity
    alone does not grant access to this subtree. Secrets are never logged.
    """
    from kazoo.client import KazooClient
    from kazoo.security import make_digest_acl
    if len(hosts) != 3 or len(set(hosts)) != 3 or not sasl_password or len(coordinator_password) < 32:
        raise FencingError('Three TLS endpoints and independent coordinator credentials required')
    acl = [make_digest_acl('control', coordinator_password, all=True)]
    client = KazooClient(hosts=','.join(hosts), timeout=8, use_ssl=True,
        verify_certs=True, check_hostname=True, ca=tls['ca'], certfile=tls['certificate'], keyfile=tls['key'],
        read_only=False, default_acl=acl,
        sasl_options={'mechanism': 'DIGEST-MD5', 'username': 'cluster', 'password': sasl_password},
        auth_data=[('digest', 'control:' + coordinator_password)],
        connection_retry={'max_tries': 2, 'delay': 0.2, 'max_delay': 1},
        command_retry={'max_tries': 1})
    return client, acl


def provision(client, owner, acl):
    """Explicit bootstrap only; existing state must match and is never replaced."""
    from kazoo.exceptions import NodeExistsError
    root = coordinator_path(owner)
    # Parents are created only when absent, with the same private ACL.
    client.ensure_path(root, acl=acl)
    scope = list(owner.namespace)
    initial = {
        root: {'schema': 1, 'scope': scope},
        root + '/queue': {'schema': 1, 'scope': scope},
        root + '/epoch': {'schema': 1, 'value': 0},
        root + '/owner': {'schema': 1, 'scope': scope, 'active': None, 'last': None},
    }
    for path, data in initial.items():
        try:
            # ensure_path already created root; initialize its initially empty
            # value only through a version check and never overwrite an owner.
            if path == root:
                current, stat = client.get(path)
                if current == b'' and stat.version == 0:
                    client.set(path, encode(data), version=0)
            else:
                client.create(path, encode(data), acl=acl)
        except NodeExistsError:
            pass
        actual_acl, _ = client.get_acls(path)
        if actual_acl != acl:
            raise FencingError('Coordinator ACL differs; explicit repair required')
        current, _ = client.get(path)
        decoded = json.loads(current)
        if path in (root, root + '/queue') and decoded != data:
            raise FencingError('Coordinator namespace differs')
    # Validate existing mutable state without changing it.
    ZkCoordinator(client, owner, acl)._state()


class ZkCoordinator:
    def __init__(self, client, candidate, acl):
        if candidate.epoch != 0:
            raise FencingError('Candidate epoch must be allocated by ZooKeeper')
        self.client, self.candidate, self.acl = client, candidate, acl
        self.root = coordinator_path(candidate)
        self.nonce = uuid.uuid4().hex
        self.path = None
        self.lease = None
        self.previous = None
        self.lost = threading.Event()
        self._connected_once = bool(client.connected)
        client.add_listener(self._connection_state)

    def _connection_state(self, state):
        if state == 'CONNECTED':
            self._connected_once = True
        elif self._connected_once:
            # Never revive a permit after SUSPENDED/LOST.
            self.lost.set()

    def _connected(self):
        if self.lost.is_set() or self.client.connected is not True:
            raise FencingError('Coordinator connection is unavailable or previously suspended')

    def _read(self, suffix):
        data, stat = self.client.get(self.root + suffix)
        actual, _ = self.client.get_acls(self.root + suffix)
        if actual != self.acl or stat.ephemeralOwner != 0:
            raise FencingError('Persistent coordinator state/ACL differs')
        return json.loads(data), stat

    def _owner(self, data):
        if data is None:
            return None
        try:
            owner = Owner(**data)
        except (TypeError, ValueError) as error:
            raise FencingError('Invalid persistent owner') from error
        if owner.namespace != self.candidate.namespace or owner.epoch <= 0:
            raise FencingError('Persistent owner namespace/epoch differs')
        return owner

    def _state(self):
        self._connected()
        self.client.sync(self.root)
        epoch, epoch_stat = self._read('/epoch')
        record, owner_stat = self._read('/owner')
        if set(epoch) != {'schema', 'value'} or epoch['schema'] != 1 or type(epoch['value']) is not int or epoch['value'] < 0:
            raise FencingError('Invalid coordinator epoch')
        if set(record) != {'schema', 'scope', 'active', 'last'} or record['schema'] != 1 or record['scope'] != list(self.candidate.namespace):
            raise FencingError('Invalid coordinator owner record')
        active, last = self._owner(record['active']), self._owner(record['last'])
        if any(o.epoch > epoch['value'] for o in (active, last) if o is not None):
            raise FencingError('Owner is newer than the coordinator epoch')
        if active is None and last is None and epoch['value'] != 0 and self.path is None:
            # An allocated but unpublished attempt is legitimate. Its epoch
            # remains consumed; an empty owner never authorizes old work.
            pass
        return epoch, epoch_stat, record, owner_stat

    def _first(self):
        children = self.client.get_children(self.root + '/queue')
        entries = []
        for name in children:
            match = re.fullmatch(r'([0-9a-f]{32})-candidate-([0-9]{10})', name)
            if match is None or int(match[2]) > 2147483647:
                raise FencingError('Unknown/wrapped election sequence; explicit review required')
            entries.append((int(match[2]), name))
        return min(entries)[1] if entries else None

    def _candidate_current(self):
        self._connected()
        self.client.sync(self.root)
        if not self.path or self._first() != self.path.rsplit('/', 1)[1]:
            return False
        data, stat = self.client.get(self.path)
        expected = {'candidate': asdict(self.candidate), 'nonce': self.nonce}
        return (json.loads(data) == expected and stat.version == 0 and
                stat.ephemeralOwner == self.client.client_id[0] and stat.ephemeralOwner != 0)

    def acquire(self):
        self._connected()
        if self.lease is not None:
            if not self.lease_is_current(self.lease):
                raise FencingError('Acquired lease is no longer current')
            return self.lease
        self._state()
        if self.path is None:
            # No automatic create retry: a lost response can have created an
            # ephemeral. Closing the session removes it; never create a twin.
            self.path = self.client.create(self.root + '/queue/' + self.nonce + '-candidate-',
                encode({'candidate': asdict(self.candidate), 'nonce': self.nonce}),
                ephemeral=True, sequence=True, acl=self.acl)
        if not self._candidate_current():
            return None
        epoch, stat, _, _ = self._state()
        request = self.client.transaction()
        request.check(self.path, version=0)
        request.check(self.root + '/epoch', version=stat.version)
        request.set_data(self.root + '/epoch', encode({'schema': 1, 'value': epoch['value'] + 1}), version=stat.version)
        if any(isinstance(r, Exception) for r in request.commit()):
            self.lost.set()
            raise FencingError('Coordinator epoch transaction failed; do not retry the mutation')
        self.lease = Lease(replace(self.candidate, epoch=epoch['value'] + 1), self.nonce)
        if not self.lease_is_current(self.lease):
            raise FencingError('Lease lost during epoch allocation')
        return self.lease

    def lease_is_current(self, lease):
        try:
            if lease != self.lease or lease.nonce != self.nonce or not self._candidate_current():
                return False
            epoch, _, _, _ = self._state()
            return epoch['value'] == lease.owner.epoch
        except Exception:
            self.lost.set()
            return False

    def require_current(self, lease):
        if self.lease_is_current(lease) is not True:
            raise FencingError('Coordinator lease is not current')

    def previous_owner(self, lease):
        self.require_current(lease)
        _, _, record, stat = self._state()
        self.previous = (record, stat.version)
        return self._owner(record['active'])

    def _publish(self, lease, value, owner_version):
        self.require_current(lease)
        epoch, stat, _, _ = self._state()
        if epoch['value'] != lease.owner.epoch:
            return False
        transaction = self.client.transaction()
        transaction.check(self.path, version=0)
        transaction.check(self.root + '/epoch', version=stat.version)
        transaction.check(self.root + '/owner', version=owner_version)
        transaction.set_data(self.root + '/owner', encode(value), version=owner_version)
        return not any(isinstance(r, Exception) for r in transaction.commit())

    def publish_owner_if_current(self, lease):
        if self.previous is None:
            raise FencingError('A fresh previous-owner read is required')
        record, version = self.previous
        updated = {**record, 'active': asdict(lease.owner), 'last': record['active'] or record['last']}
        return self._publish(lease, updated, version)

    def release_after_termination(self, lease, observe_termination):
        """Caller supplies a live observation, not an operator/receipt boolean."""
        self.require_current(lease)
        if observe_termination(lease.owner) is not True:
            raise FencingError('Termination uncertain; persistent ownership is retained')
        self.require_current(lease)
        _, _, record, stat = self._state()
        if self._owner(record['active']) != lease.owner:
            raise FencingError('Persistent owner changed before release')
        if not self._publish(lease, {**record, 'active': None, 'last': asdict(lease.owner)}, stat.version):
            raise FencingError('Owner release CAS failed; do not clear state manually')

    def close(self):
        # Persistent /owner and /epoch survive this session.
        self.lost.set()
        self.client.stop()
        self.client.close()
