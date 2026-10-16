import hashlib
import json
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from backend.recommendation.models import Catalog
from pipeline.music.normalize import normalize, RAW_SCHEMA


class Command(BaseCommand):
    help = 'Create synthetic test catalog only. Does not import or certify real music.'
    def handle(self,*args,**options):
        if not settings.LOCAL_DEMO: raise CommandError('C_LOCAL_DEMO=1 required')
        tracks=[]
        for i in range(64):
            row=normalize({'track_id':f'demo-{i:03}','track_name':f'테스트 곡 {i+1:02}',
                'artists':'검증용 연주자','album_name':'고정 검증 카탈로그','duration_ms':'240000',
                'explicit':'False','energy':'.6','mode':'1','acousticness':'.5','valence':'.7','tempo':'90',
                'time_signature':'4','instrumentalness':'.9','track_genre':'jazz'},RAW_SCHEMA)
            tracks.append({**row,'genre_group_codes':['JAZZ'],'theme_codes':['CALM','DREAMY'],
                           'mood':'잔잔한;몽환적인','cover_image_url':None})
        digest=hashlib.sha256(json.dumps(tracks,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        obj,created=Catalog.objects.get_or_create(version='c-demo-v2',defaults={'tracks':tracks,'sha256':digest,
            'source_ref':'synthetic:c-demo-v2','source_sha256':digest,'is_test':True,'ready':True})
        if not created and obj.sha256 != digest: raise CommandError('Existing demo version differs; use a new version')
        self.stdout.write('Synthetic catalog c-demo-v2 ready (64 tracks; is_test=true)')
