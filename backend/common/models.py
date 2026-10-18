import uuid
from django.conf import settings
from django.db import models


def uid():
    return str(uuid.uuid4())


class Guest(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=uid)
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    active = models.BooleanField(default=True)

    class Meta:
        permissions = [('manage_ads', 'Manage advertisements'),
                       ('manage_music', 'Import and review music'),
                       ('view_feedback', 'Read feedback history')]


class FeedbackEvent(models.Model):
    event_id = models.CharField(primary_key=True, max_length=36)
    event_type = models.CharField(max_length=64)
    owner_id = models.CharField(max_length=36, db_index=True)
    family_id = models.CharField(max_length=36, db_index=True)
    source_playlist_id = models.CharField(max_length=36, null=True, db_index=True)
    track_id = models.TextField(null=True, db_index=True)
    payload = models.JSONField()
    occurred_at = models.DateTimeField(db_index=True)
    is_test = models.BooleanField()

    class Meta:
        indexes = [models.Index(fields=['family_id', 'track_id', '-occurred_at'])]


class Outbox(models.Model):
    event = models.OneToOneField(FeedbackEvent, on_delete=models.PROTECT, primary_key=True)
    envelope = models.JSONField()
    state = models.CharField(max_length=12, default='PENDING', db_index=True)
    attempts = models.PositiveIntegerField(default=0)
    lease_token = models.CharField(max_length=36, null=True)
    lease_until = models.DateTimeField(null=True)
    published_at = models.DateTimeField(null=True)
    last_error = models.CharField(max_length=100, default='')


class FeedbackState(models.Model):
    playlist = models.ForeignKey('recommendation.Playlist', on_delete=models.PROTECT)
    target_kind = models.CharField(max_length=12)
    track_id = models.TextField(default='')
    value = models.JSONField(null=True)
    revision = models.PositiveIntegerField(default=0)
    last_event_id = models.CharField(max_length=36, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['playlist', 'target_kind', 'track_id'], name='feedback_target')]


class StreamRecord(models.Model):
    stream_key = models.TextField(primary_key=True)
    event_id = models.CharField(max_length=36, db_index=True)
    envelope = models.JSONField()
    received_at = models.DateTimeField(auto_now_add=True)


class Projection(models.Model):
    event = models.OneToOneField(FeedbackEvent, on_delete=models.PROTECT, primary_key=True)
    applied_at = models.DateTimeField(auto_now_add=True)


class Review(models.Model):
    track = models.OneToOneField('music.Track', on_delete=models.PROTECT, primary_key=True)
    revision = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=12, default='draft')
    reason = models.TextField(default='')
    updated_at = models.DateTimeField(auto_now=True)


class ReviewChange(models.Model):
    id = models.CharField(primary_key=True, max_length=36, default=uid)
    track_id = models.TextField(db_index=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    revision = models.PositiveIntegerField()
    snapshot = models.JSONField()
    occurred_at = models.DateTimeField(auto_now_add=True)


class AdminAction(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    scope = models.TextField()
    key = models.CharField(max_length=200)
    fingerprint = models.CharField(max_length=64)
    response = models.JSONField()
    status = models.PositiveSmallIntegerField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=['actor', 'scope', 'key'], name='admin_action_key')]


class MusicSource(models.Model):
    sha256 = models.CharField(primary_key=True,max_length=64)
    schema = models.CharField(max_length=40)
    raw_path = models.TextField()
    archive = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)


class ProjectedState(models.Model):
    target_key = models.TextField(primary_key=True)
    revision = models.PositiveIntegerField()
    value = models.JSONField(null=True)
    event = models.ForeignKey(FeedbackEvent,on_delete=models.PROTECT)
    is_test = models.BooleanField()


class TrackOrigin(models.Model):
    track = models.OneToOneField('music.Track',on_delete=models.PROTECT,primary_key=True)
    source = models.ForeignKey(MusicSource,on_delete=models.PROTECT)


class EventSnapshot(models.Model):
    id = models.CharField(primary_key=True,max_length=80)
    kind = models.CharField(max_length=12)
    data = models.JSONField()
