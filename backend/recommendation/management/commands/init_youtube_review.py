"""Prepare the local keyless review secret and seed old IDs as pending."""
import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from backend.recommendation import service, youtube_registry


class Command(BaseCommand):
    help = 'Initialize the Git-ignored local YouTube review access file; never print its secret.'

    def add_arguments(self, parser):
        parser.add_argument('--mapping-snapshot', help='Reviewed immutable mapping snapshot; validates original music metadata before seeding.')
        parser.add_argument('--rotate', action='store_true', help='Replace the prior local review access code.')
        parser.add_argument('--seed-legacy', action='store_true', help='Copy latest general catalog video IDs as CANDIDATE only.')
        parser.add_argument('--seed-native-reviewed', action='store_true', help='Preserve prior reviewed identity/native-queue metadata for native playback only; never iframe approval or full listening.')

    def handle(self, *args, **options):
        shared = not settings.LOCAL_DEMO and getattr(settings,'YOUTUBE_REGISTRY_BACKEND','disabled')=='database'
        if not settings.LOCAL_DEMO and not shared:
            raise CommandError('Only C_LOCAL_DEMO=1 or an explicitly enabled shared database registry may initialize')
        if shared and options['rotate']:
            raise CommandError('Production uses ADMIN sessions; local access-code rotation is not available')
        if shared:
            result={'is_test':False,'storage':'shared-database','auth_mode':'ADMIN_SESSION','secret_printed':False}
        else:
            path=youtube_registry.initialize_access_code(rotate=options['rotate'])
            result={'is_test':True,'access_code_file':str(path),'secret_printed':False}
        if options['seed_legacy'] or options['seed_native_reviewed']:
            from backend.recommendation.worker import verified_catalog
            tracks=verified_catalog(service.catalog())
            if options['mapping_snapshot']:
                from backend.recommendation.youtube import load_verified_youtube_mappings
                mappings,digest=load_verified_youtube_mappings(options['mapping_snapshot'],tracks)
                tracks=[{**track,'youtube_video_id':mappings[track['track_id']]['youtube_video_id'],
                         'youtube_match_status':'VERIFIED','youtube_mapping_snapshot':mappings[track['track_id']]}
                        for track in tracks if track['track_id'] in mappings]
                result['mapping_snapshot_sha256']=digest
            if options['seed_legacy']:result['seed']=youtube_registry.seed_legacy_mappings(tracks)
            if options['seed_native_reviewed']:result['native_seed']=youtube_registry.seed_native_reviewed_mappings(tracks)
        self.stdout.write(json.dumps(result,ensure_ascii=False))
