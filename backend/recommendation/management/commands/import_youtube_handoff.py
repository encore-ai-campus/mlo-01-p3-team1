"""Import an explicit, checksummed review handoff without changing music approvals."""
import csv
import hashlib
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
import re

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone
from backend.recommendation.models import YoutubeMapping, YoutubeTrackRevision, YoutubeReviewAudit
from backend.recommendation.service import current_catalog
from backend.recommendation.worker import verified_catalog
from backend.recommendation.youtube_registry import normalize_video_url

ACTIONS = {'SEED_LEGACY_PENDING', 'SEED_LEGACY_NATIVE_METADATA_ONLY', 'BLOCK',
           'VERIFY_OPERATOR_REPORTED_PLAYING', 'VERIFY_NATIVE_DURATION_DIFFERENCE_ACK',
           'REGISTER_CANDIDATE', 'VERIFY_OPERATOR_REPORTED_NATIVE_PLAYING', 'BLOCK_NATIVE'}
NATIVE_ACTIONS = {'VERIFY_OPERATOR_REPORTED_NATIVE_PLAYING', 'VERIFY_NATIVE_DURATION_DIFFERENCE_ACK',
                  'SEED_LEGACY_NATIVE_METADATA_ONLY'}


def stamp(value, required=False):
    if not value:
        if required: raise CommandError('Review timestamp is required')
        return None
    try: parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError: raise CommandError('Invalid review timestamp') from None
    if parsed.tzinfo is None: raise CommandError('Review timestamp must include timezone')
    return value


def positive(value, required=False):
    if not value:
        if required: raise CommandError('Observed duration is required')
        return None
    try: number = float(value)
    except ValueError: raise CommandError('Invalid observed duration') from None
    if not math.isfinite(number) or not 0 < number <= 86400: raise CommandError('Invalid observed duration')
    return number


def flag(value):
    if value not in ('0', '1', ''): raise CommandError('Invalid review flag')
    return int(value or '0')


