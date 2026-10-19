"""Local operator-reviewed YouTube IDs, independent of immutable music catalogs.

No API requests or media downloads occur here. PLAYING is an operator browser
report, not a YouTube-signed attestation or a full listening review.
"""
import csv
import io
import json
import math
import os
import re
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from django.conf import settings

from .errors import DomainError, require


VIDEO_ID = re.compile(r'[A-Za-z0-9_-]{11}\Z')
MAX_CSV_ROWS = 500
MAX_CSV_BYTES = 1_048_576


def registry_path():
    return Path(getattr(settings, 'YOUTUBE_REGISTRY_PATH', settings.BASE_DIR / '.local-preview-logs' / 'youtube-mappings.sqlite3'))


def access_code_path():
    return Path(getattr(settings, 'YOUTUBE_REVIEW_ACCESS_FILE', settings.BASE_DIR / '.local-preview-logs' / 'youtube-review-access.json'))


def initialize_access_code(rotate=False):
    """Create a Git-ignored local secret; callers must never print its value."""
    require(settings.LOCAL_DEMO, 'POLICY_NOT_READY', '로컬 검수 도구에서만 사용할 수 있어요.', 503)
    target = access_code_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not rotate:
        return target
    temporary = target.with_name(target.name + '.' + secrets.token_hex(6) + '.tmp')
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as output:
            json.dump({'access_code': secrets.token_urlsafe(32), 'created_at': _now(), 'is_test': True}, output)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def validate_access_code(value):
    require(settings.LOCAL_DEMO, 'POLICY_NOT_READY', '공유 ADMIN 인증 연결을 기다리고 있어요.', 503)
    try:
        expected = json.loads(access_code_path().read_text(encoding='utf-8'))['access_code']
    except (OSError, ValueError, KeyError, TypeError):
        raise DomainError('REVIEW_NOT_INITIALIZED', '로컬 검수 접근 코드를 먼저 준비해 주세요.', 503) from None
    require(isinstance(value, str) and len(value) <= 256 and value.isascii() and isinstance(expected, str) and expected.isascii()
            and secrets.compare_digest(value, expected), 'REVIEW_ACCESS_DENIED', '검수 접근 코드를 확인해 주세요.', 403)


def normalize_video_url(value):
    """Extract only an allow-listed YouTube HTTPS ID without fetching a URL."""
    require(isinstance(value, str) and 0 < len(value) <= 2048
            and not any(ord(character) < 32 or ord(character) == 127 for character in value))
    value = value.strip()
    if VIDEO_ID.fullmatch(value):
        return value
    try:
        parsed = urlsplit(value)
        require(parsed.scheme == 'https' and parsed.hostname in {'youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtu.be'}
                and parsed.username is None and parsed.password is None and parsed.port in (None, 443)
                and not parsed.fragment and '\\' not in value)
        if parsed.hostname == 'youtu.be':
            require(re.fullmatch(r'/[A-Za-z0-9_-]{11}', parsed.path))
            video_id = parsed.path[1:]
        elif parsed.path == '/watch':
            values = parse_qs(parsed.query, keep_blank_values=True)
            require(len(values.get('v', [])) == 1)
            video_id = values['v'][0]
        else:
            match = re.fullmatch(r'/(?:embed|shorts)/([A-Za-z0-9_-]{11})', parsed.path)
            require(match is not None)
            video_id = match.group(1)
        require(VIDEO_ID.fullmatch(video_id))
        return video_id
    except (ValueError, AttributeError):
        raise DomainError('VALIDATION_ERROR', 'YouTube 영상 URL 또는 11자리 영상 ID를 확인해 주세요.') from None


