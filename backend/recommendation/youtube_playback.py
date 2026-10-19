"""Resolve owned snapshot metadata to iframe candidates without an LLM.

The caller authorizes the playlist and selects a track from its immutable items.
Automatic matches stay CANDIDATE; playback success and recording identity are
not inferred from public API metadata or an old external-navigation mapping.
"""
import hashlib
import json
import math
import re
import unicodedata
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from django.conf import settings
from django.core.cache import cache

from .errors import require
from .youtube import VIDEO_ID
from . import youtube_registry


POLICY_VERSION = 'youtube-iframe-candidates-20261016.1'
MAX_EXCLUDED = 10
MESSAGES = {
    'API_KEY_MISSING': '자동 영상 검색용 YouTube API 키가 아직 연결되지 않았어요. 이미 확인한 영상은 재생할 수 있어요.',
    'API_QUOTA_EXCEEDED': 'YouTube 영상 검색 할당량을 모두 사용했어요. 이미 찾은 영상은 계속 사용할 수 있어요.',
    'API_AUTH_FAILED': 'YouTube 영상 검색 연결 설정을 확인해야 해요. 이미 찾은 영상은 계속 사용할 수 있어요.',
    'API_NETWORK_ERROR': 'YouTube 영상 검색에 연결하지 못했어요. 잠시 후 다시 시도해 주세요.',
    'API_INVALID_RESPONSE': 'YouTube 영상 정보를 확인하지 못했어요. 잠시 후 다시 시도해 주세요.',
    'API_RATE_LIMITED': '영상 검색 요청이 많아요. 잠시 후 다시 시도해 주세요.',
    'API_DAILY_LIMIT': '오늘의 자동 영상 검색 한도에 도달했어요. 이미 찾은 영상은 계속 사용할 수 있어요.',
    'API_BUSY': '이 곡의 영상을 확인하고 있어요. 잠시 후 다시 시도해 주세요.',
}


class SearchFailure(Exception):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def validate_playback_request(body):
    """Accept identifiers only; never accept a client URL, query or API key."""
    require(isinstance(body, dict) and not set(body) - {'track_id', 'excluded_video_ids'})
    track_id = body.get('track_id')
    require(isinstance(track_id, str) and bool(track_id.strip()) and len(track_id) <= 256)
    excluded = body.get('excluded_video_ids', [])
    require(isinstance(excluded, list) and len(excluded) <= MAX_EXCLUDED
            and all(isinstance(value, str) and VIDEO_ID.fullmatch(value) for value in excluded))
    require(len(set(excluded)) == len(excluded))
    return track_id, excluded


def _text(value):
    value = unicodedata.normalize('NFKD', str(value or '')).casefold()
    value = ''.join(character for character in value if not unicodedata.combining(character))
    return ' '.join(re.findall(r'[^\W_]+', value, flags=re.UNICODE))


def _tokens(value):
    return set(_text(value).split())


