"""Owned native YouTube temporary queues; no account writes or search calls."""
from urllib.parse import urlencode

from django.conf import settings
from rest_framework.response import Response

from .api import Endpoint
from . import service, youtube_registry
from .errors import require
from .models import Playlist


def native_queue(playlist_id, tracks):
    ready, missing, used, track_links = [], [], set(), []
    registry = youtube_registry.track_registries(track['track_id'] for track in tracks)
    for track in tracks:
        record = registry[track['track_id']]
        mappings = record['mappings']
        # Public navigation exposes IDs/readiness only, never operator notes or audit identity.
        visible = [item for item in mappings
                   if isinstance(item.get('video_id'), str) and youtube_registry.VIDEO_ID.fullmatch(item['video_id'])
                   and (item.get('native_verified') or (item.get('status') != 'BLOCKED'
                        and item.get('native_source') != 'OPERATOR_NATIVE_BLOCK'))]
        visible.sort(key=lambda item: not item.get('native_verified', False))
        track_links.append({'track_id': track['track_id'], 'revision': record['revision'],
                            'candidates': [{'video_id': item['video_id'], 'native_verified': bool(item.get('native_verified'))}
                                           for item in visible[:10]]})
        candidates = visible
        candidate=next((item for item in candidates if item['video_id'] not in used),None)
        if candidate is None:
            missing.append({'track_id':track['track_id'],'track_name':track['track_name'],
                            'reason':'DUPLICATE_VIDEO' if candidates else 'MAPPING_REQUIRED'})
            continue
        used.add(candidate['video_id'])
        ready.append({'track_id':track['track_id'],'video_id':candidate['video_id'],
                      'source':(candidate.get('native_source') or 'OPERATOR_NATIVE_REVIEW') if candidate.get('native_verified') else 'COLLECTED_UNREVIEWED',
                      'native_verified':bool(candidate.get('native_verified'))})
    url=('https://www.youtube.com/watch_videos?'+urlencode({'video_ids':','.join(item['video_id'] for item in ready)},safe=',')
         if ready else None)
    return {'playlist_id':playlist_id,'tracks':ready,'missing':missing,'total_count':len(tracks),
            'ready_count':len(ready),'unreviewed_count':sum(not item['native_verified'] for item in ready),'is_complete':bool(tracks) and not missing,'url':url,
            'queue_kind':'TEMPORARY_NATIVE_QUEUE','account_saved':False,'track_links':track_links}


class YoutubeQueue(Endpoint):
    def get(self,request,pk):
        owner=self.owner(request)
        playlist=service.owned(Playlist,owner,pk)
        require(settings.LOCAL_DEMO or getattr(settings,'YOUTUBE_REGISTRY_BACKEND','disabled')=='database','POLICY_NOT_READY','공유 영상 연결 저장소의 운영 연결을 기다리고 있어요.',503)
        require(set(playlist.snapshot['context']['excluded_track_ids'])==set(playlist.family.excluded),
                'EXCLUSIONS_NOT_APPLIED','제외 변경을 반영한 선곡표를 먼저 받아 주세요.',409)
        return Response(native_queue(playlist.pk,playlist.snapshot['items']))
