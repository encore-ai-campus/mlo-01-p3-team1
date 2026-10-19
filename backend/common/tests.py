"""통합 호스트의 실제 HTTP/DB 경계. 외부 서비스는 호출하지 않습니다."""
import csv
import hashlib
import io
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from django.test import TestCase, SimpleTestCase, Client, override_settings
from datetime import datetime, timedelta
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from backend.recommendation.models import Job, Playlist, Catalog
from backend.recommendation.worker import run_one
from backend.recommendation.errors import DomainError
from pipeline.music.normalize import RAW_FIELDS, RAW_SCHEMA
from . import events
from .models import Guest, FeedbackState, FeedbackEvent, Outbox, Projection, ProjectedState, StreamRecord, Review, ReviewChange


@override_settings(INTEGRATION_ENABLED=True,LOCAL_DEMO=True,GUEST_TTL_SECONDS=600,
    ADMIN_SESSION_SECONDS=600,OWNER_RESOLVER='backend.common.identity.owner',
    EVENT_SINK='backend.common.events.record',WEATHER_PROVIDER='',
    SEARCH_SECONDS=20,SEARCH_MAX_CANDIDATES=96,ADS_INTERNAL_SECRET='test-internal')
class IntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_c_demo',verbosity=0)
        cls.user=get_user_model().objects.create_user('reviewer',password='A-complex-test-123',is_staff=True)
        cls.user.user_permissions.add(*Permission.objects.filter(content_type__app_label='common'))

    def post(self,path,body,key='test',client=None):
        return (client or self.client).post(path,body,content_type='application/json',HTTP_IDEMPOTENCY_KEY=key)

    def result(self):
        # Snapshot is assembled by the real worker rather than invented by this test.
        response=self.post('/api/recommendation-jobs',{'region_id':'demo-region','weather_influence_mode':'OFF'})
        self.assertEqual(response.status_code,202,response.content)
        self.assertTrue(run_one())
        return Playlist.objects.get(job_id=response.json()['job_id'])

    def test_cookie_is_opaque_hashed_and_expiry_changes_ownership(self):
        result=self.result()
        token=self.client.cookies['cafe_guest'].value
        guest=Guest.objects.get(pk=result.family.owner_id)
        self.assertNotEqual(token,guest.pk)
        self.assertEqual(guest.token_hash,hashlib.sha256(token.encode()).hexdigest())
        self.assertTrue(self.client.cookies['cafe_guest']['httponly'])
        self.assertEqual(Client().get(f'/api/playlists/{result.pk}').status_code,404)
        Guest.objects.filter(pk=guest.pk).update(expires_at=timezone.now())
        self.assertEqual(self.client.get(f'/api/playlists/{result.pk}').status_code,404)

    def test_worker_request_events_and_http_idempotency(self):
        result=self.result()
        repeated=self.post('/api/recommendation-jobs',{'region_id':'demo-region','weather_influence_mode':'OFF'})
        self.assertEqual(repeated.json()['job_id'],result.job_id)
        self.assertEqual(Job.objects.count(),1)
        self.assertEqual(set(FeedbackEvent.objects.values_list('event_type',flat=True)),
                         {'RECOMMENDATION_REQUESTED','PLAYLIST_GENERATED'})
        self.assertEqual(Outbox.objects.count(),2)
        self.assertEqual(repeated['X-Contract-Version'],'phase3-20261016.3')

    def test_feedback_cancel_retry_revision_and_projection_reordering(self):
        result=self.result();track=result.snapshot['items'][0]['track_id']
        path=f'/api/playlists/{result.pk}/tracks/{track}/reaction'
        def put(body,key):
            return self.client.put(path,body,content_type='application/json',HTTP_IDEMPOTENCY_KEY=key)
        body={'reaction':'LIKE','expected_revision':0}
        first=put(body,'like');self.assertEqual(first.status_code,200,first.content)
        self.assertEqual(put(body,'like').json(),first.json())
        self.assertEqual(put({'reaction':'DISLIKE','expected_revision':0},'stale').status_code,409)
        clear=put({'reaction':None,'expected_revision':1},'clear')
        self.assertEqual(clear.status_code,200,clear.content)
        event=FeedbackEvent.objects.get(pk=clear.json()['event_id'])
        self.assertEqual(event.payload['related_feedback_event_id'],first.json()['event_id'])
        self.assertEqual(event.payload['track_snapshot'],result.snapshot['items'][0])
        newer=Outbox.objects.get(pk=event.pk).envelope
        older=Outbox.objects.get(pk=first.json()['event_id']).envelope
        import jsonschema
        schema=json.loads((Path(__file__).resolve().parents[2]/'docs/contracts/3차_공통_API_이벤트.schema.json').read_text(encoding='utf8'))
        validator=jsonschema.Draft202012Validator({'$ref':'#/$defs/FeedbackEventEnvelope','$defs':schema['$defs']},format_checker=jsonschema.FormatChecker())
        validator.validate(newer);validator.validate(older)
        self.assertTrue(events.ingest(newer,'test:0:2')['projected'])
        self.assertTrue(events.ingest(older,'test:0:1')['projected'])
        self.assertFalse(events.ingest(newer,'test:0:2')['raw_created'])
        self.assertFalse(events.ingest(newer,'test:0:3')['projected'])
        state=ProjectedState.objects.get();self.assertIsNone(state.value);self.assertEqual(state.revision,2)
        self.assertEqual(Projection.objects.count(),2);self.assertEqual(StreamRecord.objects.count(),3)

    def test_event_failure_rolls_back_feedback(self):
        result=self.result()
        with patch('backend.common.events.record',side_effect=DomainError('TEST_FAILURE','시험 실패',503)):
            response=self.client.put(f'/api/playlists/{result.pk}/rating',{'rating':5,'expected_revision':0},
                content_type='application/json',HTTP_IDEMPOTENCY_KEY='failure')
        self.assertEqual(response.status_code,503,response.content)
        self.assertFalse(FeedbackState.objects.exists())
        self.assertEqual(FeedbackEvent.objects.count(),2)

    def test_rating_envelope_has_no_track_fields_and_matches_contract(self):
        result=self.result()
        response=self.client.put(f'/api/playlists/{result.pk}/rating',{'rating':5,'expected_revision':0},
            content_type='application/json',HTTP_IDEMPOTENCY_KEY='rating')
        self.assertEqual(response.status_code,200,response.content)
        envelope=Outbox.objects.get(pk=response.json()['event_id']).envelope
        import jsonschema
        schema=json.loads((Path(__file__).resolve().parents[2]/'docs/contracts/3차_공통_API_이벤트.schema.json').read_text(encoding='utf8'))
        jsonschema.Draft202012Validator({'$ref':'#/$defs/FeedbackEventEnvelope','$defs':schema['$defs']}).validate(envelope)
        self.assertNotIn('track_id',envelope)

    def test_outbox_retry_uses_same_event_and_envelope(self):
        self.result();seen=[]
        def fail(identifier,envelope):
            seen.append((identifier,envelope));raise TimeoutError('secret-not-for-log')
        with self.assertRaisesRegex(RuntimeError,'outbox_publish_failed'):events.relay_once(fail)
        row=Outbox.objects.get(pk=seen[0][0]);self.assertEqual(row.state,'PENDING')
        self.assertEqual(row.last_error,'TimeoutError')
        events.relay_once(lambda identifier,envelope:seen.append((identifier,envelope)))
        self.assertEqual(seen[0],seen[1]);row.refresh_from_db();self.assertEqual(row.state,'SENT')

    def test_stream_conflict_preserves_original(self):
        self.result();envelope=Outbox.objects.first().envelope
        events.ingest(envelope,'test:0:1')
        with self.assertRaises(DomainError):events.ingest({**envelope,'event_type':'tampered'},'test:0:1')
        self.assertEqual(StreamRecord.objects.get().envelope,envelope)

    def test_login_requires_csrf_and_permissions_are_checked_again(self):
        client=Client(enforce_csrf_checks=True)
        me=client.get('/api/auth/me')
        credentials={'username':'reviewer','password':'A-complex-test-123'}
        self.assertEqual(self.post('/api/auth/login',credentials,client=client).status_code,403)
        response=client.post('/api/auth/login',credentials,content_type='application/json',HTTP_X_CSRFTOKEN=me.json()['csrf_token'])
        self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(len(response.json()['allowed_menus']),4)
        self.assertEqual(client.get('/api/admin/music/reviews').status_code,200)
        get_user_model().objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertEqual(client.get('/api/admin/music/reviews').status_code,401)

    def test_internal_ads_guest_bootstrap_and_secret(self):
        path='/api/internal/ads-context'
        self.assertEqual(self.post(path,{'action':'admin'}).status_code,403)
        first=self.client.post(path,{'action':'guest','bootstrap':True},content_type='application/json',HTTP_AUTHORIZATION='Bearer test-internal')
        self.assertEqual(first.status_code,200,first.content)
        self.assertFalse(first.json()['measurement_available'])
        second=self.client.post(path,{'action':'guest'},content_type='application/json',HTTP_AUTHORIZATION='Bearer test-internal')
        self.assertTrue(second.json()['measurement_available'])
        self.assertEqual(first.json()['owner_guest_id'],second.json()['owner_guest_id'])

    def test_admin_password_reissue_revokes_old_session_and_preserves_roles(self):
        import os
        from django.contrib.sessions.models import Session
        self.client.force_login(self.user)
        before=set(self.user.user_permissions.values_list('pk',flat=True))
        with patch.dict(os.environ,{'BOOTSTRAP_ADMIN_PASSWORD':'Replacement-test-only-456!'}):
            call_command('bootstrap_admin','reviewer',reset_password=True,verbosity=0)
        self.assertFalse(Session.objects.exists())
        self.user.refresh_from_db();self.assertTrue(self.user.check_password('Replacement-test-only-456!'))
        self.assertEqual(before,set(self.user.user_permissions.values_list('pk',flat=True)))
        self.assertFalse(self.client.get('/api/auth/me').json()['authenticated'])

    def test_off_weather_refresh_is_noop_without_provider(self):
        result=self.result()
        with patch('backend.recommendation.service.obtain',side_effect=AssertionError('OFF must not read weather')):
            response=self.post(f'/api/playlists/{result.pk}/weather-refresh',{'exclusion_revision':0},'weather')
        self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(Job.objects.count(),1)

    def test_off_no_region_preserves_null_and_allows_approval_feedback_and_refresh(self):
        with patch('backend.recommendation.service.obtain',side_effect=AssertionError('OFF must not read weather')):
            accepted=self.post('/api/recommendation-jobs',{'weather_influence_mode':'OFF'},'no-region')
        self.assertEqual(accepted.status_code,202,accepted.content)
        self.assertTrue(run_one())
        result=Playlist.objects.get(job_id=accepted.json()['job_id'])
        self.assertIsNone(result.snapshot['context']['options']['region_id'])
        self.assertIsNone(result.snapshot['context']['weather'])
        duplicate=self.post('/api/recommendation-jobs',{'weather_influence_mode':'OFF','region_id':''},'no-region')
        self.assertEqual(accepted.json(),duplicate.json())
        rating=self.client.put(f'/api/playlists/{result.pk}/rating',{'rating':4,'expected_revision':0},
            content_type='application/json',HTTP_IDEMPOTENCY_KEY='rate-no-region')
        self.assertEqual(rating.status_code,200,rating.content)
        approval=self.post(f'/api/playlists/{result.pk}/approval',{'approval_revision':0,'exclusion_revision':0},'approve-no-region')
        self.assertEqual(approval.status_code,200,approval.content)
        refreshed=self.post(f'/api/playlists/{result.pk}/weather-refresh',{'exclusion_revision':0},'refresh-no-region')
        self.assertEqual(refreshed.status_code,200,refreshed.content)
        self.assertFalse(refreshed.json()['changed'])

    def test_unset_weather_becomes_off_and_invalid_types_are_rejected(self):
        with patch('backend.recommendation.service.obtain',side_effect=AssertionError('Unset region must not read weather')):
            for index,body in enumerate([{}, {'weather_influence_mode':'ON'}, {'region_id':None}, {'region_id':'  '}]):
                response=self.post('/api/recommendation-jobs',body,f'no-on-{index}')
                self.assertEqual(response.status_code,202,response.content)
                job=Job.objects.get(pk=response.json()['job_id'])
                self.assertEqual(job.input['options']['weather_influence_mode'],'OFF')
                self.assertIsNone(job.input['options']['region_id'])
                self.assertIsNone(job.input['weather'])
        response=self.post('/api/recommendation-jobs',{'weather_influence_mode':'OFF','region_id':False},'invalid')
        self.assertEqual(response.status_code,422,response.content)

    def test_region_tree_covers_provided_mapping_and_production_reads_pg(self):
        from backend.weather.regions import bundled
        response=self.client.get('/api/regions/tree')
        self.assertEqual(response.status_code,200,response.content)
        choices=response.json()['items']
        self.assertEqual(len(choices),len(bundled()))
        self.assertGreater(len(choices),3500)
        seongsu=next(row for row in choices if row['region_id']=='region:1120065000')
        self.assertEqual((seongsu['province'],seongsu['district'],seongsu['locality']),('서울특별시','성동구','성수1가제1동'))
        with override_settings(LOCAL_DEMO=False),patch('pipeline.weather.mapping_postgres.load_regions',return_value={
            'entries':[{'id':'r','name':'파장동','address':'경기도 수원시 장안구 파장동','kind':'동','nx':1,'ny':2}]}):
            production=self.client.get('/api/regions/tree').json()
        self.assertEqual(production['source'],'postgresql_mapping')
        self.assertEqual(production['items'][0]['district'],'수원시 장안구')

    def test_import_review_publish_excludes_unapproved_and_binds_source(self):
        self.client.force_login(self.user)
        rows=[]
        for identifier in ['approved','draft']:
            row={name:'' for name in RAW_FIELDS}
            row.update(track_id=identifier,track_name='곡',artists='A',album_name='앨범',duration_ms='240000',
                explicit='False',energy='.4',acousticness='.6',mode='1',tempo='90',time_signature='4',
                instrumentalness='.9',track_genre='jazz')
            rows.append(row)
        stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fieldnames=sorted(RAW_FIELDS));writer.writeheader();writer.writerows(rows)
        raw=stream.getvalue().encode();digest=hashlib.sha256(raw).hexdigest()
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory, override_settings(MUSIC_RAW_DIRECTORY=directory,CSV_UPLOAD_MAX_BYTES=100000):
            def upload(key):
                return self.client.post('/api/admin/music/imports',{'file':SimpleUploadedFile('source.csv',raw),
                    'source_schema_version':RAW_SCHEMA,'source_sha256':digest},HTTP_IDEMPOTENCY_KEY=key)
            imported=upload('import');self.assertEqual(imported.status_code,200,imported.content)
            self.assertEqual(imported.json()['imported_count'],2)
            self.assertEqual(upload('import').json(),imported.json())
            review=Review.objects.get(track_id='approved')
            body={'expected_revision':review.revision,'review_status':'approved','reason':'검수 완료'}
            approved=self.post('/api/admin/music/approved/reviews',body,'review')
            self.assertEqual(approved.status_code,200,approved.content)
            self.assertEqual(self.post('/api/admin/music/approved/reviews',body,'review').json(),approved.json())
            published=self.post('/api/admin/music/catalogs',{'version':'integration-v1','source_ref':'music-source:'+digest,'source_sha256':digest},'publish')
            self.assertEqual(published.status_code,201,published.content)
            self.assertEqual([t['track_id'] for t in Catalog.objects.get(pk='integration-v1').tracks],['approved'])
            self.assertEqual(ReviewChange.objects.count(),1)


