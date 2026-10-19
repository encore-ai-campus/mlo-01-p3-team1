"""Explicit, idempotent production publication of already approved source rows."""
import json,re
from django.conf import settings
from django.core.management.base import BaseCommand,CommandError
from backend.common.models import MusicSource
from backend.music.catalog import publish
from backend.recommendation.models import Catalog
from backend.recommendation.worker import verified_catalog

class Command(BaseCommand):
    help='Publish a new immutable GENERAL catalog from an existing approved source; never imports or approves tracks.'
    def add_arguments(self,parser):
        parser.add_argument('--catalog-version',required=True)
        parser.add_argument('--source-sha256',required=True)
    def handle(self,*args,**options):
        if settings.LOCAL_DEMO or not settings.INTEGRATION_ENABLED:
            raise CommandError('Production integration mode is required')
        version,digest=options['catalog_version'],options['source_sha256']
        if not version.strip() or len(version)>200 or not re.fullmatch('[0-9a-f]{64}',digest):
            raise CommandError('An explicit version and source SHA-256 are required')
        if not MusicSource.objects.filter(pk=digest).exists():
            raise CommandError('Registered immutable music source is required')
        item=Catalog.objects.filter(pk=version).first()
        if item is None:item=publish(version,'music-source:'+digest,digest,is_test=False)
        if item.source_sha256!=digest or item.is_test or not item.ready:
            raise CommandError('Existing catalog identity or readiness differs')
        tracks=verified_catalog(item)
        self.stdout.write(json.dumps({'version':item.pk,'tracks':len(tracks),'sha256':item.sha256,
                                     'already_approved_only':True,'general_only':True,'is_test':False}))
