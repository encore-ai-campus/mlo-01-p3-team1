import hashlib
import json
import tempfile
from pathlib import Path
from django.conf import settings
from django.db import transaction
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.response import Response
from backend.recommendation.api import Endpoint
from backend.recommendation.errors import require
from backend.recommendation.inputs import shape, strict_int, strings
from backend.music.models import Track, Album, Tag, TrackTag
from backend.music.catalog import publish
from backend.recommendation.policy import THEMES, groups
from backend.recommendation.models import Catalog
from pipeline.music.normalize import convert, RAW_SCHEMA, RESULT_SCHEMA, FIELDS
from .identity import admin
from .models import AdminAction, Review, ReviewChange, MusicSource, TrackOrigin
from .music_archive import store as archive_source


def mutation(request, user, scope, body, operation):
    key=request.headers.get('Idempotency-Key','')
    require(bool(key.strip()) and len(key)<=200)
    digest=hashlib.sha256(json.dumps(body,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=user.pk)
        cached=AdminAction.objects.filter(actor=user,scope=scope,key=key).first()
        if cached:
            require(cached.fingerprint==digest,'IDEMPOTENCY_CONFLICT','같은 키의 요청 내용이 다릅니다.',409)
            return Response(cached.response,status=cached.status)
        data,status=operation()
        AdminAction.objects.create(actor=user,scope=scope,key=key,fingerprint=digest,response=data,status=status)
        return Response(data,status=status)


class Imports(Endpoint):
    def post(self, request):
        user=admin(request,'manage_music')
        require(set(request.data)<= {'file','source_schema_version','source_sha256'})
        upload=request.FILES.get('file'); schema=request.data.get('source_schema_version')
        require(schema in (RAW_SCHEMA,RESULT_SCHEMA) and upload is not None)
        require(settings.CSV_UPLOAD_MAX_BYTES>0,'POLICY_NOT_READY','음악 업로드 한도 설정이 필요합니다.',503)
        require(0<upload.size<=settings.CSV_UPLOAD_MAX_BYTES,'UPLOAD_TOO_LARGE','CSV 크기를 확인해 주세요.',422)
        raw=upload.read(settings.CSV_UPLOAD_MAX_BYTES+1)
        require(len(raw)<=settings.CSV_UPLOAD_MAX_BYTES)
        digest=hashlib.sha256(raw).hexdigest()
        require(request.data.get('source_sha256')==digest,'SOURCE_HASH_MISMATCH','업로드 파일 해시가 다릅니다.',422)
        require(bool(settings.MUSIC_RAW_DIRECTORY),'POLICY_NOT_READY','음악 원본 보관 경로가 필요합니다.',503)
        directory=Path(settings.MUSIC_RAW_DIRECTORY)
        require(directory.is_absolute(),'POLICY_NOT_READY','원본 보관 경로는 절대 경로여야 합니다.',503)
        directory.mkdir(parents=True,exist_ok=True)
        source_path=directory/(digest+'.csv')
        if source_path.exists():
            require(hashlib.sha256(source_path.read_bytes()).hexdigest()==digest,'SOURCE_CORRUPT','보관 원본의 무결성을 확인해 주세요.',503)
        else:
            with tempfile.NamedTemporaryFile(dir=directory,delete=False) as temporary:
                temporary.write(raw);temporary_name=temporary.name
            Path(temporary_name).replace(source_path)
        archive=archive_source(source_path,digest)
        def operation():
            source,_=MusicSource.objects.get_or_create(sha256=digest,defaults={'schema':schema,'raw_path':str(source_path),'archive':archive})
            if source.archive.get('mode')!='S3' and archive.get('mode')=='S3':
                source.archive=archive;source.save(update_fields=['archive'])
            existing={t.pk:{'instrumental_review_value':t.instrumental_review_value,
                'instrumental':t.instrumental,'artists_id':t.artists_id,'album_id':t.album.album_id,
                'album_release_date':t.album.album_release_date,
                **{k:getattr(t,k) for k in ('raw_energy','raw_acousticness','raw_valence')}}
                for t in Track.objects.select_related('album')}
            result=convert(source_path,schema,existing)
            for row in result['tracks']:
                previous=Track.objects.filter(pk=row['track_id']).first()
                if previous:
                    album=previous.album
                elif row['album_id']:
                    album,_=Album.objects.get_or_create(album_id=row['album_id'],defaults={k:row[k] for k in ['album_name','album_release_date']})
                else:
                    album=Album.objects.create(album_name=row['album_name'],album_release_date=row['album_release_date'])
                fields={k:row[k] for k in FIELDS if k not in ('track_id','album_id','album_name','album_release_date','genre','mood','main_inst')}
                fields.update({k:row[k] for k in ('raw_energy','raw_acousticness','raw_valence')})
                if previous and previous.instrumental_review_value is not None:
                    fields['instrumental']=previous.instrumental_review_value
                track,_=Track.objects.update_or_create(pk=row['track_id'],defaults={**fields,'album':album})
                review,_=Review.objects.get_or_create(track=track)
                prior_origin=TrackOrigin.objects.filter(track=track).first()
                if prior_origin is None or prior_origin.source_id!=source.pk:
                    review.status='draft';review.revision+=1;review.save()
                    TrackTag.objects.filter(track=track,tag__tag_type='genre').update(review_status='draft')
                TrackOrigin.objects.update_or_create(track=track,defaults={'source':source})
                for genre in (row.get('genre') or '').split(';'):
                    if not genre:continue
                    tag,_=Tag.objects.get_or_create(tag_type='genre',tag_code=genre,
                        defaults={'tag_name':genre,'is_active':bool(groups([genre]))})
                    TrackTag.objects.update_or_create(track=track,tag=tag,defaults={'review_status':'approved'})
            # Do not echo raw CSV cells: only line identifiers/codes for diagnostics.
            errors=[{k:v for k,v in e.items() if k in ('row_number','line','code','error','field')} if isinstance(e,dict) else {'code':'INVALID_ROW'} for e in result['errors']]
            return {'source_sha256':digest,'imported_count':len(result['tracks']),
                    'source_ref':'music-source:'+digest,
                    'errors':errors,'conflicting_track_ids':result['conflicting_track_ids'],'ready_published':False},200
        return mutation(request,user,'music-import',{'schema':schema,'sha256':digest},operation)


class Reviews(Endpoint):
    def get(self, request):
        admin(request,'manage_music')
        query=Track.objects.select_related('review').order_by('track_id')
        status=request.query_params.get('status')
        if status:
            require(status in ('draft','approved'))
            query=query.filter(review__status=status)
        after=request.query_params.get('cursor')
        if after:query=query.filter(track_id__gt=after)
        rows=list(query[:21]);items=[]
        for track in rows[:20]:
            review=Review.objects.filter(track=track).first()
            items.append({'track_id':track.pk,'track_name':track.track_name,'artists_name':track.artists_name,
                          'revision':review.revision if review else 0,'review_status':review.status if review else 'draft',
                          'instrumental_review_value':track.instrumental_review_value})
        return Response({'items':items,'next_cursor':rows[19].pk if len(rows)>20 else None,'as_of':timezone.now().isoformat().replace('+00:00','Z')})


class ReviewUpdate(Endpoint):
    def post(self,request,track_id):
        user=admin(request,'manage_music')
        body=shape(request.data,['expected_revision','review_status','reason','instrumental_review_value','mood_codes','instrument_codes'],
                   ['expected_revision','review_status','reason'])
        strict_int(body['expected_revision'])
        require(body['review_status'] in ('draft','approved') and type(body['reason']) is str and bool(body['reason'].strip()))
        if 'instrumental_review_value' in body:
            require(body['instrumental_review_value'] is None or type(body['instrumental_review_value']) is bool)
        for field in ('mood_codes','instrument_codes'):
            if field in body:body[field]=strings(body[field])
        require(set(body.get('mood_codes',[]))<=THEMES.keys())
        def operation():
            track=Track.objects.select_for_update().filter(pk=track_id).first()
            require(track is not None,'NOT_FOUND','곡을 찾을 수 없습니다.',404)
            review,_=Review.objects.get_or_create(track=track)
            require(review.revision==body['expected_revision'],'REVIEW_REVISION_CONFLICT','최신 검수 상태를 확인해 주세요.',409)
            if 'instrumental_review_value' in body:
                track.instrumental_review_value=body['instrumental_review_value'];track.save(update_fields=['instrumental_review_value'])
            for field,kind in [('mood_codes','mood'),('instrument_codes','instrument')]:
                if field not in body:continue
                TrackTag.objects.filter(track=track,tag__tag_type=kind).update(review_status='draft')
                for code in body[field]:
                    tag,_=Tag.objects.get_or_create(tag_type=kind,tag_code=code,defaults={'tag_name':THEMES.get(code,code),'is_active':True})
                    TrackTag.objects.update_or_create(track=track,tag=tag,defaults={'review_status':body['review_status']})
            review.revision+=1;review.status=body['review_status'];review.reason=body['reason'];review.save()
            ReviewChange.objects.create(track_id=track_id,actor=user,revision=review.revision,snapshot=body)
            return {'track_id':track_id,'revision':review.revision,'review_status':review.status},200
        return mutation(request,user,'music-review:'+track_id,body,operation)


class Readiness(Endpoint):
    def get(self,request):
        admin(request,'manage_music')
        from backend.music.catalog import export_tracks
        from backend.recommendation.policy import eligible,weather_fit,GENRES,SPEEDS,WEATHER_WEIGHTS
        from backend.recommendation.inputs import DEFAULTS
        registered_count=common_count=duration=0
        weather_counts={code:0 for code in WEATHER_WEIGHTS}
        options={**DEFAULTS,'weather_influence_mode':'OFF'}
        for track in export_tracks():
            registered_count+=1
            if not eligible(track,options,list(GENRES),list(SPEEDS),[]):continue
            common_count+=1;duration+=track['duration_ms']
            for code in weather_counts:weather_counts[code]+=weather_fit(track,code) is not None
        return Response({'registered_count':registered_count,'approved_review_count':Review.objects.filter(status='approved').count(),
                         'common_eligible_count':common_count,'duration_ms':duration,
                         'weather_counts':weather_counts,
                         'catalog_versions':list(Catalog.objects.order_by('-created_at').values('version','ready','is_test')[:10]),
                         'is_test':settings.LOCAL_DEMO,'as_of':timezone.now().isoformat().replace('+00:00','Z')})


class Publish(Endpoint):
    def post(self,request):
        user=admin(request,'manage_music')
        body=shape(request.data,['version','source_ref','source_sha256'],['version','source_ref','source_sha256'])
        require(all(type(v) is str and bool(v.strip()) for v in body.values()))
        require(len(body['source_sha256'])==64 and all(c in '0123456789abcdef' for c in body['source_sha256']))
        def operation():
            require(Review.objects.filter(status='approved').exists(),'REVIEW_PENDING','승인된 곡이 없습니다.',409)
            source=MusicSource.objects.filter(pk=body['source_sha256']).first()
            require(source is not None and body['source_ref']=='music-source:'+source.pk,'SOURCE_REQUIRED','등록된 불변 원본 참조가 필요합니다.',422)
            require(settings.LOCAL_DEMO or source.archive.get('mode')=='S3' or
                    (settings.MUSIC_S3_ARCHIVE_DEFERRED and source.archive.get('mode')=='S3_DEFERRED'),
                    'SOURCE_ARCHIVE_REQUIRED','운영 카탈로그는 원본 보관 상태를 확인해야 합니다.',503)
            require(Path(source.raw_path).is_file() and hashlib.sha256(Path(source.raw_path).read_bytes()).hexdigest()==source.pk,
                    'SOURCE_CORRUPT','보관 원본을 확인해 주세요.',503)
            catalog=publish(**body,is_test=settings.LOCAL_DEMO)
            return {'catalog_version':catalog.pk,'sha256':catalog.sha256,'ready':catalog.ready},201
        return mutation(request,user,'catalog-publish',body,operation)
