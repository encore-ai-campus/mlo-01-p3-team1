import json
import hashlib
from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from backend.recommendation.errors import require
from .models import FeedbackEvent, Outbox, StreamRecord, Projection, ProjectedState, EventSnapshot, uid


def record(kind, payload):
    require(transaction.get_connection().in_atomic_block, 'EVENT_TRANSACTION_REQUIRED', '이벤트는 업무 상태와 함께 저장해야 합니다.', 503)
    required = ['event_id', 'owner_id', 'family_id', 'request_id']
    require(all(isinstance(payload.get(k), str) and payload[k] for k in required))
    if kind.startswith('TRACK_') or kind.startswith('PLAYLIST_RATING') or kind == 'PLAYLIST_APPROVED':
        require(bool(payload.get('context_snapshot')), 'SNAPSHOT_REQUIRED', '당시 조건이 필요합니다.', 503)
    if kind.startswith('TRACK_'):
        require(bool(payload.get('track_snapshot')), 'SNAPSHOT_REQUIRED', '당시 곡 정보가 필요합니다.', 503)
    # JSON round trip rejects accidental model/date objects before committing business state.
    data = json.loads(json.dumps(payload, allow_nan=False))
    at = timezone.now()
    event = FeedbackEvent.objects.create(event_id=data['event_id'], event_type=kind,
        owner_id=data['owner_id'], family_id=data['family_id'], source_playlist_id=data.get('source_playlist_id'),
        track_id=data.get('track_id'), payload=data, occurred_at=at, is_test=data.get('is_test') is True)
    envelope = {**data, 'event_type':kind, 'occurred_at':at.isoformat().replace('+00:00','Z'),
                'contract_version':settings.FEEDBACK_ENVELOPE_VERSION}
    if kind.startswith('TRACK_REACTION') or kind.startswith('PLAYLIST_RATING'):
        def snapshot(kind,value):
            digest=hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()
            identifier=f'{kind}:{digest}'
            saved,_=EventSnapshot.objects.get_or_create(pk=identifier,defaults={'kind':kind,'data':value})
            require(saved.data==value,'SNAPSHOT_CONFLICT','불변 스냅샷을 확인해 주세요.',409)
            return identifier
        envelope={k:envelope[k] for k in ('event_id','event_type','contract_version','request_id',
            'owner_id','family_id','source_playlist_id','target_revision','previous_value','new_value',
            'related_feedback_event_id','occurred_at','is_test')}
        reaction=kind.startswith('TRACK_REACTION')
        envelope['target_kind']='TRACK_REACTION' if reaction else 'PLAYLIST_RATING'
        envelope['context_id']=snapshot('context',data['context_snapshot'])
        if reaction:
            envelope['track_id']=data['track_id']
            envelope['track_snapshot_ref']=snapshot('track',data['track_snapshot'])
    Outbox.objects.create(event=event, envelope=envelope)


def relay_once(publish):
    now = timezone.now()
    with transaction.atomic():
        row = (Outbox.objects.select_for_update(skip_locked=not settings.LOCAL_DEMO)
               .filter(Q(state='PENDING')|Q(state='SENDING', lease_until__lt=now)).order_by('event__occurred_at').first())
        if row is None:
            return False
        row.state='SENDING'; row.lease_token=uid(); row.lease_until=now+timedelta(seconds=30)
        row.attempts+=1; row.save()
        token, event_id, envelope = row.lease_token, row.pk, row.envelope
    try:
        publish(event_id, envelope)
    except Exception as error:
        Outbox.objects.filter(pk=event_id, lease_token=token).update(state='PENDING', last_error=type(error).__name__[:100])
        raise RuntimeError('outbox_publish_failed') from None
    Outbox.objects.filter(pk=event_id, lease_token=token).update(state='SENT', published_at=timezone.now(),
                                                              lease_until=None, last_error='')
    return True


def ingest(envelope, stream_key):
    """At-least-once delivery: preserve offsets/raw payload; project an event once."""
    require(envelope.get('contract_version') == settings.FEEDBACK_ENVELOPE_VERSION,
            'CONTRACT_VERSION_MISMATCH', '이벤트 계약 버전이 다릅니다.', 409)
    with transaction.atomic():
        raw, created = StreamRecord.objects.get_or_create(stream_key=stream_key,
            defaults={'event_id':envelope['event_id'], 'envelope':envelope})
        require(raw.envelope == envelope, 'STREAM_OFFSET_CONFLICT', '같은 offset에 다른 이벤트가 있습니다.', 409)
        event = FeedbackEvent.objects.select_for_update().filter(pk=envelope['event_id']).first()
        require(event is not None, 'EVENT_NOT_FOUND', '업무 원본이 없습니다.', 409)
        stored = Outbox.objects.get(pk=event.pk).envelope
        require(stored == envelope, 'EVENT_CONFLICT', '업무 원본과 수신 내용이 다릅니다.', 409)
        _, projected = Projection.objects.get_or_create(event=event)
        if projected:
            payload=event.payload
            rating=event.event_type.startswith('PLAYLIST_RATING')
            reaction=event.event_type.startswith('TRACK_REACTION')
            excluded=event.event_type in ('TRACK_EXCLUDED','TRACK_EXCLUSION_CANCELLED')
            if rating or reaction or excluded:
                kind='exclusion' if excluded else 'rating' if rating else 'reaction'
                target=event.family_id if excluded else event.source_playlist_id
                target_key=f'{kind}:{target}:{event.track_id or ""}'
                revision=payload.get('revision') if excluded else payload.get('target_revision')
                require(type(revision) is int and revision>0)
                state=ProjectedState.objects.select_for_update().filter(pk=target_key).first()
                value=(event.event_type=='TRACK_EXCLUDED') if excluded else payload.get('new_value')
                if state is None or revision>state.revision:
                    ProjectedState.objects.update_or_create(target_key=target_key,defaults={
                        'revision':revision,'value':value,'event':event,'is_test':event.is_test})
        return {'raw_created':created, 'projected':projected}
