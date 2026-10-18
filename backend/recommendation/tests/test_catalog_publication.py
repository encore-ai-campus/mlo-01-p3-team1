from datetime import timedelta
from unittest.mock import patch

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from backend.recommendation.models import Catalog, CatalogPublication
from backend.recommendation.service import current_catalog


@override_settings(LOCAL_DEMO=True)
class CatalogPublicationTests(TestCase):
    def create(self, version, **extra):
        return Catalog.objects.create(version=version, tracks=[], sha256='fixture',
            source_ref='fixture', source_sha256='a'*64, is_test=True, ready=True, **extra)

    def test_equal_times_and_reverse_version_names_follow_registration_order(self):
        with patch('django.utils.timezone.now', return_value=timezone.now()):
            first=self.create('z-first')
            latest=self.create('a-latest')
        self.assertEqual(first.created_at,latest.created_at)
        self.assertEqual(current_catalog().pk,latest.pk)
        self.assertGreater(latest.publication.pk,first.publication.pk)

    def test_clock_rollback_and_updates_do_not_change_registration_order(self):
        first=self.create('first')
        with patch('django.utils.timezone.now', return_value=first.created_at-timedelta(seconds=1)):
            latest=self.create('latest')
        first.ready=False;first.save(update_fields=['ready'])
        first.ready=True;first.save(update_fields=['ready'])
        self.assertEqual(CatalogPublication.objects.count(),2)
        self.assertEqual(current_catalog().pk,latest.pk)


class CatalogPublicationMigrationTests(TransactionTestCase):
    def test_existing_snapshots_are_preserved_and_backfilled(self):
        before=[('recommendation','0004_demo_feedback')]
        after=[('recommendation','0005_catalog_publication')]
        executor=MigrationExecutor(connection)
        executor.migrate(before)
        try:
            old=executor.loader.project_state(before).apps.get_model('recommendation','Catalog')
            at=timezone.now()
            for version in ('legacy-a','legacy-b'):
                old.objects.create(version=version,tracks=[{'track_id':version}],sha256=version,
                    source_ref='immutable',source_sha256='a'*64,is_test=True,ready=True)
            old.objects.update(created_at=at)
            executor=MigrationExecutor(connection);executor.migrate(after)
            self.assertEqual(CatalogPublication.objects.count(),2)
            self.assertEqual(Catalog.objects.get(pk='legacy-a').tracks,[{'track_id':'legacy-a'}])
            self.assertEqual(Catalog.objects.get(pk='legacy-a').sha256,'legacy-a')
            with override_settings(LOCAL_DEMO=True):self.assertEqual(current_catalog().pk,'legacy-b')
        finally:
            MigrationExecutor(connection).migrate(after)
