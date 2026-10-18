import uuid
from django.db import models


def uid(): return str(uuid.uuid4())


class OwnerLock(models.Model):
    owner_id = models.TextField(primary_key=True)


class Catalog(models.Model):
    version = models.TextField(primary_key=True)
    tracks = models.JSONField()
    sha256 = models.TextField()
    source_ref = models.TextField()
    source_sha256 = models.TextField()
    is_test = models.BooleanField(default=False)
    ready = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class Family(models.Model):
    id = models.TextField(primary_key=True,default=uid)
    owner_id = models.TextField(db_index=True)
    options = models.JSONField()
    raw_selection = models.JSONField(default=dict)
    allowed_genres = models.JSONField(default=list)
    allowed_speeds = models.JSONField(default=list)
    policy_version = models.TextField()
    mapping_version = models.TextField()
    excluded = models.JSONField(default=list)
    exclusion_revision = models.PositiveIntegerField(default=0)
    excluded_items = models.JSONField(default=dict)
    approved_playlist_id = models.TextField(null=True)
    approval_revision = models.PositiveIntegerField(default=0)


class Job(models.Model):
    id = models.TextField(primary_key=True,default=uid)
    family = models.ForeignKey(Family,on_delete=models.PROTECT)
    parent_id = models.TextField(null=True)
    method = models.TextField(default='RULE_BASED')
    status = models.TextField(default='QUEUED',db_index=True)
    input = models.JSONField()
    catalog = models.ForeignKey(Catalog,on_delete=models.PROTECT)
    error = models.JSONField(null=True)
    request_id = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    lease_token = models.TextField(null=True)
    lease_generation = models.PositiveIntegerField(default=0)
    lease_expires_at = models.DateTimeField(null=True)
    provider_attempted = models.BooleanField(default=False)
    provider_diagnostics = models.JSONField(default=dict)


class Playlist(models.Model):
    id = models.TextField(primary_key=True,default=uid)
    job = models.OneToOneField(Job,on_delete=models.PROTECT)
    family = models.ForeignKey(Family,on_delete=models.PROTECT)
    snapshot = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)


class DemoFeedback(models.Model):
    """Local CSV preview feedback until B's shared feedback store is connected."""
    playlist = models.ForeignKey(Playlist,on_delete=models.PROTECT)
    target_kind = models.TextField()
    track_id = models.TextField(default='')
    value = models.JSONField(null=True)
    revision = models.PositiveIntegerField(default=0)
    last_event_id = models.TextField(null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['playlist','target_kind','track_id'],name='demo_feedback_target')]


class Idempotency(models.Model):
    owner_id = models.TextField()
    scope = models.TextField()
    key = models.TextField()
    body = models.JSONField()
    response = models.JSONField()
    status = models.PositiveSmallIntegerField()
    class Meta:
        constraints = [models.UniqueConstraint(fields=['owner_id','scope','key'], name='rec_idempotency_scope')]


class PendingEvent(models.Model):
    """C-owned handoff outbox. EVENT_SINK may instead write B's shared outbox in the same transaction.

    No guessed FeedbackEventEnvelope.contract_version; unresolved envelope must be bound by B.
    """
    event_id = models.TextField(primary_key=True,default=uid)
    event_type = models.TextField()
    payload = models.JSONField()
    occurred_at = models.DateTimeField(auto_now_add=True)