def read_handoff(music_csv, audit_csv, catalog_tracks):
    audit, evidence, seen_audits = [], defaultdict(set), set()
    with Path(audit_csv).open(encoding='utf-8-sig', newline='') as handle:
        for row in csv.DictReader(handle):
            key = (row['track_id'], row['video_id'])
            if row['track_id'] not in catalog_tracks or not re.fullmatch(r'[A-Za-z0-9_-]{11}', row['video_id']):
                raise CommandError('Audit identity is outside current approved catalog')
            if row['action'] not in ACTIONS or row['id'] in seen_audits or not row['id'].isdigit():
                raise CommandError('Invalid or duplicate source audit')
            seen_audits.add(row['id']); evidence[key].add(row['action'])
            revision = int(row['revision'])
            if revision < 0: raise CommandError('Invalid source revision')
            audit.append({'source_id': row['id'], 'track_id': key[0], 'video_id': key[1],
                          'action': 'HANDOFF_' + row['action'], 'revision': revision,
                          'created_at': stamp(row['created_at_utc'], True)})
    mappings, revisions, seen_tracks, pairs = [], {}, set(), set()
    for_count = Counter()
    with Path(music_csv).open(encoding='utf-8-sig', newline='') as handle:
        for row in csv.DictReader(handle):
            track_id = row['track_id']; track = catalog_tracks.get(track_id)
            if track is None or row['occasion_status'] != 'GENERAL' or int(row['duration_ms']) != track['duration_ms']:
                raise CommandError('Input does not match current approved GENERAL catalog')
            seen_tracks.add(track_id)
            video = row['youtube_video_id']
            if not video: continue
            if normalize_video_url(row['youtube_video_url']) != video: raise CommandError('Video URL and ID mismatch')
            key = (track_id, video)
            if key in pairs: raise CommandError('Duplicate mapping pair')
            pairs.add(key); for_count[track_id] += 1
            if for_count[track_id] > 10: raise CommandError('Candidate bound exceeded')
            revision = int(row['youtube_revision'])
            if revision < 0 or (track_id in revisions and revisions[track_id] != revision):
                raise CommandError('Inconsistent track revision')
            revisions[track_id] = revision
            status = row['youtube_iframe_status']; native = flag(row['youtube_native_verified'])
            if status not in {'CANDIDATE', 'BLOCKED', 'VERIFIED'}: raise CommandError('Invalid iframe status')
            note, reason, native_reason = row['youtube_note'], row['youtube_iframe_block_reason'], row['youtube_native_block_reason']
            if any(len(text) > 1000 for text in (note, reason, native_reason)): raise CommandError('Oversized review note')
            identity, playback = flag(row['youtube_identity_confirmed']), flag(row['youtube_iframe_playback_observed'])
            duration = positive(row['youtube_iframe_duration_seconds'], status == 'VERIFIED')
            observed = stamp(row['youtube_iframe_observed_at_utc'], status == 'VERIFIED')
            native_duration = positive(row['youtube_native_duration_seconds'], bool(native))
            native_observed = stamp(row['youtube_native_observed_at_utc'], bool(native))
            original = track['duration_ms'] / 1000
            if status == 'VERIFIED' and (identity != 1 or playback != 1 or
                    'VERIFY_OPERATOR_REPORTED_PLAYING' not in evidence[key] or
                    abs(duration - original) > min(60, max(12, original * .12))):
                raise CommandError('Iframe approval lacks matching observation evidence')
            if status == 'BLOCKED' and (not reason or 'BLOCK' not in evidence[key]):
                raise CommandError('Iframe block lacks source audit')
            if native and not (evidence[key] & NATIVE_ACTIONS): raise CommandError('Native approval lacks source audit')
            if native and abs(native_duration-original) > min(60, max(12, original*.12)):
                if 'VERIFY_NATIVE_DURATION_DIFFERENCE_ACK' not in evidence[key] or abs(native_duration-original) > 60 or not note:
                    raise CommandError('Native duration mismatch lacks acknowledgment')
            if native_reason and 'BLOCK_NATIVE' not in evidence[key]: raise CommandError('Native block lacks source audit')
            mappings.append({'track_id': track_id, 'video_id': video, 'status': status,
                'source': row['youtube_mapping_source'], 'note': note, 'reason': reason,
                'identity_confirmed': identity, 'playback_observed': playback,
                'duration_seconds': duration, 'observed_at': observed,
                'updated_at': stamp(row['youtube_updated_at_utc'], True), 'native_verified': native,
                'native_duration_seconds': native_duration, 'native_observed_at': native_observed,
                'native_source': row['youtube_native_source'], 'native_reason': native_reason})
    if seen_tracks != set(catalog_tracks): raise CommandError('Handoff must cover the exact current GENERAL catalog')
    if not mappings or not audit: raise CommandError('Empty handoff')
    return mappings, revisions, audit


