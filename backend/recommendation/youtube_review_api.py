"""Local review APIs. A separate production ADMIN adapter is still required."""
from django.conf import settings
from rest_framework.response import Response

from . import service
from .api import Endpoint
from .errors import DomainError, require
from .models import Playlist
from . import youtube_registry as registry


def _body(body, allowed, required=()):
    require(isinstance(body, dict) and not set(body) - set(allowed) and set(required) <= set(body))
    return body


def _positive_int(value, default, maximum):
    if value is None:
        return default
    require(isinstance(value, str) and value.isdigit() and 1 <= int(value) <= maximum)
    return int(value)


def _scope(request, owner):
    playlist_id = request.query_params.get('playlist_id') if request.method == 'GET' else request.data.get('playlist_id')
    if playlist_id:
        require(isinstance(playlist_id, str) and len(playlist_id) <= 256)
        playlist = service.owned(Playlist, owner, playlist_id)
        return playlist.snapshot['items']
    if settings.LOCAL_DEMO:
        return service.catalog().tracks
    from .worker import verified_catalog
    return verified_catalog(service.catalog())


def _known_tracks(request, owner, ids):
    require(all(isinstance(value, str) and 0 < len(value) <= 256 for value in ids))
    # Registration is against the current general catalog, optionally an owned
    # historical playlist. It never creates music records from arbitrary text.
    tracks = _scope(request, owner)
    result = {item['track_id']: item for item in tracks if item['track_id'] in ids}
    missing = set(ids) - result.keys()
    require(not missing, 'TRACK_NOT_FOUND', '일반 카탈로그 또는 본인 선곡표에 없는 곡이 있어요.', 422,
            track_ids=sorted(missing)[:20])
    return result


def _state(mappings):
    if any(item['status'] == 'VERIFIED' or item.get('native_verified') for item in mappings):
        return 'VERIFIED'
    if any(item['status'] == 'CANDIDATE' for item in mappings):
        return 'PENDING'
    return 'BLOCKED' if mappings else 'UNMAPPED'


class ReviewEndpoint(Endpoint):
    def dispatch(self,request,*args,**kwargs):
        from .youtube_database import review_actor
        token=review_actor.set('system')
        try:return super().dispatch(request,*args,**kwargs)
        finally:review_actor.reset(token)

    def authorize(self, request):
        if settings.LOCAL_DEMO:
            registry.validate_access_code(request.headers.get('X-Youtube-Review-Code'))
        else:
            require(getattr(settings,'YOUTUBE_REGISTRY_BACKEND','disabled')=='database','POLICY_NOT_READY','영상 연결 저장소 설정이 필요합니다.',503)
            from backend.common.identity import admin
            from .youtube_database import review_actor
            user=admin(request,'manage_music')
            review_actor.set(str(user.pk))
        return self.owner(request)


class ReviewStatus(Endpoint):
    def get(self, request):
        if settings.LOCAL_DEMO:
            return Response({'enabled':True,'is_test':True,'auth_mode':'LOCAL_CODE','access_code_file':str(registry.access_code_path())})
        from django.contrib.auth import get_user
        from backend.common.identity import raw_request
        user=get_user(raw_request(request))
        from backend.common.admin_roles import permitted
        allowed=bool(user.is_authenticated and user.is_active and user.is_staff and permitted(user, 'manage_music'))
        return Response({'enabled':getattr(settings,'YOUTUBE_REGISTRY_BACKEND','disabled')=='database','is_test':False,'auth_mode':'ADMIN_SESSION','authenticated':allowed})


class ReviewTracks(ReviewEndpoint):
    def get(self, request):
        owner = self.authorize(request)
        tracks = _scope(request, owner)
        data = registry.read_registry()
        query = request.query_params.get('q', '').strip().casefold()
        status = request.query_params.get('status', 'ALL')
        require(len(query) <= 200 and status in {'ALL', 'UNMAPPED', 'PENDING', 'VERIFIED', 'BLOCKED'})
        page = _positive_int(request.query_params.get('page'), 1, 1_000_000)
        size = _positive_int(request.query_params.get('page_size'), 30, 100)
        summary = {'total': len(tracks), 'unmapped': 0, 'pending': 0, 'verified': 0, 'blocked': 0}
        matched = []
        for track in tracks:
            entry = data.get(track['track_id'], {'revision': 0, 'mappings': []})
            state = _state(entry['mappings'])
            summary[state.lower()] += 1
            if (status != 'ALL' and state != status) or (query and query not in ' '.join(str(track.get(key, '')) for key in ('track_id', 'track_name', 'artists_name')).casefold()):
                continue
            matched.append({key: track[key] for key in ('track_id', 'track_name', 'artists_name', 'duration_ms')} | entry | {'state': state})
        return Response({'items': matched[(page-1)*size:page*size], 'total': len(matched),
                         'page': page, 'page_size': size, 'summary': summary})