class WeatherAdapterTests(SimpleTestCase):
    def source(self):
        from pipeline.weather.common import KST
        now=datetime(2026,10,16,12,10,tzinfo=KST)
        hour=now.replace(minute=0);issued=hour-timedelta(minutes=30)
        def value(code,number,target):
            return {'value':number,'status':'valid','unit':'code','issued_at':issued.isoformat(),
                    'received_at':(issued+timedelta(minutes=1)).isoformat(),'target_at':target.isoformat()}
        document={'nx':60,'ny':127,'observation':{'target_at':hour.isoformat(),'values':{'PTY':value('PTY',0,hour)}},
            'forecast':[{'target_at':(hour+timedelta(hours=i)).isoformat(),'issued_at':issued.isoformat(),
                'values':{code:value(code,number,hour+timedelta(hours=i)) for code,number in [('PTY',0),('SKY',4)]}}
                for i in range(1,7)],'sky_context':[{'target_at':hour.isoformat(),'values':{'SKY':value('SKY',1,hour)}}]}
        return now,document

    def test_actual_source_current_hour_and_184_minute_forecast_contract(self):
        from backend.weather.adapter import build
        from backend.recommendation.weather import validate,current_profile
        now,document=self.source()
        bundle=build({'id':'region','name':'지역','nx':60,'ny':127},document,now,
                     {'observation_max_age_minutes':30,'forecast_max_age_minutes':120})
        segments=validate(bundle,now,184*60*1000)
        self.assertEqual(current_profile(bundle,segments,now),'CLEAR')
        self.assertEqual(bundle['current']['sky'],1)
        self.assertEqual(bundle['segments'][0]['sky'],4)
        with self.assertRaises(DomainError):validate(bundle,now+timedelta(minutes=21))

    def test_missing_current_sky_cannot_be_filled_from_next_hour(self):
        from backend.weather.adapter import build
        from backend.recommendation.weather import validate,current_profile
        now,document=self.source();document['sky_context']=[]
        bundle=build({'id':'region','name':'지역','nx':60,'ny':127},document,now,
                     {'observation_max_age_minutes':30,'forecast_max_age_minutes':120})
        with self.assertRaises(DomainError):current_profile(bundle,validate(bundle,now),now)


