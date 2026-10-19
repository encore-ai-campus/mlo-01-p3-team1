from django.test import TestCase, override_settings

from backend.common.models import MusicSource, Review, TrackOrigin
from backend.music.catalog import export_tracks, publish
from backend.music.models import Album, Track, Tag, TrackTag
from backend.recommendation.catalog_storage import unpack
from backend.recommendation.errors import DomainError
from backend.recommendation.inputs import DEFAULTS
from backend.recommendation.models import Catalog, Job, Playlist
from backend.recommendation.policy import eligible
from backend.recommendation.worker import run_one


@override_settings(LOCAL_DEMO=False, INTEGRATION_ENABLED=True, GUEST_TTL_SECONDS=600,
                   OWNER_RESOLVER='backend.common.identity.owner', EVENT_SINK='backend.common.events.record',
                   WEATHER_PROVIDER='', SEARCH_SECONDS=20, SEARCH_MAX_CANDIDATES=96)
class OccasionPublicationTests(TestCase):
    def setUp(self):
        self.source=MusicSource.objects.create(sha256='a'*64,schema='spotify-raw20-v1',raw_path='fixture-only')
        self.album=Album.objects.create(album_name='Fixture album')
        self.tag=Tag.objects.create(tag_type='genre',tag_code='jazz',tag_name='Jazz',is_active=True)
        for index,name in enumerate(('Normal A','Normal B','Normal C','Christmas music','Silent Night')):
            track=Track.objects.create(track_id=f'track-{index}',track_name=name,artists_name='Fixture Artist',
                album=self.album,duration_ms=3600000,explicit=False,energy=4,mode=True,acousticness=60,
                raw_energy='.4',raw_acousticness='.6',raw_valence='.5',speed='medium',instrumental=True,
                play_url=f'https://open.spotify.com/track/track-{index}')
            TrackTag.objects.create(track=track,tag=self.tag,review_status='approved')
            Review.objects.create(track=track,status='approved')
            TrackOrigin.objects.create(track=track,source=self.source)

    def test_operating_publication_and_worker_use_general_only(self):
        rows=list(export_tracks(approved_only=True,source_sha256=self.source.pk))
        self.assertEqual([r['occasion_status'] for r in rows],['GENERAL']*3+['SEASONAL_EVENT','REVIEW_REQUIRED'])
        catalog=publish('screened','music-source:'+self.source.pk,self.source.pk)
        saved=unpack(catalog.tracks)
        self.assertEqual(len(saved),3)
        self.assertTrue(all(row['occasion_decision_version'] and row['occasion_policy_version'] for row in saved))
        response=self.client.post('/api/recommendation-jobs',{},content_type='application/json',HTTP_IDEMPOTENCY_KEY='general')
        self.assertEqual(response.status_code,202,response.content)
        self.assertTrue(run_one())
        job=Job.objects.get(pk=response.json()['job_id'])
        self.assertEqual(job.status,'SUCCEEDED',job.error)
        result=Playlist.objects.get(job=job).snapshot
        self.assertEqual({row['track_id'] for row in result['items']},{'track-0','track-1','track-2'})
        self.assertTrue(all(row['occasion_status']=='GENERAL' for row in result['items']))

    def test_missing_or_non_general_decision_is_not_eligible_in_either_mode(self):
        row=list(export_tracks())[0]
        for mode in ('ON','OFF'):
            for status in ('SEASONAL_EVENT','REVIEW_REQUIRED','UNSCREENED',None):
                self.assertFalse(eligible({**row,'occasion_status':status},
                    {**DEFAULTS,'weather_influence_mode':mode},['JAZZ'],['medium'],[]))
            for field in ('occasion_policy_version','occasion_decision_version','decision_source'):
                self.assertFalse(eligible({**row,field:None},
                    {**DEFAULTS,'weather_influence_mode':mode},['JAZZ'],['medium'],[]))
            self.assertFalse(eligible({**row,'decision_source':['RULE_SCREEN']},
                {**DEFAULTS,'weather_influence_mode':mode},['JAZZ'],['medium'],[]))

    def test_no_general_source_cannot_publish_or_mutate_old_snapshots(self):
        first=publish('original','music-source:'+self.source.pk,self.source.pk)
        original=first.sha256
        Track.objects.all().update(track_name='Christmas music')
        with self.assertRaises(DomainError):publish('blocked','music-source:'+self.source.pk,self.source.pk)
        self.assertFalse(Catalog.objects.filter(pk='blocked').exists())
        first.refresh_from_db();self.assertEqual(first.sha256,original)
