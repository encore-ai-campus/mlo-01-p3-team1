from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('music', '0002_track_raw_acousticness_track_raw_energy_and_more')]

    operations = [
        migrations.CreateModel(
            name='MusicImportRun',
            fields=[
                ('source_sha256', models.CharField(max_length=64, primary_key=True, serialize=False)),
                ('source_schema_version', models.CharField(max_length=40)),
                ('total_count', models.PositiveIntegerField()),
                ('processed_count', models.PositiveIntegerField(default=0)),
                ('error_count', models.PositiveIntegerField(default=0)),
                ('last_track_id', models.TextField(null=True)),
                ('completed', models.BooleanField(default=False)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'db_table': 'music_import_run'},
        ),
    ]