class RegionInputContractTests(SimpleTestCase):
    def test_current_request_schema_accepts_unset_weather(self):
        import jsonschema
        schema=json.loads((Path(__file__).resolve().parents[2]/'config/contracts/basic-request.phase3-20261016.3.schema.json').read_text(encoding='utf8'))
        validator=jsonschema.Draft202012Validator(schema)
        for body in [{},{'region_id':''},{'region_id':' '},{'weather_influence_mode':'ON'},
                     {'weather_influence_mode':'OFF'},{'weather_influence_mode':'OFF','region_id':None},
                     {'weather_influence_mode':'OFF','region_id':''},{'region_id':'region:1120065000'}]:
            validator.validate(body)
        for body in [{'weather_influence_mode':'bad'},{'weather_influence_mode':'OFF','region_id':False}]:
            self.assertTrue(list(validator.iter_errors(body)),body)


@override_settings(LOCAL_DEMO=False,MUSIC_S3_BUCKET='test-bucket',MUSIC_S3_REGION='test-region',MUSIC_S3_PREFIX='test/raw',CSV_UPLOAD_MAX_BYTES=1000)
class MusicArchiveTests(SimpleTestCase):
    def test_conditional_upload_pins_version_and_restore_checks_hash(self):
        from unittest.mock import MagicMock
        from .music_archive import store,restore
        raw=b'csv-test-only';digest=hashlib.sha256(raw).hexdigest()
        client=MagicMock()
        client.get_bucket_versioning.return_value={'Status':'Enabled'}
        client.head_object.return_value={'Metadata':{'sha256':digest},'ContentLength':len(raw),'VersionId':'version-1'}
        client.get_object.return_value={'Body':io.BytesIO(raw)}
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            source=Path(directory)/'source.csv';source.write_bytes(raw)
            manifest=store(source,digest,client)
            self.assertEqual(client.put_object.call_args.kwargs['IfNoneMatch'],'*')
            self.assertEqual(manifest['version_id'],'version-1')
            target=Path(directory)/'restored.csv';restore(manifest,target,client)
            self.assertEqual(target.read_bytes(),raw)
            self.assertEqual(client.get_object.call_args.kwargs['VersionId'],'version-1')
            with self.assertRaises(DomainError):restore(manifest,target,client)

    def test_s3_retry_preserves_existing_object_and_checks_content_identity(self):
        from unittest.mock import MagicMock
        from botocore.exceptions import ClientError
        from .music_archive import store
        raw=b'csv-test-only';digest=hashlib.sha256(raw).hexdigest();client=MagicMock()
        client.get_bucket_versioning.return_value={'Status':'Enabled'}
        client.put_object.side_effect=ClientError({'Error':{'Code':'PreconditionFailed'},'ResponseMetadata':{'HTTPStatusCode':412}},'PutObject')
        client.head_object.return_value={'Metadata':{'sha256':digest},'ContentLength':len(raw),'VersionId':'original-version'}
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            source=Path(directory)/'source.csv';source.write_bytes(raw)
            self.assertEqual(store(source,digest,client)['version_id'],'original-version')
            client.head_object.return_value['Metadata']['sha256']='0'*64
            with self.assertRaises(DomainError):store(source,digest,client)

    def test_failed_or_unversioned_archive_never_counts_as_success(self):
        from unittest.mock import MagicMock
        from .music_archive import store,restore
        raw=b'csv-test-only';digest=hashlib.sha256(raw).hexdigest();client=MagicMock()
        client.get_bucket_versioning.return_value={}
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            source=Path(directory)/'source.csv';source.write_bytes(raw)
            with self.assertRaises(DomainError):store(source,digest,client)
            client.put_object.assert_not_called()
            target=Path(directory)/'bad.csv'
            client.get_object.return_value={'Body':io.BytesIO(b'corrupt')}
            with self.assertRaises(DomainError):restore({'mode':'S3','region':'r','bucket':'b','key':'k','version_id':'v','sha256':digest},target,client)
            self.assertFalse(target.exists())
