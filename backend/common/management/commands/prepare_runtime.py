"""One-time configured database/data preparation; never silently promotes test data."""
import json
import os
from pathlib import Path
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help='공통 migration과 선택한 음악 원본을 준비합니다. 실제 쓰기는 --apply에만 수행합니다.'

    def add_arguments(self,parser):
        parser.add_argument('--apply',action='store_true')
        parser.add_argument('--music',action='store_true')
        parser.add_argument('--streams',action='store_true')

    def handle(self,*args,**options):
        if not options['apply']:
            self.stdout.write(json.dumps({'applied':False,'steps':['migrate']+(['feedback_topic'] if options['streams'] else [])+(['music_import','publish_approved_only'] if options['music'] else [])}));return
        call_command('migrate',interactive=False,stdout=self.stdout)
        username=os.environ.get('BOOTSTRAP_ADMIN_USERNAME','')
        if username:
            from django.contrib.auth import get_user_model
            existing_user=get_user_model().objects.filter(username=username).first()
            if existing_user:
                if not existing_user.is_active or not existing_user.is_staff:raise CommandError('configured_account_not_active_admin')
                self.stdout.write(json.dumps({'existing_admin_preserved':True}))
            else:
                permissions=[x.strip() for x in os.environ.get('BOOTSTRAP_ADMIN_PERMISSIONS','').split(',') if x.strip()]
                if not permissions or not set(permissions)<={'manage_ads','manage_music','view_feedback'}:
                    raise CommandError('explicit_admin_permissions_required')
                call_command('bootstrap_admin',username,permissions=permissions,stdout=self.stdout)
        if options['streams']:
            from pipeline.prepare_kafka import ensure_topic
            self.stdout.write(json.dumps({'feedback_topic':ensure_topic('FEEDBACK_KAFKA_')}))
        if not options['music']:return
        source=os.environ.get('MUSIC_SOURCE_PATH','')
        digest=os.environ.get('MUSIC_SOURCE_SHA256','')
        version=os.environ.get('MUSIC_CATALOG_VERSION','')
        schema=os.environ.get('MUSIC_SOURCE_SCHEMA','spotify-raw20-v1')
        if not source or not digest or not version:raise CommandError('music_source_path_sha256_version_required')
        path=Path(source)
        if not path.is_absolute():path=settings.BASE_DIR/path
        call_command('import_music_catalog_source',str(path),schema=schema,expected_sha256=digest,apply=True,stdout=self.stdout)
        from backend.common.models import Review
        from backend.recommendation.models import Catalog
        from backend.music.catalog import publish
        if not Review.objects.filter(status='approved',track__trackorigin__source_id=digest).exists():
            self.stdout.write(json.dumps({'music_imported':True,'catalog_ready':False,'reason':'REVIEW_REQUIRED'}))
            return
        existing=Catalog.objects.filter(pk=version).first()
        if existing:
            if existing.source_sha256!=digest or existing.source_ref!='music-source:'+digest or existing.is_test!=settings.LOCAL_DEMO:
                raise CommandError('catalog_version_conflict')
        else:existing=publish(version,'music-source:'+digest,digest,is_test=settings.LOCAL_DEMO)
        self.stdout.write(json.dumps({'catalog_version':existing.pk,'catalog_ready':existing.ready,'is_test':existing.is_test}))
