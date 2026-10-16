"""Build a local-only, explicitly unreviewed preview catalog from the supplied CSV."""
import hashlib
import json
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from backend.recommendation.models import Catalog
from backend.recommendation.policy import groups, weather_fit, WEATHER_SCORE_VERSION
from backend.recommendation.occasion import load_occasion_decisions
from backend.recommendation.youtube import load_verified_youtube_mappings
from pipeline.music.normalize import convert, RAW_SCHEMA

DEFAULT_SOURCE = Path(__file__).resolve().parents[4] / 'docs' / 'handoff' / 'music' / 'spotify_dataset.csv'
DEFAULT_GENERAL = Path(__file__).resolve().parents[4] / 'analysis' / 'weather_music_20261016' / 'general'


def load_playback_selection(path, source_sha256, general_rows):
    """Validate an explicit local subset without changing its requested order."""
    try:
        content = Path(path).read_bytes()
        value = json.loads(content.decode('utf-8-sig'))
    except (OSError, ValueError) as exc:
        raise CommandError('Playback selection file could not be read') from exc
    fields = {'schema_version', 'source_dataset_sha256', 'track_ids', 'selection_version'}
    if (not isinstance(value, dict) or set(value) != fields
            or value.get('schema_version') != 'YOUTUBE_PLAYBACK_SELECTION_V1'
            or value.get('source_dataset_sha256') != source_sha256
            or not isinstance(value.get('selection_version'), str) or not value['selection_version'].strip()):
        raise CommandError('Playback selection schema, source or version is invalid')
    ids = value['track_ids']
    if (not isinstance(ids, list) or not ids
            or not all(isinstance(key, str) and key and key == key.strip() for key in ids)
            or len(ids) != len(set(ids))):
        raise CommandError('Playback selection requires a positive count of unique track IDs')
    known = {row['track_id'] for row in general_rows if row['occasion_status'] == 'GENERAL'}
    if not set(ids) <= known:
        raise CommandError('Every playback-selected track must exist in the GENERAL source catalog')
    return ids, value['selection_version'], hashlib.sha256(content).hexdigest()


class Command(BaseCommand):
    help = 'Load real CSV into a test-only, unreviewed recommendation preview catalog.'
    def add_arguments(self, parser):
        parser.add_argument('source', nargs='?', default=str(DEFAULT_SOURCE))
        parser.add_argument('--expected-sha256',default='b202fa49909b2d5cef71a04b1d21243cfeb36414535f2ca9272aa646721177bd')
        parser.add_argument('--general-dir', default=str(DEFAULT_GENERAL))
        parser.add_argument('--youtube-mappings')
        parser.add_argument('--playback-selection')
    def handle(self, *args, **options):
        if not settings.LOCAL_DEMO: raise CommandError('C_LOCAL_DEMO=1 required')
        if options.get('playback_selection') and not options.get('youtube_mappings'):
            raise CommandError('--youtube-mappings is required with --playback-selection')
        source=Path(options['source'])
        if not source.is_file(): raise CommandError('CSV source not found')
        data=convert(source,RAW_SCHEMA)
        if data['source_sha256'] != options['expected_sha256']: raise CommandError('CSV SHA-256 differs from expected source')
        try:
            decisions, decision_sha256, occasion_policy = load_occasion_decisions(options['general_dir'], data['source_sha256'])
        except (OSError, ValueError, KeyError) as exc:
            raise CommandError('Verified general-operation occasion decisions are required; no unfiltered fallback') from exc
        rows=[]
        for row in data['tracks']:
            decision = decisions.get(row['track_id'])
            if decision is None: raise CommandError('Occasion decision missing for a source track')
            if decision['occasion_status'] != 'GENERAL': continue
            genres=groups((row['genre'] or '').split(';'))
            preview={**row,**decision,'genre_group_codes':genres,'theme_codes':[],
                     'occasion_decisions_sha256':decision_sha256,
                     'cover_image_url':None,'preview_clear_score_version':WEATHER_SCORE_VERSION}
            fit=weather_fit(preview,'CLEAR') if genres and preview['speed'] else None
            preview['preview_clear_w']=([fit['W'].numerator,fit['W'].denominator] if fit else None)
            rows.append(preview)
        if not rows: raise CommandError('No GENERAL tracks; the existing catalog is preserved')
        selection_ids, selection_version, selection_sha256 = None, None, None
        if options.get('playback_selection'):
            selection_ids, selection_version, selection_sha256 = load_playback_selection(
                options['playback_selection'], data['source_sha256'], rows)
        youtube_sha256 = None
        youtube_mappings = {}
        if options.get('youtube_mappings'):
            try:
                youtube_mappings, youtube_sha256 = load_verified_youtube_mappings(options['youtube_mappings'], rows)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                raise CommandError('YouTube mapping snapshot verification failed; no catalog was written') from exc
            for row in rows:
                mapping = youtube_mappings.get(row['track_id'])
                if mapping:
                    row.update(youtube_video_id=mapping['youtube_video_id'], youtube_match_status='VERIFIED',
                               youtube_mapping_snapshot=mapping, youtube_mappings_sha256=youtube_sha256)
        general_count = len(rows)
        if selection_ids is not None:
            if not set(selection_ids) <= youtube_mappings.keys():
                raise CommandError('Every playback-selected track requires a VERIFIED YouTube mapping')
            lookup = {row['track_id']: row for row in rows}
            rows = [{**lookup[key], 'playback_selection_position': index,
                     'playback_selection_version': selection_version, 'playback_selection_sha256': selection_sha256}
                    for index, key in enumerate(selection_ids, 1)]
        digest=hashlib.sha256(json.dumps(rows,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        version=f'spotify-preview-{data["source_sha256"][:12]}-general-{decision_sha256[:12]}'
        if youtube_sha256: version += '-yt-' + youtube_sha256[:12]
        if selection_sha256: version += '-selection-' + selection_sha256[:12]
        source_ref = (f'local-preview:youtube-playback-selection:{source.name}' if selection_sha256
                      else f'local-preview:{source.name}')
        catalog,created=Catalog.objects.get_or_create(version=version,defaults={
            'tracks':rows,'sha256':digest,'source_ref':source_ref,
            'source_sha256':data['source_sha256'],'is_test':True,'ready':True})
        if not created and catalog.sha256 != digest: raise CommandError('Existing preview version differs')
        self.stdout.write(json.dumps({'version':version,'unique_tracks':len(rows),'source_errors':len(data['errors']),
                                      'clear_weather_eligible':sum(row['preview_clear_w'] is not None for row in rows),
                                      'occasion_policy_version':occasion_policy,'occasion_decisions_sha256':decision_sha256,
                                      'not_general_skipped':len(data['tracks'])-general_count,
                                      'verified_youtube_mapping_count':len(youtube_mappings),'youtube_mappings_sha256':youtube_sha256,
                                      'playback_selection_only':selection_ids is not None,
                                      'playback_selection_version':selection_version,'playback_selection_sha256':selection_sha256,
                                      'unreviewed_preview':True}))
