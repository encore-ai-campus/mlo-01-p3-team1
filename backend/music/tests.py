import csv
import tempfile
from pathlib import Path
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.core.management import call_command
from django.db import IntegrityError, transaction
from backend.recommendation.models import Catalog
from backend.recommendation.errors import DomainError
from .models import Album,Track,Tag,TrackTag
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