class ReviewMappings(ReviewEndpoint):
    def post(self, request):
        owner = self.authorize(request)
        body = _body(request.data, {'track_id', 'video_url', 'expected_revision', 'note', 'playlist_id'},
                     {'track_id', 'video_url', 'expected_revision'})
        _known_tracks(request, owner, [body['track_id']])
        row = {key: value for key, value in body.items() if key != 'playlist_id'}
        return Response(registry.register_mappings([row]))


class ReviewImport(ReviewEndpoint):
    def post(self, request):
        owner = self.authorize(request)
        body = _body(request.data, {'csv_text', 'playlist_id'}, {'csv_text'})
        try:
            rows = registry.parse_mapping_csv(body['csv_text'])
        except DomainError as error:
            if error.details.get('row'):
                error.details['row_errors'] = [{'row': error.details['row'], 'message': error.message}]
            raise
        try:
            _known_tracks(request, owner, [item['track_id'] for item in rows])
        except DomainError as error:
            if error.code == 'TRACK_NOT_FOUND':
                missing = set(error.details['track_ids'])
                error.details['row_errors'] = [{'row': index, 'field': 'track_id', 'message': error.message}
                                              for index, row in enumerate(rows, 2) if row['track_id'] in missing]
            raise
        try:
            return Response(registry.register_mappings(rows, source='OPERATOR_CSV'))
        except DomainError as error:
            row = error.details.get('row')
            if row is not None:
                error.details['row'] = row + 1
                error.details['row_errors'] = [{'row': row + 1, 'message': error.message}]
            elif error.details.get('track_id'):
                error.details['row_errors'] = [{'row': index, 'message': error.message}
                                              for index, row in enumerate(rows, 2) if row['track_id'] == error.details['track_id']]
            raise


class ReviewVerify(ReviewEndpoint):
    def post(self, request):
        owner = self.authorize(request)
        body = _body(request.data, {'track_id', 'video_id', 'expected_revision', 'identity_confirmed',
                                  'playback_observed', 'duration_seconds', 'note', 'playlist_id'},
                     {'track_id', 'video_id', 'expected_revision', 'identity_confirmed', 'playback_observed', 'duration_seconds'})
        track = _known_tracks(request, owner, [body['track_id']])[body['track_id']]
        return Response(registry.verify_mapping(track, body['video_id'], body['expected_revision'],
                        body['identity_confirmed'], body['playback_observed'], body['duration_seconds'], body.get('note', '')))


class ReviewBlock(ReviewEndpoint):
    def post(self, request):
        owner = self.authorize(request)
        body = _body(request.data, {'track_id', 'video_id', 'expected_revision', 'reason', 'playlist_id'},
                     {'track_id', 'video_id', 'expected_revision', 'reason'})
        _known_tracks(request, owner, [body['track_id']])
        return Response(registry.block_mapping(body['track_id'], body['video_id'], body['expected_revision'], body['reason']))


class ReviewNativeVerify(ReviewEndpoint):
    def post(self, request):
        owner = self.authorize(request)
        body = _body(request.data, {'track_id', 'video_id', 'expected_revision', 'identity_confirmed',
                                  'playback_observed', 'duration_seconds', 'note', 'playlist_id', 'duration_difference_confirmed'},
                     {'track_id', 'video_id', 'expected_revision', 'identity_confirmed', 'playback_observed', 'duration_seconds'})
        track = _known_tracks(request, owner, [body['track_id']])[body['track_id']]
        return Response(registry.verify_native_mapping(track, body['video_id'], body['expected_revision'],
                        body['identity_confirmed'], body['playback_observed'], body['duration_seconds'], body.get('note', ''),
                        body.get('duration_difference_confirmed', False)))


class ReviewNativeBlock(ReviewEndpoint):
    def post(self, request):
        owner = self.authorize(request)
        body = _body(request.data, {'track_id', 'video_id', 'expected_revision', 'reason', 'playlist_id'},
                     {'track_id', 'video_id', 'expected_revision', 'reason'})
        _known_tracks(request, owner, [body['track_id']])
        return Response(registry.block_native_mapping(body['track_id'], body['video_id'], body['expected_revision'], body['reason']))
