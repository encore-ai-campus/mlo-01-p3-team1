"""Build a local-only, explicitly unreviewed preview catalog from the supplied CSV."""
import hashlib
import json
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from backend.recommendation.models import Catalog
from backend.recommendation.policy import groups, precompute_scores
from pipeline.music.normalize import convert, RAW_SCHEMA

DEFAULT_SOURCE = Path(__file__).resolve().parents[4] / 'docs' / 'handoff' / 'music' / 'spotify_dataset.csv'


class Command(BaseCommand):
    help = 'Load real CSV into a test-only, unreviewed recommendation preview catalog.'
    def add_arguments(self, parser):
        parser.add_argument('source', nargs='?', default=str(DEFAULT_SOURCE))
        parser.add_argument('--expected-sha256',default='b202fa49909b2d5cef71a04b1d21243cfeb36414535f2ca9272aa646721177bd')
    def handle(self, *args, **options):
        if not settings.LOCAL_DEMO: raise CommandError('C_LOCAL_DEMO=1 required')
        source=Path(options['source'])
        if not source.is_file(): raise CommandError('CSV source not found')
        data=convert(source,RAW_SCHEMA)
        # Git may check out the received CSV with CRLF on Windows. Keep the
        # actual byte hash for provenance; permit only that line-ending change.
        lf_sha256=hashlib.sha256(source.read_bytes().replace(b'\r\n',b'\n')).hexdigest()
        if options['expected_sha256'] not in {data['source_sha256'],lf_sha256}:
            raise CommandError('CSV SHA-256 differs from expected source')
        rows=[]
        for row in data['tracks']:
            genres=groups((row['genre'] or '').split(';'))
            preview={**row,'genre_group_codes':genres,'theme_codes':[],
                     'cover_image_url':None}
            rows.append(precompute_scores(preview))
        digest=hashlib.sha256(json.dumps(rows,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        version=f'spotify-preview-{data["source_sha256"][:12]}-v3'
        catalog,created=Catalog.objects.get_or_create(version=version,defaults={
            'tracks':rows,'sha256':digest,'source_ref':f'local-preview:{source.name}',
            'source_sha256':data['source_sha256'],'is_test':True,'ready':True})
        if not created and catalog.sha256 != digest: raise CommandError('Existing preview version differs')
        self.stdout.write(json.dumps({'version':version,'source_sha256':data['source_sha256'],
                                      'unique_tracks':len(rows),'source_errors':len(data['errors']),
                                      'conflicting_track_ids':len(data['conflicting_track_ids']),
                                      'clear_weather_eligible':sum(row['score_cache']['weather']['CLEAR'] is not None for row in rows),
                                      'unreviewed_preview':True}))
