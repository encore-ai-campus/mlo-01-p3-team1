"""Explicit shared-registry write probe; all probe rows roll back atomically."""
import json,os,sys,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','backend.cafe.settings')
import django
django.setup()
from django.conf import settings
from django.db import connection,transaction
from backend.recommendation import youtube_registry as registry
from backend.recommendation.models import YoutubeTrackRevision,YoutubeMapping
from backend.recommendation.youtube_playback import resolve_playback_candidates
from backend.recommendation.youtube_queue_api import native_queue

if settings.LOCAL_DEMO or settings.YOUTUBE_REGISTRY_BACKEND!='database' or connection.vendor!='postgresql':
    raise RuntimeError('real_shared_postgresql_required')
track={'track_id':'deployment-probe-'+str(uuid.uuid4()),'track_name':'deployment probe','artists_name':'operator','duration_ms':240000}
with transaction.atomic():
    registry.register_mappings([{'track_id':track['track_id'],'video_url':'probeVideo1','expected_revision':0}])
    registry.verify_native_mapping(track,'probeVideo1',1,True,True,240)
    assert native_queue('probe',[track])['ready_count']==1
    assert resolve_playback_candidates(track)['status']=='MAPPING_REQUIRED'
    registry.verify_mapping(track,'probeVideo1',2,True,True,240)
    assert resolve_playback_candidates(track)['status']=='READY'
    registry.block_mapping(track['track_id'],'probeVideo1',3,'deployment transaction probe')
    assert native_queue('probe',[track])['ready_count']==1
    assert resolve_playback_candidates(track)['status']=='MAPPING_REQUIRED'
    transaction.set_rollback(True)
assert not YoutubeTrackRevision.objects.filter(pk=track['track_id']).exists()
print(json.dumps({'shared_postgresql_registry':'PASS','revision_and_independent_approvals':'PASS','probe_rows_persisted':False}))
