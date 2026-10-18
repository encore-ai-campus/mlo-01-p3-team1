from django.db import migrations, models
import django.db.models.deletion


def backfill_publications(apps, schema_editor):
    catalog = apps.get_model('recommendation', 'Catalog')
    publication = apps.get_model('recommendation', 'CatalogPublication')
    using = schema_editor.connection.alias
    # Historical equal timestamps have no recoverable creation order. Preserve a deterministic order once.
    for pk in catalog.objects.using(using).order_by('created_at', 'version').values_list('pk', flat=True).iterator():
        publication.objects.using(using).create(catalog_id=pk)


class Migration(migrations.Migration):
    dependencies = [('recommendation', '0004_demo_feedback')]
    operations = [
        migrations.CreateModel(
            name='CatalogPublication',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('catalog', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE,
                                                related_name='publication', to='recommendation.catalog')),
            ],
        ),
        migrations.RunPython(backfill_publications, migrations.RunPython.noop),
    ]
