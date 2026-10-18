"""Fail-closed promotion gate; live ZooKeeper/EC2/Spark adapters are required.

This gate neither starts a workload nor claims a deployed HA controller. The
caller must supervise its lease throughout execution and terminate on loss.
Only a fresh, authenticated coordinator lease plus confirmed old-instance and
executor fencing can authorize a new owner. JSON receipts are not live proof.
"""
from dataclasses import dataclass
from typing import Protocol
import re


class FencingError(RuntimeError):
    pass


@dataclass(frozen=True)
class Owner:
    project: str
    environment: str
    generation: str
    query: str
    node: str
    instance_id: str
    epoch: int

    def __post_init__(self):
        for value in (self.project, self.environment, self.generation, self.query):
            if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,95}', value):
                raise FencingError('Invalid owner namespace')
        if self.node not in ('control-a', 'control-b') or not re.fullmatch(r'i-[0-9a-f]{8,17}', self.instance_id):
            raise FencingError('Control node/instance identity required')
        if type(self.epoch) is not int or self.epoch < 0:
            raise FencingError('Nonnegative coordinator epoch required')

    @property
    def namespace(self):
        return self.project, self.environment, self.generation, self.query


@dataclass(frozen=True)
class Lease:
    owner: Owner
    nonce: str

    def __post_init__(self):
        if not re.fullmatch(r'[0-9a-f]{32}', self.nonce):
            raise FencingError('Unique coordinator lease token required')


class Backend(Protocol):
    """Methods must query trusted live systems, never accept receipt booleans.

    Coordinator uses an authenticated ZooKeeper ephemeral-sequential lease and
    a persistent previous-owner record. EC2 fencing checks the exact approved
    old instance and confirms stopped/terminated (request acceptance is not
    completion). Spark checks all Masters and Workers; unknown/unreachable
    observations fail. Publication is an atomic compare-and-set under the lease.
    """
    def lease_is_current(self, lease: Lease) -> bool: ...
    def previous_owner(self, lease: Lease) -> Owner | None: ...
    def stop_and_confirm_old_instance(self, old: Owner) -> bool: ...
    def old_spark_work_is_gone(self, old: Owner) -> bool: ...
    def publish_owner_if_current(self, lease: Lease) -> bool: ...


@dataclass(frozen=True)
class ActivationPermit:
    lease: Lease
    backend: Backend

    def assert_current(self):
        if self.backend.lease_is_current(self.lease) is not True:
            raise FencingError('Lease lost; stop workloads and do not release ownership until termination is confirmed')


def authorize(lease: Lease, backend: Backend) -> ActivationPermit:
    permit = ActivationPermit(lease, backend)
    permit.assert_current()
    old = backend.previous_owner(lease)
    # None means a live, authenticated read found no previous owner. Lookup
    # errors must raise, not be translated to None by an adapter.
    permit.assert_current()
    if old is not None:
        if not isinstance(old, Owner) or old.namespace != lease.owner.namespace or old.epoch >= lease.owner.epoch:
            raise FencingError('Previous owner namespace/epoch differs')
        if old.node == lease.owner.node or old.instance_id == lease.owner.instance_id:
            raise FencingError('Cannot fence the candidate itself; inspect previous termination explicitly')
        if backend.stop_and_confirm_old_instance(old) is not True:
            raise FencingError('Old EC2 fencing not confirmed; promotion blocked')
        permit.assert_current()
        if backend.old_spark_work_is_gone(old) is not True:
            raise FencingError('Old Driver/application/executor termination not confirmed')
        permit.assert_current()
    if backend.publish_owner_if_current(lease) is not True:
        raise FencingError('Atomic owner publication failed; promotion blocked')
    permit.assert_current()
    return permit
