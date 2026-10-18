"""Optional immutable original-song mapping for external YouTube navigation."""
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re

VIDEO_ID = re.compile(r'^[A-Za-z0-9_-]{11}$')


def load_verified_youtube_mappings(path, tracks):
    """Attach only explicitly VERIFIED records; preserve other input statuses."""
    file = Path(path)
    payload = json.loads(file.read_text(encoding='utf-8-sig'))
    if payload.get('schema_version') != 'YOUTUBE_MAPPING_V1' or not isinstance(payload.get('mappings'), list):
        raise ValueError('Unsupported YouTube mapping snapshot')
    records, seen = {}, set()
    lookup = {track['track_id']: track for track in tracks}
    for record in payload['mappings']:
        if not isinstance(record, dict) or not record.get('track_id') or record['track_id'] in seen:
            raise ValueError('Invalid or duplicate YouTube source track')
        seen.add(record['track_id'])
        # BLOCKED_EMBED and candidates remain untouched in the source file.
        # No inference from an embed failure to successful external navigation.
        if record.get('match_status') != 'VERIFIED' or record['track_id'] not in lookup:
            continue
        track = lookup[record['track_id']]
        pairs = [('source_track_name', 'track_name'), ('source_artists', 'artists_name'),
                 ('source_album_name', 'album_name')]
        if (any(record.get(source) != track[key] for source, key in pairs)
                or type(record.get('source_duration_ms')) is not int
                or record['source_duration_ms'] != track['duration_ms']
                or not isinstance(record.get('youtube_video_id'), str)
                or not VIDEO_ID.fullmatch(record['youtube_video_id'])):
            raise ValueError('YouTube source metadata or video ID differs')
        if not all(isinstance(record.get(key), str) and record[key].strip() for key in (
                'youtube_title', 'youtube_channel', 'verification_note', 'verified_by', 'checked_at')):
            raise ValueError('YouTube verification evidence is required')
        try:
            checked = datetime.fromisoformat(record['checked_at'].replace('Z', '+00:00'))
            if checked.tzinfo is None: raise ValueError()
        except ValueError:
            raise ValueError('YouTube verification time must include a timezone') from None
        duration = record.get('platform_duration_seconds')
        if (isinstance(duration, bool) or not isinstance(duration, (float, int))
                or not math.isfinite(duration) or duration <= 0):
            raise ValueError('Verified YouTube duration is required')
        snapshot_fields = ('track_id', 'source_track_name', 'source_artists', 'source_album_name',
                           'source_duration_ms', 'youtube_video_id', 'youtube_title', 'youtube_channel',
                           'platform_duration_seconds', 'match_status', 'verification_note',
                           'verified_by', 'checked_at', 'match_method', 'mapping_version')
        records[record['track_id']] = {key: record[key] for key in snapshot_fields if key in record}
    return records, hashlib.sha256(file.read_bytes()).hexdigest()