def _now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _connection(write=False):
    if not settings.LOCAL_DEMO:
        require(getattr(settings, 'YOUTUBE_REGISTRY_BACKEND', 'disabled') == 'database', 'POLICY_NOT_READY', '공유 영상 연결 저장소의 운영 연결을 기다리고 있어요.', 503)
        from .youtube_database import registry_connection
        with registry_connection(write) as connection:
            yield connection
        return
    target = registry_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(target), timeout=15)
    except (OSError, sqlite3.Error):
        raise DomainError('REGISTRY_UNAVAILABLE', '영상 연결 저장소를 사용할 수 없어요.', 503) from None
    connection.row_factory = sqlite3.Row
    try:
        connection.execute('PRAGMA foreign_keys=ON')
        connection.executescript('''
            CREATE TABLE IF NOT EXISTS track_revision (
                track_id TEXT PRIMARY KEY, revision INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS mapping (
                track_id TEXT NOT NULL REFERENCES track_revision(track_id), video_id TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('CANDIDATE','VERIFIED','BLOCKED')),
                source TEXT NOT NULL, note TEXT NOT NULL DEFAULT '', reason TEXT NOT NULL DEFAULT '',
                identity_confirmed INTEGER NOT NULL DEFAULT 0, playback_observed INTEGER NOT NULL DEFAULT 0,
                duration_seconds REAL, observed_at TEXT, updated_at TEXT NOT NULL,
                PRIMARY KEY(track_id,video_id));
            CREATE TABLE IF NOT EXISTS review_audit (
                id INTEGER PRIMARY KEY, track_id TEXT NOT NULL, video_id TEXT NOT NULL,
                action TEXT NOT NULL, revision INTEGER NOT NULL, created_at TEXT NOT NULL);
        ''')
        # Serialize additive migration with writes, including existing local
        # stores created before native navigation became the primary path.
        connection.execute('BEGIN IMMEDIATE')
        columns = {row['name'] for row in connection.execute('PRAGMA table_info(mapping)')}
        for name, definition in (('native_verified', 'INTEGER NOT NULL DEFAULT 0'),
                                 ('native_duration_seconds', 'REAL'),
                                 ('native_observed_at', 'TEXT'),
                                 ('native_source', "TEXT NOT NULL DEFAULT ''"),
                                 ('native_reason', "TEXT NOT NULL DEFAULT ''")):
            if name not in columns:
                connection.execute('ALTER TABLE mapping ADD COLUMN ' + name + ' ' + definition)
        if not write:
            connection.commit()
        yield connection
        if write:
            connection.commit()
    except sqlite3.Error:
        connection.rollback()
        raise DomainError('REGISTRY_UNAVAILABLE', '영상 연결 저장소를 사용할 수 없어요.', 503) from None
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _mapping(row):
    result = dict(row)
    result['video_url'] = 'https://www.youtube.com/watch?v=' + result['video_id']
    result['identity_confirmed'] = bool(result['identity_confirmed'])
    result['playback_observed'] = bool(result['playback_observed'])
    result['native_verified'] = bool(result['native_verified'])
    return result


def read_registry():
    with _connection() as connection:
        result = {row['track_id']: {'revision': row['revision'], 'mappings': []}
                  for row in connection.execute('SELECT * FROM track_revision')}
        for row in connection.execute("SELECT * FROM mapping ORDER BY CASE status WHEN 'VERIFIED' THEN 0 WHEN 'CANDIDATE' THEN 1 ELSE 2 END,updated_at DESC,video_id"):
            result[row['track_id']]['mappings'].append(_mapping(row))
    return result


def track_registry(track_id):
    with _connection() as connection:
        revision = connection.execute('SELECT revision FROM track_revision WHERE track_id=?', (track_id,)).fetchone()
        rows = connection.execute("SELECT * FROM mapping WHERE track_id=? ORDER BY CASE status WHEN 'VERIFIED' THEN 0 WHEN 'CANDIDATE' THEN 1 ELSE 2 END,updated_at DESC,video_id", (track_id,))
        return {'track_id': track_id, 'revision': revision['revision'] if revision else 0,
                'mappings': [_mapping(row) for row in rows]}


