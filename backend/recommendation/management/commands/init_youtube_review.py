"""Prepare the local keyless review secret and seed old IDs as pending."""
import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from backend.recommendation import service, youtube_registry


class Command(BaseCommand):
    help = 'Initialize the Git-ignored local YouTube review access file; never print its secret.'

    def add_arguments(self, parser):
        parser.add_argument('--rotate', action='store_true', help='Replace the prior local review access code.')
        parser.add_argument('--seed-legacy', action='store_true', help='Copy latest general catalog video IDs as CANDIDATE only.')
        parser.add_argument('--seed-native-reviewed', action='store_true', help='Preserve prior reviewed identity/native-queue metadata for native playback only; never iframe approval or full listening.')

    def handle(self, *args, **options):
        if not settings.LOCAL_DEMO:
            raise CommandError('Only C_LOCAL_DEMO=1 may initialize the local review store')
        path = youtube_registry.initialize_access_code(rotate=options['rotate'])
        result = {'is_test': True, 'access_code_file': str(path), 'secret_printed': False}
        if options['seed_legacy']:
            result['seed'] = youtube_registry.seed_legacy_mappings(service.catalog().tracks)
        if options['seed_native_reviewed']:
            result['native_seed'] = youtube_registry.seed_native_reviewed_mappings(service.catalog().tracks)
        self.stdout.write(json.dumps(result, ensure_ascii=False))