def apply_handoff(mappings, revisions, audit, source_digest, dry_run=False):
    prefix = 'handoff:' + source_digest + ':'
    if dry_run: return {'dry_run': True, 'input_mappings': len(mappings), 'source_audits': len(audit)}
    with transaction.atomic():
        if connection.vendor == 'postgresql':
            with connection.cursor() as cursor: cursor.execute('SELECT pg_advisory_xact_lock(%s)', [int(source_digest[:15], 16)])
        imported = YoutubeReviewAudit.objects.filter(actor__startswith=prefix).count()
        if imported:
            if imported != len(audit): raise CommandError('Incomplete or altered prior handoff receipt')
            return {'already_imported': True, 'source_audits': imported}
        existing_revisions = {r.pk: r for r in YoutubeTrackRevision.objects.select_for_update()}
        new_revisions = [YoutubeTrackRevision(track_id=tid, revision=value + 1)
                         for tid, value in revisions.items() if tid not in existing_revisions]
        YoutubeTrackRevision.objects.bulk_create(new_revisions, batch_size=1000)
        existing = {(row.track_id, row.video_id): row for row in YoutubeMapping.objects.select_for_update()}
        create, update, touched = [], [], set()
        fields = [key for key in mappings[0] if key not in {'track_id', 'video_id'}]
        for incoming in mappings:
            key = (incoming['track_id'], incoming['video_id']); old = existing.get(key)
            if old is None: create.append(YoutubeMapping(**incoming)); touched.add(incoming['track_id']); continue
            desired = dict(incoming)
            # Explicit denials win; unreviewed candidates never downgrade an existing approval.
            if old.status == 'BLOCKED' or (old.status == 'VERIFIED' and desired['status'] == 'CANDIDATE'):
                for name in ['status', 'reason', 'identity_confirmed', 'playback_observed', 'duration_seconds', 'observed_at']:
                    desired[name] = getattr(old, name)
            if old.native_reason or (old.native_verified and not desired['native_verified'] and not desired['native_reason']):
                for name in ['native_verified', 'native_duration_seconds', 'native_observed_at', 'native_source', 'native_reason']:
                    desired[name] = getattr(old, name)
            changed = any(getattr(old, name) != desired[name] for name in fields)
            if changed:
                for name in fields: setattr(old, name, desired[name])
                update.append(old); touched.add(old.track_id)
        YoutubeMapping.objects.bulk_create(create, batch_size=1000)
        if update: YoutubeMapping.objects.bulk_update(update, fields, batch_size=500)
        revision_updates = []
        for tid in touched & existing_revisions.keys():
            row = existing_revisions[tid]; row.revision = max(row.revision, revisions[tid]) + 1; revision_updates.append(row)
        if revision_updates: YoutubeTrackRevision.objects.bulk_update(revision_updates, ['revision'], batch_size=1000)
        YoutubeReviewAudit.objects.bulk_create([YoutubeReviewAudit(**{k: v for k, v in row.items() if k != 'source_id'}, actor=prefix+row['source_id']) for row in audit], batch_size=1000)
        return {'inserted_mappings': len(create), 'merged_existing_mappings': len(update),
                'source_audits': len(audit), 'total_mappings': YoutubeMapping.objects.count(),
                'native_verified_mappings': YoutubeMapping.objects.filter(native_verified=1).count(),
                'iframe_verified_mappings': YoutubeMapping.objects.filter(status='VERIFIED').count(),
                'music_approvals_unchanged': True}


class Command(BaseCommand):
    help = 'Import explicit review evidence from a private, checksummed handoff; music data is not changed.'
    def add_arguments(self, parser):
        parser.add_argument('--music-csv', required=True)
        parser.add_argument('--audit-csv', required=True)
        parser.add_argument('--music-sha256', required=True)
        parser.add_argument('--audit-sha256', required=True)
        parser.add_argument('--source-sha256', required=True)
        parser.add_argument('--dry-run', action='store_true')
    def handle(self, *args, **options):
        if settings.LOCAL_DEMO or not settings.INTEGRATION_ENABLED or getattr(settings, 'YOUTUBE_REGISTRY_BACKEND', '') != 'database':
            raise CommandError('Production shared database mode is required')
        for path_key, digest_key in [('music_csv', 'music_sha256'), ('audit_csv', 'audit_sha256')]:
            path = Path(options[path_key])
            if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != options[digest_key]:
                raise CommandError('Handoff checksum mismatch')
        catalog = current_catalog()
        if catalog is None or catalog.is_test or catalog.source_sha256 != options['source_sha256']:
            raise CommandError('Current approved catalog source does not match handoff')
        tracks = {t['track_id']: t for t in verified_catalog(catalog)}
        mappings, revisions, audit = read_handoff(options['music_csv'], options['audit_csv'], tracks)
        result = apply_handoff(mappings, revisions, audit, options['music_sha256'], options['dry_run'])
        import json
        self.stdout.write(json.dumps(result, ensure_ascii=False))