def track_registries(track_ids):
    """Read only the requested tracks in bounded batches, on one connection."""
    ids = list(dict.fromkeys(track_ids))
    result = {track_id: {'track_id': track_id, 'revision': 0, 'mappings': []} for track_id in ids}
    if not ids:
        return result
    with _connection() as connection:
        for start in range(0, len(ids), 500):
            batch = ids[start:start + 500]
            slots = ','.join('?' for _ in batch)
            for row in connection.execute(f'SELECT track_id,revision FROM track_revision WHERE track_id IN ({slots})', batch):
                result[row['track_id']]['revision'] = row['revision']
            rows = connection.execute(f"SELECT * FROM mapping WHERE track_id IN ({slots}) ORDER BY CASE status WHEN 'VERIFIED' THEN 0 WHEN 'CANDIDATE' THEN 1 ELSE 2 END,updated_at DESC,video_id", batch)
            for row in rows:
                result[row['track_id']]['mappings'].append(_mapping(row))
    return result


def playback_candidates(track_id, excluded_video_ids=()):
    """Only operator-verified IDs are exposed to public playback."""
    return [{'video_id': item['video_id'], 'title': '', 'channel_title': '',
             'duration_seconds': item['duration_seconds'], 'source': 'LOCAL_REGISTRY',
             'match_status': item['status']}
            for item in track_registry(track_id)['mappings']
            if item['status'] == 'VERIFIED' and item['video_id'] not in excluded_video_ids]


def verified_candidates(track_id, excluded_video_ids=()):
    return playback_candidates(track_id, excluded_video_ids)


def _revision(connection, track_id, expected):
    require(type(expected) is int and expected >= 0)
    connection.execute('INSERT OR IGNORE INTO track_revision(track_id) VALUES(?)', (track_id,))
    current = connection.execute('SELECT revision FROM track_revision WHERE track_id=?', (track_id,)).fetchone()['revision']
    require(current == expected, 'MAPPING_REVISION_CONFLICT', '다른 검수 변경이 있어요. 최신 연결 정보를 다시 확인해 주세요.', 409,
            track_id=track_id, revision=current)
    return current


def _audit(connection, track_id, video_id, action, revision):
    if not settings.LOCAL_DEMO:
        from .youtube_database import review_actor
        connection.execute('INSERT INTO review_audit(track_id,video_id,action,revision,created_at,actor) VALUES(?,?,?,?,?,?)',
                           (track_id, video_id, action, revision, _now(), review_actor.get()))
        return
    connection.execute('INSERT INTO review_audit(track_id,video_id,action,revision,created_at) VALUES(?,?,?,?,?)',
                       (track_id, video_id, action, revision, _now()))


def _note(value):
    require(isinstance(value, str) and len(value) <= 1000)
    return value.strip()


