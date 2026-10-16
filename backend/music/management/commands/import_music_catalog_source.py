"""Resumable operator import for large CSVs. Review and READY publication stay separate."""
import bisect
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from backend.common.models import MusicSource, Review, TrackOrigin
from backend.common.music_archive import store as archive_source
from backend.recommendation.policy import groups
from pipeline.music.normalize import FIELDS, RAW_SCHEMA, RESULT_SCHEMA, convert, normalize
from backend.music.models import Album, MusicImportRun, Tag, Track, TrackTag


def source_hash(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def stored_source(path, digest):
    directory=Path(settings.MUSIC_RAW_DIRECTORY)
    if not settings.MUSIC_RAW_DIRECTORY or not directory.is_absolute():
        raise CommandError('MUSIC_RAW_DIRECTORY must be an absolute directory')
    directory.mkdir(parents=True, exist_ok=True)
    target=directory/(digest+'.csv')
    if target.exists():
        if source_hash(target)!=digest:raise CommandError('stored source hash mismatch')
        return target
    with tempfile.NamedTemporaryFile(dir=directory,delete=False) as temporary:
        temporary_path=Path(temporary.name)
    try:
        with path.open('rb') as original, temporary_path.open('wb') as copied:
            shutil.copyfileobj(original,copied)
        if source_hash(temporary_path)!=digest:raise CommandError('copied source hash mismatch')
        temporary_path.replace(target)
    finally:
        temporary_path.unlink(missing_ok=True)
    return target


def existing_values():
    return {track.pk:{'instrumental_review_value':track.instrumental_review_value,
        'instrumental':track.instrumental,'artists_id':track.artists_id,
        'album_id':track.album.album_id,'album_release_date':track.album.album_release_date,
        **{name:getattr(track,name) for name in ('raw_energy','raw_acousticness','raw_valence')}}
        for track in Track.objects.select_related('album').iterator(chunk_size=1000)}


def apply_track(row, original, schema, source):
    previous=Track.objects.select_for_update().filter(pk=row['track_id']).first()
    if previous:
        album=previous.album
    elif row['album_id']:
        album,_=Album.objects.get_or_create(album_id=row['album_id'],
            defaults={name:row[name] for name in ('album_name','album_release_date')})
    else:
        album=Album.objects.create(album_name=row['album_name'],album_release_date=row['album_release_date'])
    fields={name:row[name] for name in FIELDS if name not in
        ('track_id','album_id','album_name','album_release_date','genre','mood','main_inst')}
    fields.update({name:row[name] for name in ('raw_energy','raw_acousticness','raw_valence')})
    if previous:
        fields['instrumental']=normalize(original,schema,{
            'instrumental_review_value':previous.instrumental_review_value,
            'instrumental':previous.instrumental})['instrumental']
    track,_=Track.objects.update_or_create(pk=row['track_id'],defaults={**fields,'album':album})
    review,_=Review.objects.get_or_create(track=track)
    prior_origin=TrackOrigin.objects.filter(track=track).first()
    if prior_origin is None or prior_origin.source_id!=source.pk:
        review.status='draft';review.revision+=1;review.save(update_fields=['status','revision','updated_at'])
        TrackTag.objects.filter(track=track,tag__tag_type='genre').update(review_status='draft')
    TrackOrigin.objects.update_or_create(track=track,defaults={'source':source})
    for genre in (row['genre'] or '').split(';'):
        if not genre:continue
        tag,_=Tag.objects.get_or_create(tag_type='genre',tag_code=genre,
            defaults={'tag_name':genre,'is_active':bool(groups([genre]))})
        TrackTag.objects.update_or_create(track=track,tag=tag,defaults={'review_status':'approved'})


class Command(BaseCommand):
    help='Check or batch-import a source CSV. --apply requires prepared DB and source archive; never approves or publishes.'

    def add_arguments(self, parser):
        parser.add_argument('source')
        parser.add_argument('--schema',choices=(RAW_SCHEMA,RESULT_SCHEMA),required=True)
        parser.add_argument('--expected-sha256',required=True)
        parser.add_argument('--batch-size',type=int,default=500)
        parser.add_argument('--allow-quarantined-rows',action='store_true')
        parser.add_argument('--apply',action='store_true')

    def handle(self,*args,**options):
        path=Path(options['source']).resolve()
        if not path.is_file():raise CommandError('CSV source not found')
        digest=source_hash(path)
        if digest!=options['expected_sha256']:raise CommandError('CSV SHA-256 differs from expected source')
        if not 1<=options['batch_size']<=2000:raise CommandError('batch size must be 1..2000')
        schema=options['schema']
        result=convert(path,schema,existing_values())
        rows=sorted(result['tracks'],key=lambda row:row['track_id'])
        ids=[row['track_id'] for row in rows]
        summary={'source_sha256':digest,'source_schema_version':schema,'normalized_tracks':len(rows),
                 'errors':len(result['errors']),'conflicts':len(result['conflicting_track_ids']),
                 'error_lines':[error['line'] for error in result['errors'][:100]],
                 'error_lines_truncated':len(result['errors'])>100,
                 'ready_published':False}
        if not options['apply']:
            self.stdout.write(json.dumps({**summary,'applied':False},sort_keys=True))
            return
        if (result['errors'] or result['conflicting_track_ids']) and not options['allow_quarantined_rows']:
            raise CommandError('CSV contains quarantined rows; inspect dry-run and pass --allow-quarantined-rows explicitly')
        target=stored_source(path,digest)
        archive=archive_source(target,digest)
        with transaction.atomic():
            source,created=MusicSource.objects.get_or_create(sha256=digest,defaults={
                'schema':schema,'raw_path':str(target),'archive':archive})
            if not created:
                if source.schema!=schema:raise CommandError('registered source schema differs')
                source.raw_path=str(target)
                if source.archive.get('mode')!='S3' and archive.get('mode')=='S3':source.archive=archive
                source.save(update_fields=['raw_path','archive'])
            run,created=MusicImportRun.objects.get_or_create(source_sha256=digest,defaults={
                'source_schema_version':schema,'total_count':len(rows),'error_count':len(result['errors'])})
            if not created and (run.source_schema_version!=schema or run.total_count!=len(rows)):
                raise CommandError('checkpoint source schema/count differs')
        while True:
            with transaction.atomic():
                run=MusicImportRun.objects.select_for_update().get(pk=digest)
                if run.completed:break
                start=bisect.bisect_right(ids,run.last_track_id) if run.last_track_id is not None else 0
                chunk=rows[start:start+options['batch_size']]
                if not chunk:
                    run.completed=True;run.save(update_fields=['completed','updated_at'])
                    break
                for row in chunk:
                    original=result['source_rows'][row['track_id']][0]['raw']
                    apply_track(row,original,schema,source)
                run.processed_count=start+len(chunk)
                run.last_track_id=chunk[-1]['track_id']
                run.completed=run.processed_count==len(rows)
                run.save(update_fields=['processed_count','last_track_id','completed','updated_at'])
        self.stdout.write(json.dumps({**summary,'applied':True,'processed_count':run.processed_count,
                                      'completed':run.completed,'source_ref':'music-source:'+digest},sort_keys=True))
