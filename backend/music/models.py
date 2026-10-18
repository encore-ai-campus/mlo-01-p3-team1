from django.db import models


class Album(models.Model):
    album_key = models.BigAutoField(primary_key=True)
    album_id = models.TextField(null=True, unique=True)
    album_name = models.TextField()
    album_release_date = models.TextField(null=True)
    class Meta: db_table = 'music_album'


class Track(models.Model):
    track_id = models.TextField(primary_key=True)
    track_name = models.TextField()
    artists_name = models.TextField()
    artists_id = models.TextField(null=True)
    album = models.ForeignKey(Album, on_delete=models.PROTECT, db_column='album_key')
    duration_ms = models.PositiveIntegerField()
    explicit = models.BooleanField()
    energy = models.PositiveSmallIntegerField(null=True)
    mode = models.BooleanField(null=True)
    acousticness = models.PositiveSmallIntegerField(null=True)
    raw_energy = models.TextField(null=True)
    raw_acousticness = models.TextField(null=True)
    raw_valence = models.TextField(null=True)
    speed = models.TextField(null=True)
    instrumental = models.BooleanField(null=True)
    instrumental_review_value = models.BooleanField(null=True)
    play_url = models.TextField()
    class Meta:
        db_table = 'music_track'
        constraints = [models.CheckConstraint(condition=models.Q(energy__lte=10),name='music_energy_range'),
                       models.CheckConstraint(condition=models.Q(acousticness__lte=100),name='music_acoustic_range'),
                       models.CheckConstraint(condition=models.Q(speed__isnull=True)|models.Q(speed__in=['slow','medium','fast','fastest']),name='music_speed')]


class Tag(models.Model):
    tag_id = models.BigAutoField(primary_key=True)
    tag_type = models.TextField()
    tag_code = models.TextField()
    tag_name = models.TextField()
    is_active = models.BooleanField(default=False)
    class Meta:
        db_table = 'music_tag'
        constraints = [models.UniqueConstraint(fields=['tag_type','tag_code'],name='music_tag_kind_code'),
                       models.CheckConstraint(condition=models.Q(tag_type__in=['genre','mood','instrument']),name='music_tag_kind')]


class TrackTag(models.Model):
    pk = models.CompositePrimaryKey('track_id','tag_id')
    track = models.ForeignKey(Track, on_delete=models.CASCADE)
    tag = models.ForeignKey(Tag, on_delete=models.PROTECT)
    review_status = models.TextField(default='draft')
    class Meta:
        db_table = 'track_tag'
        constraints = [models.CheckConstraint(condition=models.Q(review_status__in=['draft','approved']),name='music_link_review')]


class MusicImportRun(models.Model):
    """Operational checkpoint; not a fifth recommendation/music attribute table."""
    source_sha256 = models.CharField(primary_key=True, max_length=64)
    source_schema_version = models.CharField(max_length=40)
    total_count = models.PositiveIntegerField()
    processed_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    last_track_id = models.TextField(null=True)
    completed = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'music_import_run'
