from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('recommendation', '0003_family_raw_selection')]

    operations = [
        migrations.CreateModel(
            name='DemoFeedback',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('target_kind', models.TextField()),
                ('track_id', models.TextField(default='')),
                ('value', models.JSONField(null=True)),
                ('revision', models.PositiveIntegerField(default=0)),
                ('last_event_id', models.TextField(null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('playlist', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='recommendation.playlist')),
            ],
        ),
        migrations.AddConstraint(
            model_name='demofeedback',
            constraint=models.UniqueConstraint(fields=('playlist', 'target_kind', 'track_id'), name='demo_feedback_target'),
        ),
    ]