def register_mappings(rows, source='OPERATOR_URL'):
    """Validate all IDs, revisions and duplicate rows before one SQLite commit."""
    require(isinstance(rows, list) and 0 < len(rows) <= MAX_CSV_ROWS)
    normalized, seen, revisions = [], set(), {}
    for index, row in enumerate(rows, 1):
        require(isinstance(row, dict) and not set(row) - {'track_id', 'video_url', 'expected_revision', 'note'})
        track_id = row.get('track_id')
        require(isinstance(track_id, str) and bool(track_id.strip()) and len(track_id) <= 256, row=index)
        try:
            video_id = normalize_video_url(row.get('video_url'))
        except DomainError as error:
            error.details.update(row=index, field='video_url')
            raise
        require((track_id, video_id) not in seen, 'CSV_DUPLICATE_MAPPING', '같은 곡·영상이 중복된 행을 확인해 주세요.', 422, row=index)
        seen.add((track_id, video_id))
        revision = row.get('expected_revision')
        require(type(revision) is int and revision >= 0, row=index)
        require(track_id not in revisions or revisions[track_id] == revision, 'CSV_REVISION_CONFLICT',
                '같은 곡의 예상 revision이 서로 달라요.', 422, row=index)
        revisions[track_id] = revision
        normalized.append((track_id, video_id, _note(row.get('note', ''))))
    with _connection(write=True) as connection:
        for track_id, revision in revisions.items():
            _revision(connection, track_id, revision)
        changed = set()
        for track_id, video_id, note in normalized:
            existing = connection.execute('SELECT * FROM mapping WHERE track_id=? AND video_id=?', (track_id, video_id)).fetchone()
            if existing is None:
                count = connection.execute('SELECT COUNT(*) FROM mapping WHERE track_id=?', (track_id,)).fetchone()[0]
                require(count < 10, 'MAPPING_LIMIT', '한 곡에는 대체 영상을 포함해 최대 10개를 연결할 수 있어요.', 422, track_id=track_id)
                connection.execute("INSERT INTO mapping(track_id,video_id,status,source,note,updated_at) VALUES(?,?,'CANDIDATE',?,?,?)",
                                   (track_id, video_id, source, note, _now()))
                changed.add(track_id)
            elif existing['note'] != note:
                connection.execute('UPDATE mapping SET note=?,updated_at=? WHERE track_id=? AND video_id=?', (note, _now(), track_id, video_id))
                changed.add(track_id)
        for track_id in changed:
            connection.execute('UPDATE track_revision SET revision=revision+1 WHERE track_id=?', (track_id,))
        for track_id, video_id, _ in normalized:
            if track_id in changed:
                _audit(connection, track_id, video_id, 'REGISTER_CANDIDATE', revisions[track_id] + 1)
    return {'imported_count': len(normalized), 'changed_track_count': len(changed),
            'items': [track_registry(track_id) for track_id in revisions]}


def parse_mapping_csv(text):
    require(isinstance(text, str), 'CSV_ENCODING_INVALID', 'UTF-8 CSV 텍스트를 등록해 주세요.')
    try:
        encoded_length = len(text.encode('utf-8'))
    except UnicodeEncodeError:
        raise DomainError('CSV_ENCODING_INVALID', 'UTF-8 CSV 텍스트를 등록해 주세요.') from None
    require(encoded_length <= MAX_CSV_BYTES,
            'CSV_TOO_LARGE', 'CSV는 UTF-8 형식, 1MiB 이하로 등록해 주세요.')
    reader = csv.DictReader(io.StringIO(text.lstrip('\ufeff'), newline=''), strict=True)
    try:
        fields = reader.fieldnames
    except csv.Error:
        raise DomainError('CSV_HEADERS_INVALID', 'CSV 헤더의 따옴표와 구분자를 확인해 주세요.') from None
    require(fields is not None and len(set(fields)) == len(fields)
            and set(fields) in ({'track_id', 'video_url', 'expected_revision'}, {'track_id', 'video_url', 'expected_revision', 'note'}),
            'CSV_HEADERS_INVALID', 'CSV 헤더는 track_id,video_url,expected_revision,note를 사용해 주세요.')
    rows = []
    try:
        for number, row in enumerate(reader, 2):
            require(len(rows) < MAX_CSV_ROWS, 'CSV_TOO_MANY_ROWS', '한 번에 최대 500행을 등록할 수 있어요.')
            require(None not in row and all(value is not None for value in row.values()), 'CSV_ROW_INVALID', 'CSV 열 개수를 확인해 주세요.', row=number)
            revision = row['expected_revision'].strip()
            require(re.fullmatch(r'0|[1-9][0-9]{0,9}', revision), 'CSV_ROW_INVALID', 'revision은 0 이상의 정수여야 해요.', row=number)
            rows.append({**row, 'track_id': row['track_id'].strip(), 'video_url': row['video_url'].strip(), 'expected_revision': int(revision)})
    except csv.Error:
        raise DomainError('CSV_ROW_INVALID', 'CSV 구분자와 따옴표를 확인해 주세요.') from None
    require(rows, 'CSV_EMPTY', 'CSV에 등록할 행이 없어요.')
    return rows


