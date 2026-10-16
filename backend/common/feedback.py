"""본인 결과 버전에 귀속된 운영 평가 상태와 원자 이벤트 저장."""

from backend.recommendation.errors import require
from backend.recommendation.inputs import shape, strict_int
from .models import FeedbackState
from backend.recommendation.models import Playlist
from backend.recommendation.service import event, mutate, owned


def read(owner, playlist_id):
    playlist = owned(Playlist, owner, playlist_id)
    states = {(row.target_kind, row.track_id): row for row in FeedbackState.objects.filter(playlist=playlist)}
    reactions = [
        {'track_id': item['track_id'],
         'reaction': states[('TRACK', item['track_id'])].value if ('TRACK', item['track_id']) in states else None,
         'revision': states[('TRACK', item['track_id'])].revision if ('TRACK', item['track_id']) in states else 0}
        for item in playlist.snapshot['items']
    ]
    rating = states.get(('PLAYLIST', ''))
    return {'source_playlist_id': playlist.pk, 'track_reactions': reactions,
            'playlist_rating': {'rating': rating.value if rating else None, 'revision': rating.revision if rating else 0}}


def save(owner, playlist_id, target_kind, track_id, data, key, request_id):
    playlist = owned(Playlist, owner, playlist_id)
    field = 'reaction' if target_kind == 'TRACK' else 'rating'
    body = shape(data, [field, 'expected_revision'], [field, 'expected_revision'])
    value = body[field]
    if target_kind == 'TRACK':
        require(type(track_id) is str and track_id in {item['track_id'] for item in playlist.snapshot['items']},
                'NOT_FOUND', '평가할 곡을 찾을 수 없어요.', 404)
        require(value is None or type(value) is str and value in ('LIKE', 'DISLIKE'),
                'VALIDATION_ERROR', '곡 반응을 확인해 주세요.')
    else:
        require(value is None or type(value) is int and 1 <= value <= 5,
                'VALIDATION_ERROR', '별점은 1~5점으로 선택해 주세요.')
        track_id = ''
    body = {field: value, 'expected_revision': strict_int(body['expected_revision'])}

    def op():
        source = owned(Playlist, owner, playlist_id)
        state = FeedbackState.objects.select_for_update().filter(
            playlist=source, target_kind=target_kind, track_id=track_id).first()
        current_value = state.value if state else None
        revision = state.revision if state else 0
        require(body['expected_revision'] == revision, 'FEEDBACK_REVISION_CONFLICT',
                '다른 화면에서 평가가 바뀌었어요. 최신 평가를 확인해 주세요.', 409,
                value=current_value, revision=revision)
        event_id = None
        if value != current_value:
            if state is None:
                state = FeedbackState(playlist=source, target_kind=target_kind, track_id=track_id)
            previous_event_id = state.last_event_id
            revision += 1
            kind = ('TRACK_REACTION_CLEARED' if value is None else 'TRACK_REACTION_CHANGED') if target_kind == 'TRACK' else (
                'PLAYLIST_RATING_CLEARED' if value is None else 'PLAYLIST_RATING_CHANGED')
            track_snapshot = next((item for item in source.snapshot['items'] if item['track_id'] == track_id), None)
            event_id = event(kind, source.family, request_id,
                             {'source_playlist_id': source.pk, 'target_kind': target_kind,
                              'track_id': track_id or None, 'target_revision': revision,
                              'previous_value': current_value, 'new_value': value,
                              'related_feedback_event_id': previous_event_id if value is None else None,
                              'context_snapshot': source.snapshot['context'], 'track_snapshot': track_snapshot})
            state.value = value
            state.revision = revision
            state.last_event_id = event_id
            state.save()
        return {'source_playlist_id': source.pk, 'target_kind': target_kind, 'track_id': track_id or None,
                'value': value, 'revision': revision,
                'updated_at': state.updated_at.isoformat() if state else None, 'event_id': event_id}, 200

    scope = f'feedback:{playlist_id}:{target_kind}:{track_id}'
    return mutate(owner, scope, key, body, op)
