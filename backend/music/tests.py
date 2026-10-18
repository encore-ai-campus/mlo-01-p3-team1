import csv
import hashlib
import io
import tempfile
from pathlib import Path
from unittest.mock import patch
from django.test import TestCase, TransactionTestCase, override_settings
from django.core.management import call_command, CommandError
from django.db import IntegrityError, transaction
from backend.recommendation.models import Catalog
from backend.recommendation.errors import DomainError
from .models import Album,Track,Tag,TrackTag,MusicImportRun
from .catalog import export_tracks,publish
from pipeline.music.normalize import convert, RAW_FIELDS, RAW_SCHEMA


class CatalogTests(TestCase):
    def setUp(self):
        self.album=Album.objects.create(album_name='같은 앨범명',album_id=None)
        self.track=Track.objects.create(track_id='one',track_name='곡',artists_name='A',album=self.album,
            duration_ms=240000,explicit=False,energy=4,acousticness=60,mode=True,speed='medium',
            instrumental=True,instrumental_review_value=False,play_url='https://open.spotify.com/track/one')
        for kind,code,active,status in [('genre','jazz',True,'approved'),('genre','j-rock',True,'approved'),
            ('mood','CALM',True,'approved'),('mood','DREAMY',True,'draft'),('instrument','piano',False,'approved')]:
            tag=Tag.objects.create(tag_type=kind,tag_code=code,tag_name=code,is_active=active)
            TrackTag.objects.create(track=self.track,tag=tag,review_status=status)
    def test_one_row_approved_tags_and_false_review_priority(self):
        rows=list(export_tracks());self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['genre_group_codes'],['J-POP','JAZZ','ROCK'])
        self.assertEqual(rows[0]['theme_codes'],['CALM']);self.assertIsNone(rows[0]['main_inst'])
        self.assertFalse(rows[0]['instrumental'])
    def test_composite_pk_and_separate_missing_album_ids(self):
        self.assertIsInstance(TrackTag.objects.first().pk,tuple)
        Album.objects.create(album_name='같은 앨범명')
        self.assertEqual(Album.objects.count(),2)
        link=TrackTag.objects.first()
        with self.assertRaises(IntegrityError),transaction.atomic():
            TrackTag.objects.create(track_id=link.track_id,tag_id=link.tag_id,review_status='approved')
    def test_publish_is_immutable_and_failed_version_does_not_replace(self):
        obj=publish('v1','immutable:source','a'*64,True)
        original=obj.tracks
        self.assertEqual(len(original[0]['score_cache']['weather']),5)
        self.assertEqual(len(original[0]['score_cache']['theme']),9)
        self.assertEqual(original[0]['theme_codes'],['CALM'])
        self.track.track_name='새 이름';self.track.save()
        with self.assertRaises(DomainError):publish('v1','immutable:source','a'*64,True)
        obj.refresh_from_db();self.assertEqual(obj.tracks,original)
        self.assertEqual(Catalog.objects.filter(ready=True).count(),1)
    @override_settings(LOCAL_DEMO=True)
    def test_import_rechecks_review_cleared_after_conversion(self):
        self.track.instrumental=False;self.track.save()
        raw={name:'' for name in RAW_FIELDS}
        raw.update(track_id='one',track_name='곡',artists='A',album_name='앨범',duration_ms='240000',
                   explicit='False',energy='.4',acousticness='.6',mode='1',tempo='90',time_signature='4',
                   instrumentalness='.9',track_genre='jazz')
        def concurrent_clear(*args,**kwargs):
            result=convert(*args,**kwargs)
            Track.objects.filter(pk='one').update(instrumental_review_value=None)
            return result
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as folder:
            source=Path(folder)/'source.csv'
            with source.open('w',newline='',encoding='utf8') as stream:
                writer=csv.DictWriter(stream,fieldnames=sorted(RAW_FIELDS));writer.writeheader();writer.writerow(raw)
            with patch('backend.music.management.commands.stage_music.convert',side_effect=concurrent_clear):
                call_command('stage_music',str(source),schema=RAW_SCHEMA,report=str(Path(folder)/'report.json'),load_local_demo=True,verbosity=0)
        self.track.refresh_from_db()
        self.assertIsNone(self.track.instrumental_review_value)
        self.assertTrue(self.track.instrumental)