def verify_mapping(track, video_id, expected_revision, identity_confirmed, playback_observed, duration_seconds, note=''):
    require(isinstance(video_id, str) and VIDEO_ID.fullmatch(video_id))
    require(identity_confirmed is True and playback_observed is True, 'REVIEW_INCOMPLETE',
            '원곡 확인과 iframe 실제 재생 관측을 모두 완료해 주세요.')
    require(type(duration_seconds) in (int, float) and math.isfinite(duration_seconds) and 0 < duration_seconds <= 86400)
    original = track['duration_ms'] / 1000
    require(original > 0 and abs(duration_seconds - original) <= min(60, max(12, original * .12)),
            'DURATION_MISMATCH', '원본 곡과 영상 재생시간 차이가 커서 검수를 보류했어요.',
            original_duration_seconds=original, observed_duration_seconds=duration_seconds)
    note = _note(note)
    track_id = track['track_id']
    with _connection(write=True) as connection:
        _revision(connection, track_id, expected_revision)
        exists = connection.execute('SELECT 1 FROM mapping WHERE track_id=? AND video_id=?', (track_id, video_id)).fetchone()
        require(exists is not None, 'NOT_FOUND', '등록된 영상 연결을 찾을 수 없어요.', 404)
        connection.execute("UPDATE mapping SET status='VERIFIED',identity_confirmed=1,playback_observed=1,duration_seconds=?,observed_at=?,updated_at=?,note=?,reason='' WHERE track_id=? AND video_id=?",
                           (duration_seconds, _now(), _now(), note, track_id, video_id))
        connection.execute('UPDATE track_revision SET revision=revision+1 WHERE track_id=?', (track_id,))
        _audit(connection, track_id, video_id, 'VERIFY_OPERATOR_REPORTED_PLAYING', expected_revision + 1)
    return track_registry(track_id)


def verify_native_mapping(track, video_id, expected_revision, identity_confirmed, playback_observed, duration_seconds, note='', duration_difference_confirmed=False):
    """Store a trusted operator's manual native-player report, separately from iframe."""
    require(isinstance(video_id, str) and VIDEO_ID.fullmatch(video_id))
    require(identity_confirmed is True and playback_observed is True, 'REVIEW_INCOMPLETE',
            '원곡 정보와 외부 YouTube 실제 재생을 모두 확인해 주세요.')
    require(type(duration_seconds) in (int, float) and math.isfinite(duration_seconds) and 0 < duration_seconds <= 86400)
    require(type(duration_difference_confirmed) is bool)
    note = _note(note)
    original = track['duration_ms'] / 1000
    difference = abs(duration_seconds - original)
    standard_limit = min(60, max(12, original * .12))
    acknowledged_difference = duration_difference_confirmed and bool(note) and difference <= 60
    require(original > 0 and (difference <= standard_limit or acknowledged_difference),
            'DURATION_MISMATCH', '원본 곡과 영상 재생시간 차이가 커서 외부 재생 검수를 보류했어요.',
            original_duration_seconds=original, observed_duration_seconds=duration_seconds)
    track_id = track['track_id']
    with _connection(write=True) as connection:
        _revision(connection, track_id, expected_revision)
        exists = connection.execute('SELECT 1 FROM mapping WHERE track_id=? AND video_id=?', (track_id, video_id)).fetchone()
        require(exists is not None, 'NOT_FOUND', '등록된 영상 연결을 찾을 수 없어요.', 404)
        connection.execute("UPDATE mapping SET native_verified=1,native_duration_seconds=?,native_observed_at=?,native_source='OPERATOR_NATIVE_REPORTED_PLAYING',native_reason='',updated_at=?,note=? WHERE track_id=? AND video_id=?",
                           (duration_seconds, _now(), _now(), note, track_id, video_id))
        connection.execute('UPDATE track_revision SET revision=revision+1 WHERE track_id=?', (track_id,))
        action = ('VERIFY_NATIVE_DURATION_DIFFERENCE_ACK' if difference > standard_limit
                  else 'VERIFY_OPERATOR_REPORTED_NATIVE_PLAYING')
        _audit(connection, track_id, video_id, action, expected_revision + 1)
    return track_registry(track_id)


