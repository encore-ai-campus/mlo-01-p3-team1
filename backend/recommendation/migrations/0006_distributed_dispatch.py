from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('recommendation', '0005_catalog_publication')]
    operations = [
        migrations.CreateModel(name='DispatchControl', fields=[
            ('name', models.CharField(max_length=40, primary_key=True, serialize=False)),
            ('next_provider_at', models.DateTimeField(null=True)),
        ]),
        migrations.AddField(model_name='job', name='worker_id', field=models.CharField(default='', max_length=160)),
        migrations.AddField(model_name='job', name='claimed_at', field=models.DateTimeField(null=True)),
        migrations.AddField(model_name='job', name='finished_at', field=models.DateTimeField(null=True)),
        migrations.AddField(model_name='job', name='recovery_count', field=models.PositiveIntegerField(default=0)),
        migrations.AddField(model_name='job', name='provider_started_at', field=models.DateTimeField(null=True)),
        migrations.AddField(model_name='job', name='provider_lease_until', field=models.DateTimeField(null=True)),
        migrations.AddIndex(model_name='job', index=models.Index(fields=['method', 'status', 'created_at'], name='rec_method_queue_idx')),
        migrations.AddIndex(model_name='job', index=models.Index(fields=['status', 'lease_expires_at'], name='rec_expired_lease_idx')),
    ]