def _duration(value):
    match = re.fullmatch(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?', str(value or ''))
    if not match or not any(match.groups()):
        return None
    hours, minutes, seconds = match.groups()
    result = int(hours or 0) * 3600 + int(minutes or 0) * 60 + float(seconds or 0)
    return result if result > 0 else None


def _catalog_candidate(track):
    video_id = track.get('youtube_video_id')
    if track.get('youtube_match_status') != 'VERIFIED' or not isinstance(video_id, str) or not VIDEO_ID.fullmatch(video_id):
        return None
    snapshot = track.get('youtube_mapping_snapshot') or {}
    duration = snapshot.get('platform_duration_seconds')
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration <= 0:
        duration = track.get('duration_ms', 0) / 1000
    return {'video_id': video_id,
            'title': snapshot.get('youtube_title') or track['track_name'],
            'channel_title': snapshot.get('youtube_channel') or track['artists_name'],
            'duration_seconds': duration, 'source': 'CATALOG_MAPPING', 'match_status': 'VERIFIED'}


def _api_json(resource, parameters, api_key):
    """Fixed HTTPS API host; errors never include a credential-bearing URL."""
    url = 'https://www.googleapis.com/youtube/v3/' + resource + '?' + urlencode({**parameters, 'key': api_key})
    timeout = max(1.0, min(15.0, float(getattr(settings, 'YOUTUBE_SEARCH_TIMEOUT_SECONDS', 8))))
    request = Request(url, headers={'Accept': 'application/json', 'User-Agent': 'CafeMusic-YouTubeResolver/1'})
    try:
        with build_opener(NoRedirect()).open(request, timeout=timeout) as response:
            payload = json.loads(response.read(2_000_001))
    except HTTPError as error:
        try:
            errors = json.loads(error.read(32768)).get('error', {}).get('errors', [])
            reasons = {entry.get('reason') for entry in errors if isinstance(entry, dict)}
        except (ValueError, TypeError, AttributeError):
            reasons = set()
        if reasons & {'quotaExceeded', 'dailyLimitExceeded', 'dailyLimitExceededUnreg'}:
            reason = 'API_QUOTA_EXCEEDED'
        elif error.code == 429 or reasons & {'rateLimitExceeded', 'userRateLimitExceeded'}:
            reason = 'API_RATE_LIMITED'
        elif error.code in (400, 401, 403):
            reason = 'API_AUTH_FAILED'
        else:
            reason = 'API_NETWORK_ERROR'
        raise SearchFailure(reason) from None
    except (URLError, TimeoutError, OSError):
        raise SearchFailure('API_NETWORK_ERROR') from None
    except (ValueError, UnicodeDecodeError):
        raise SearchFailure('API_INVALID_RESPONSE') from None
    if not isinstance(payload, dict) or not isinstance(payload.get('items'), list):
        raise SearchFailure('API_INVALID_RESPONSE')
    return payload['items']


def _match_candidate(track, video):
    """Conservative metadata matching; no claimed human verification."""
    if not isinstance(video, dict):
        return None
    video_id = video.get('id')
    if not isinstance(video_id, str) or not VIDEO_ID.fullmatch(video_id):
        return None
    status, details, snippet = video.get('status') or {}, video.get('contentDetails') or {}, video.get('snippet') or {}
    if not all(isinstance(value, dict) for value in (status, details, snippet)):
        return None
    if status.get('embeddable') is not True or status.get('privacyStatus') != 'public':
        return None
    if snippet.get('liveBroadcastContent', 'none') != 'none':
        return None
    restrictions = details.get('regionRestriction') or {}
    if not isinstance(restrictions, dict) or 'KR' in restrictions.get('blocked', []) or ('allowed' in restrictions and 'KR' not in restrictions['allowed']):
        return None
    content_rating = details.get('contentRating') or {}
    if not isinstance(content_rating, dict) or content_rating.get('ytRating') == 'ytAgeRestricted':
        return None
    duration = _duration(details.get('duration'))
    source_duration = track['duration_ms'] / 1000
    if not duration or source_duration <= 0 or abs(duration - source_duration) > min(60, max(12, source_duration * .12)):
        return None
    title = snippet.get('title')
    channel = snippet.get('channelTitle')
    if not isinstance(title, str) or not isinstance(channel, str) or not title.strip() or not channel.strip():
        return None
    source_tokens = _tokens(track['track_name'])
    title_tokens = _tokens(title)
    # These variants must already be named by the original recording metadata.
    variant_words = {'live', 'remix', 'cover', 'karaoke', 'instrumental', 'slowed', 'sped', 'nightcore',
                     'reaction', 'tutorial', '8d', 'piano', 'acoustic', 'concert', '라이브', '커버', '노래방'}
    source_variants = _tokens(track['track_name'] + ' ' + track.get('album_name', ''))
    if (title_tokens & variant_words) - source_variants:
        return None
    # Remove release/version annotation tokens from title coverage only when
    # the source itself supplied those markers; preserve the variant guard.
    song_tokens = source_tokens - {'feat', 'ft', 'featuring', 'remastered', 'remaster', 'version', 'edit'}
    if not song_tokens or len(song_tokens & title_tokens) / len(song_tokens) < .8:
        return None
    artist = track['artists_name'].split(';')[0]
    artist_tokens = _tokens(artist)
    identity_tokens = _tokens(title + ' ' + channel + ' ' + str(snippet.get('description', ''))[:2000])
    if not artist_tokens or len(artist_tokens & identity_tokens) / len(artist_tokens) < .75:
        return None
    title_coverage = len(song_tokens & title_tokens) / len(song_tokens)
    artist_coverage = len(artist_tokens & _tokens(title + ' ' + channel)) / len(artist_tokens)
    score = 70 * title_coverage + 20 * artist_coverage + 10 * (1 - abs(duration - source_duration) / max(source_duration, 1))
    return {'video_id': video_id, 'title': title[:500], 'channel_title': channel[:300],
            'duration_seconds': duration, 'source': 'YOUTUBE_API', 'match_status': 'CANDIDATE', '_score': score}


def _search(track, api_key):
    artists = track['artists_name'].replace(';', ' ')
    query = (track['track_name'] + ' ' + artists)[:300]
    found = _api_json('search', {'part': 'snippet', 'type': 'video', 'q': query,
        'videoEmbeddable': 'true', 'videoSyndicated': 'true', 'regionCode': 'KR',
        'maxResults': 5, 'order': 'relevance'}, api_key)
    ids = []
    for item in found:
        video_id = item.get('id', {}).get('videoId') if isinstance(item, dict) and isinstance(item.get('id'), dict) else None
        if isinstance(video_id, str) and VIDEO_ID.fullmatch(video_id) and video_id not in ids:
            ids.append(video_id)
    if not ids:
        return []
    videos = _api_json('videos', {'part': 'snippet,contentDetails,status', 'id': ','.join(ids)}, api_key)
    matches = [candidate for video in videos if (candidate := _match_candidate(track, video)) and candidate['video_id'] in ids]
    matches.sort(key=lambda candidate: (-candidate['_score'], candidate['video_id']))
    unique = {}
    for candidate in matches:
        candidate.pop('_score')
        unique.setdefault(candidate['video_id'], candidate)
    return list(unique.values())


def _reserve_search(owner_id):
    """Cache atomic counters bound misses, including concurrent cache misses."""
    now = datetime.now(timezone.utc)
    owner_hash = hashlib.sha256(str(owner_id).encode()).hexdigest()[:24]
    minute = now.strftime('%Y%m%d%H%M')
    owner_limit = max(0, int(getattr(settings, 'YOUTUBE_SEARCH_PER_OWNER_MINUTE', 6)))
    owner_key = f'ytp:rate:{owner_hash}:{minute}'
    cache.add(owner_key, 0, timeout=120)
    if cache.incr(owner_key) > owner_limit:
        raise SearchFailure('API_RATE_LIMITED')
    day_key = 'ytp:daily:' + now.strftime('%Y%m%d')
    daily_limit = max(0, int(getattr(settings, 'YOUTUBE_SEARCH_DAILY_LIMIT', 80)))
    cache.add(day_key, 0, timeout=90_000)
    if cache.incr(day_key) > daily_limit:
        raise SearchFailure('API_DAILY_LIMIT')


def _lookup(track, owner_id, api_key):
    identity = {key: track.get(key) for key in ('track_id', 'track_name', 'artists_name', 'album_name', 'duration_ms')}
    identity['policy'] = POLICY_VERSION
    identity['key_fingerprint'] = hashlib.sha256(api_key.encode()).hexdigest()[:16]
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    cache_key = 'ytp:candidates:' + digest
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    lock_key = 'ytp:inflight:' + digest
    if not cache.add(lock_key, True, timeout=45):
        raise SearchFailure('API_BUSY')
    try:
        # A thread that completed just before lock acquisition may have filled it.
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        _reserve_search(owner_id)
        try:
            candidates = _search(track, api_key)
            cached = {'candidates': candidates}
            ttl = int(getattr(settings, 'YOUTUBE_SEARCH_CACHE_SECONDS', 21_600)) if candidates else 600
        except SearchFailure as failure:
            cached = {'candidates': [], 'reason': failure.reason}
            ttl = 60
        cache.set(cache_key, cached, timeout=max(1, min(86_400, ttl)))
        return cached
    finally:
        cache.delete(lock_key)


def resolve_playback_candidates(track, excluded_video_ids=(), owner_id=''):
    """Read-only, lazy resolution for one authorized immutable result item."""
    if getattr(settings, 'YOUTUBE_PLAYBACK_MODE', 'KEYLESS') == 'KEYLESS':
        return _keyless_candidates(track, excluded_video_ids)
    excluded = set(excluded_video_ids)
    mapped = _catalog_candidate(track)
    if mapped and mapped['video_id'] not in excluded:
        return {'track_id': track['track_id'], 'status': 'READY', 'candidates': [mapped]}
    api_key = str(getattr(settings, 'YOUTUBE_DATA_API_KEY', '') or '').strip()
    if not api_key:
        return {'track_id': track['track_id'], 'status': 'SEARCH_UNAVAILABLE', 'candidates': [],
                'reason': 'API_KEY_MISSING', 'message': MESSAGES['API_KEY_MISSING']}
    try:
        found = _lookup(track, owner_id, api_key)
    except SearchFailure as failure:
        found = {'candidates': [], 'reason': failure.reason}
    candidates = [candidate for candidate in found['candidates'] if candidate['video_id'] not in excluded]
    if candidates:
        return {'track_id': track['track_id'], 'status': 'READY', 'candidates': candidates}
    reason = found.get('reason')
    if reason:
        return {'track_id': track['track_id'], 'status': 'SEARCH_UNAVAILABLE', 'candidates': [],
                'reason': reason, 'message': MESSAGES[reason]}
    return {'track_id': track['track_id'], 'status': 'NO_MATCH', 'candidates': [],
            'message': '검색한 후보에서 원곡명·아티스트·길이가 맞는 한국 재생 가능 삽입 영상을 찾지 못했어요.'}


def _keyless_candidates(track, excluded_video_ids):
    """Never fall through to native metadata or remote search in keyless mode."""
    from .errors import DomainError
    if not settings.LOCAL_DEMO and getattr(settings,'YOUTUBE_REGISTRY_BACKEND','disabled') != 'database':
        return {'track_id': track['track_id'], 'status': 'SEARCH_UNAVAILABLE', 'candidates': [],
                'reason': 'REGISTRY_NOT_CONFIGURED', 'message': '공유 영상 연결 저장소의 운영 연결을 기다리고 있어요.'}
    try:
        registered = youtube_registry.track_registry(track['track_id'])
    except (DomainError, OSError):
        return {'track_id': track['track_id'], 'status': 'SEARCH_UNAVAILABLE', 'candidates': [],
                'reason': 'REGISTRY_UNAVAILABLE', 'message': '영상 연결 저장소에 연결하지 못했어요. 잠시 후 다시 확인해 주세요.'}
    excluded = set(excluded_video_ids)
    candidates = [{'video_id': row['video_id'], 'title': track['track_name'],
                   'channel_title': track['artists_name'], 'duration_seconds': row['duration_seconds'],
                   'source': 'MAPPING_REGISTRY', 'match_status': 'VERIFIED'}
                  for row in registered['mappings'] if row['status'] == 'VERIFIED'
                  and row['identity_confirmed'] and row['playback_observed']
                  and row['duration_seconds'] and row['video_id'] not in excluded]
    if candidates:
        return {'track_id': track['track_id'], 'status': 'READY', 'candidates': candidates[:5],
                'mapping_revision': registered['revision']}
    reason = ('UNMAPPED' if not registered['mappings'] else
              'PENDING' if any(row['status'] == 'CANDIDATE' for row in registered['mappings']) else 'BLOCKED')
    return {'track_id': track['track_id'], 'status': 'MAPPING_REQUIRED', 'candidates': [],
            'reason': reason, 'mapping_revision': registered['revision'],
            'message': '이 곡은 영상 연결 검수가 필요해요. 다음 곡을 재생하고 검수 목록에 남겨 둘게요.'}