def block_mapping(track_id, video_id, expected_revision, reason):
    require(isinstance(video_id, str) and VIDEO_ID.fullmatch(video_id))
    reason = _note(reason)
    require(reason, message='차단 또는 보류 사유를 입력해 주세요.')
    with _connection(write=True) as connection:
        _revision(connection, track_id, expected_revision)
        exists = connection.execute('SELECT 1 FROM mapping WHERE track_id=? AND video_id=?', (track_id, video_id)).fetchone()
        require(exists is not None, 'NOT_FOUND', '등록된 영상 연결을 찾을 수 없어요.', 404)
        connection.execute("UPDATE mapping SET status='BLOCKED',reason=?,updated_at=? WHERE track_id=? AND video_id=?", (reason, _now(), track_id, video_id))
        connection.execute('UPDATE track_revision SET revision=revision+1 WHERE track_id=?', (track_id,))
        _audit(connection, track_id, video_id, 'BLOCK', expected_revision + 1)
    return track_registry(track_id)


def block_native_mapping(track_id, video_id, expected_revision, reason):
    """Revoke native readiness without changing the separate iframe decision."""
    require(isinstance(video_id, str) and VIDEO_ID.fullmatch(video_id))
    reason = _note(reason)
    require(reason, message='외부 재생 연결 철회 사유를 입력해 주세요.')
    with _connection(write=True) as connection:
        _revision(connection, track_id, expected_revision)
        exists = connection.execute('SELECT 1 FROM mapping WHERE track_id=? AND video_id=?', (track_id, video_id)).fetchone()
        require(exists is not None, 'NOT_FOUND', '등록된 영상 연결을 찾을 수 없어요.', 404)
        connection.execute("UPDATE mapping SET native_verified=0,native_source='OPERATOR_NATIVE_BLOCK',native_reason=?,updated_at=? WHERE track_id=? AND video_id=?",
                           (reason, _now(), track_id, video_id))
        connection.execute('UPDATE track_revision SET revision=revision+1 WHERE track_id=?', (track_id,))
        _audit(connection, track_id, video_id, 'BLOCK_NATIVE', expected_revision + 1)
    return track_registry(track_id)


def seed_legacy_mappings(tracks):
    """Import old IDs as pending only; never override a later operator decision."""
    inserted = 0
    with _connection(write=True) as connection:
        changed = set()
        for track in tracks:
            video_id = track.get('youtube_video_id')
            if not isinstance(video_id, str) or not VIDEO_ID.fullmatch(video_id):
                continue
            track_id = track['track_id']
            connection.execute('INSERT OR IGNORE INTO track_revision(track_id) VALUES(?)', (track_id,))
            cursor = connection.execute("INSERT OR IGNORE INTO mapping(track_id,video_id,status,source,note,updated_at) VALUES(?,?,'CANDIDATE','LEGACY_REVIEW_PENDING',?,?)",
                                        (track_id, video_id, '기존 외부 연결 자료이며 iframe 삽입 및 원곡 재검수 대기', _now()))
            if cursor.rowcount:
                inserted += 1
                changed.add(track_id)
                _audit(connection, track_id, video_id, 'SEED_LEGACY_PENDING', 0)
        for track_id in changed:
            connection.execute('UPDATE track_revision SET revision=revision+1 WHERE track_id=?', (track_id,))
    return {'inserted_count': inserted, 'changed_track_count': len(changed)}


