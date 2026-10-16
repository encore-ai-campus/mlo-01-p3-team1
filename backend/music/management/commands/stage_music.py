import json
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from pipeline.music.normalize import convert, normalize, FIELDS, RAW_SCHEMA, RESULT_SCHEMA
from backend.recommendation.policy import groups
from backend.music.models import Album, Track, Tag, TrackTag


class Command(BaseCommand):
    help = 'Convert CSV into a local staging report; optional local demo RDB load. Never publishes READY.'
    def add_arguments(self,parser):
        parser.add_argument('source');parser.add_argument('--schema',choices=[RAW_SCHEMA,RESULT_SCHEMA],required=True)
        parser.add_argument('--report',required=True);parser.add_argument('--load-local-demo',action='store_true')
    def handle(self,*args,**options):
        if not settings.LOCAL_DEMO: raise CommandError('Use B authorized import API for production writes')
        source=Path(options['source']);report=Path(options['report'])
        if source.resolve()==report.resolve(): raise CommandError('Source and report must differ')
        existing={}
        for track in Track.objects.all():
            existing[track.pk]={'instrumental_review_value':track.instrumental_review_value,'instrumental':track.instrumental,
                               'artists_id':track.artists_id,'album_id':track.album.album_id,'album_release_date':track.album.album_release_date,
                               **{key:getattr(track,key) for key in ('raw_energy','raw_acousticness','raw_valence')}}
        result=convert(source,options['schema'],existing)
        report.parent.mkdir(parents=True,exist_ok=True)
        report.write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
        if options['load_local_demo']:
            for row in result['tracks']:
                with transaction.atomic():
                    previous=Track.objects.select_for_update().filter(pk=row['track_id']).first()
                    if previous: album=previous.album
                    elif row['album_id']:
                        album,_=Album.objects.get_or_create(album_id=row['album_id'],defaults={k:row[k] for k in ['album_name','album_release_date']})
                    else: album=Album.objects.create(album_name=row['album_name'],album_release_date=row['album_release_date'])
                    fields={k:row[k] for k in FIELDS if k not in ['track_id','album_id','album_name','album_release_date','genre','mood','main_inst']}
                    fields.update({key:row[key] for key in ('raw_energy','raw_acousticness','raw_valence')})
                    if previous:
                        current={'instrumental_review_value':previous.instrumental_review_value,'instrumental':previous.instrumental}
                        raw=result['source_rows'][row['track_id']][0]['raw']
                        fields['instrumental']=normalize(raw,options['schema'],current)['instrumental']
                    track,_=Track.objects.update_or_create(track_id=row['track_id'],defaults={**fields,'album':album})
                    for genre in (row['genre'] or '').split(';'):
                        if not genre: continue
                        tag,_=Tag.objects.get_or_create(tag_type='genre',tag_code=genre,defaults={'tag_name':genre,'is_active':bool(groups([genre]))})
                        TrackTag.objects.get_or_create(track=track,tag=tag,defaults={'review_status':'approved'})
        self.stdout.write(json.dumps({'normalized_tracks':len(result['tracks']),'errors':len(result['errors']),
                                     'conflicts':len(result['conflicting_track_ids']),'ready_published':False}))