class ResumableImportTests(TransactionTestCase):
    def test_quarantined_rows_need_explicit_acknowledgement(self):
        row={name:'' for name in RAW_FIELDS}
        row.update(track_id='invalid',artists='A',album_name='앨범',duration_ms='240000',
            explicit='False',energy='.4',acousticness='.6',valence='.5',mode='1',
            tempo='90',time_signature='4',instrumentalness='.9',track_genre='jazz')
        stream=io.StringIO(newline='')
        writer=csv.DictWriter(stream,fieldnames=sorted(RAW_FIELDS));writer.writeheader();writer.writerow(row)
        raw=stream.getvalue().encode()
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as folder:
            path=Path(folder)/'source.csv';path.write_bytes(raw)
            with override_settings(LOCAL_DEMO=True,MUSIC_RAW_DIRECTORY=str(Path(folder)/'archive')):
                with self.assertRaises(CommandError):
                    call_command('import_music_catalog_source',str(path),schema=RAW_SCHEMA,
                        expected_sha256=hashlib.sha256(raw).hexdigest(),apply=True,stdout=io.StringIO())
            self.assertEqual(MusicImportRun.objects.count(),0)

    def test_batches_resume_without_approving_or_publishing(self):
        rows=[]
        for identifier in ('a','b','c'):
            row={name:'' for name in RAW_FIELDS}
            row.update(track_id=identifier,track_name='곡 '+identifier,artists='A',album_name='앨범',
                duration_ms='240000',explicit='False',energy='.4',acousticness='.6',valence='.5',
                mode='1',tempo='90',time_signature='4',instrumentalness='.9',track_genre='jazz')
            rows.append(row)
        stream=io.StringIO(newline='')
        writer=csv.DictWriter(stream,fieldnames=sorted(RAW_FIELDS));writer.writeheader();writer.writerows(rows)
        raw=stream.getvalue().encode();digest=hashlib.sha256(raw).hexdigest()
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as folder:
            path=Path(folder)/'source.csv';path.write_bytes(raw)
            archive=Path(folder)/'archive'
            kwargs={'schema':RAW_SCHEMA,'expected_sha256':digest,'batch_size':2}
            with override_settings(LOCAL_DEMO=True,MUSIC_RAW_DIRECTORY=str(archive)):
                call_command('import_music_catalog_source',str(path),stdout=io.StringIO(),**kwargs)
                self.assertEqual(Track.objects.count(),0)
                from backend.music.management.commands.import_music_catalog_source import apply_track
                seen=0
                def interrupt(*args,**inner):
                    nonlocal seen
                    seen+=1
                    if seen==3:raise RuntimeError('simulated interruption')
                    return apply_track(*args,**inner)
                with patch('backend.music.management.commands.import_music_catalog_source.apply_track',side_effect=interrupt):
                    with self.assertRaises(RuntimeError):
                        call_command('import_music_catalog_source',str(path),apply=True,stdout=io.StringIO(),**kwargs)
                self.assertEqual(Track.objects.count(),2)
                self.assertEqual(MusicImportRun.objects.get(pk=digest).processed_count,2)
                call_command('import_music_catalog_source',str(path),apply=True,stdout=io.StringIO(),**kwargs)
                self.assertEqual(Track.objects.count(),3)
                self.assertTrue(MusicImportRun.objects.get(pk=digest).completed)
                self.assertEqual(Catalog.objects.count(),0)
                self.assertEqual(set(Track.objects.values_list('review__status',flat=True)),{'draft'})
                call_command('import_music_catalog_source',str(path),apply=True,stdout=io.StringIO(),**kwargs)
                self.assertEqual(Track.objects.count(),3)