def seed_native_reviewed_mappings(tracks):
    """Preserve prior identity/native-queue metadata evidence, never claim PLAYING.

Only the previously reviewed one-to-one metadata snapshot qualifies. This is
an explicit operator command, not a public resolver fallback or iframe approval.
"""
    eligible = []
    for track in tracks:
        snapshot = track.get('youtube_mapping_snapshot')
        if not isinstance(snapshot, dict) or track.get('youtube_match_status') != 'VERIFIED':
            continue
        video_id = track.get('youtube_video_id')
        duration = snapshot.get('platform_duration_seconds')
        if not (snapshot.get('match_status') == 'VERIFIED'
                and snapshot.get('match_method') == 'PRIMARY_METADATA_AND_NATIVE_QUEUE_INCLUSION'
                and isinstance(video_id, str) and VIDEO_ID.fullmatch(video_id)
                and snapshot.get('youtube_video_id') == video_id
                and snapshot.get('track_id') == track['track_id']
                and snapshot.get('source_track_name') == track['track_name']
                and snapshot.get('source_artists') == track['artists_name']
                and snapshot.get('source_album_name') == track.get('album_name')
                and type(snapshot.get('source_duration_ms')) is int
                and snapshot['source_duration_ms'] == track['duration_ms']
                and all(isinstance(snapshot.get(key), str) and snapshot[key].strip()
                        for key in ('youtube_title', 'youtube_channel', 'verification_note', 'verified_by', 'checked_at', 'mapping_version'))
                and type(duration) in (int, float) and math.isfinite(duration) and duration > 0):
            continue
        try:
            checked = datetime.fromisoformat(snapshot['checked_at'].replace('Z', '+00:00'))
            if checked.tzinfo is None:
                continue
        except ValueError:
            continue
        original = track['duration_ms'] / 1000
        if original <= 0 or abs(duration - original) > min(60, max(12, original * .12)):
            continue
        eligible.append((track['track_id'], video_id, duration, snapshot['checked_at']))
    changed = 0
    with _connection(write=True) as connection:
        changed_tracks = set()
        for track_id, video_id, duration, checked_at in eligible:
            connection.execute('INSERT OR IGNORE INTO track_revision(track_id) VALUES(?)', (track_id,))
            connection.execute("INSERT OR IGNORE INTO mapping(track_id,video_id,status,source,note,updated_at) VALUES(?,?,'CANDIDATE','LEGACY_REVIEW_PENDING',?,?)",
                               (track_id, video_id, '기존 원곡 메타데이터·한국 제공·외부 큐 검수 자료; 전곡 재생 관측 또는 청취 아님', _now()))
            existing = connection.execute('SELECT native_verified,native_source FROM mapping WHERE track_id=? AND video_id=?', (track_id, video_id)).fetchone()
            if existing['native_verified'] or existing['native_source'] == 'OPERATOR_NATIVE_BLOCK':
                continue
            connection.execute("UPDATE mapping SET native_verified=1,native_duration_seconds=?,native_observed_at=?,native_source='LEGACY_NATIVE_METADATA_REVIEW',updated_at=? WHERE track_id=? AND video_id=?",
                               (duration, checked_at, _now(), track_id, video_id))
            changed += 1
            changed_tracks.add(track_id)
            revision = connection.execute('SELECT revision FROM track_revision WHERE track_id=?', (track_id,)).fetchone()['revision'] + 1
            _audit(connection, track_id, video_id, 'SEED_LEGACY_NATIVE_METADATA_ONLY', revision)
        for track_id in changed_tracks:
            connection.execute('UPDATE track_revision SET revision=revision+1 WHERE track_id=?', (track_id,))
    return {'eligible_count': len(eligible), 'native_verified_count': changed, 'changed_track_count': len(changed_tracks)}
