import uuid
from django.db import models, router, transaction


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

    def save(self, *args, **kwargs):
        using = kwargs.get('using') or router.db_for_write(type(self), instance=self)
        with transaction.atomic(using=using):
            new = self._state.adding
            super().save(*args, **kwargs)
            if new:
                CatalogPublication.objects.using(using).create(catalog=self)


class CatalogPublication(models.Model):
    """Database-issued registration order, independent of clock precision and version names."""
    catalog = models.OneToOneField(Catalog, on_delete=models.CASCADE, related_name='publication')


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
    worker_id = models.CharField(max_length=160, default='')
    claimed_at = models.DateTimeField(null=True)
    finished_at = models.DateTimeField(null=True)
    recovery_count = models.PositiveIntegerField(default=0)
    provider_started_at = models.DateTimeField(null=True)
    provider_lease_until = models.DateTimeField(null=True)

    class Meta:
        indexes = [
            models.Index(fields=['method', 'status', 'created_at'], name='rec_method_queue_idx'),
            models.Index(fields=['status', 'lease_expires_at'], name='rec_expired_lease_idx'),
        ]


class DispatchControl(models.Model):
    """Shared admission/provider locks; never held during recommendation or HTTP work."""
    name = models.CharField(max_length=40, primary_key=True)
    next_provider_at = models.DateTimeField(null=True)


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

class YoutubeTrackRevision(models.Model):
    track_id = models.TextField(primary_key=True)
    revision = models.PositiveIntegerField(default=0, db_default=0)
    class Meta:
        db_table = 'youtube_track_revision'


class YoutubeMapping(models.Model):
    track = models.ForeignKey(YoutubeTrackRevision, db_column='track_id', on_delete=models.PROTECT)
    video_id = models.CharField(max_length=11)
    status = models.CharField(max_length=12)
    source = models.TextField()
    note = models.TextField(default='', db_default='')
    reason = models.TextField(default='', db_default='')
    identity_confirmed = models.PositiveSmallIntegerField(default=0, db_default=0)
    playback_observed = models.PositiveSmallIntegerField(default=0, db_default=0)
    duration_seconds = models.FloatField(null=True)
    observed_at = models.TextField(null=True)
    updated_at = models.TextField()
    native_verified = models.PositiveSmallIntegerField(default=0, db_default=0)
    native_duration_seconds = models.FloatField(null=True)
    native_observed_at = models.TextField(null=True)
    native_source = models.TextField(default='', db_default='')
    native_reason = models.TextField(default='', db_default='')
    class Meta:
        db_table = 'youtube_mapping'
        constraints = [models.UniqueConstraint(fields=['track','video_id'],name='youtube_track_video_unique')]


class YoutubeReviewAudit(models.Model):
    track_id = models.TextField(db_index=True)
    video_id = models.CharField(max_length=11)
    action = models.TextField()
    revision = models.PositiveIntegerField()
    created_at = models.TextField()
    actor = models.TextField(default='system', db_default='system')
    class Meta:
        db_table = 'youtube_review_audit'
