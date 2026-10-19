"""Join both additive 0006 migrations without renumbering applied production history."""
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("recommendation", "0006_youtubereviewaudit_youtubetrackrevision_and_more"),
        ("recommendation", "0006_distributed_dispatch"),
    ]
    operations = []
