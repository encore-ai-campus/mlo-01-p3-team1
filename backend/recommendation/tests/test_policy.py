import csv
import tempfile
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from unittest import TestCase
from pipeline.music.normalize import normalize, speed, instrumental, convert, RAW_SCHEMA, RESULT_SCHEMA
from backend.recommendation.policy import score, initial_speeds, groups, eligible, profile
from backend.recommendation.inputs import DEFAULTS
from backend.recommendation.provider import validate_proposal
from backend.recommendation.solver import choose
from backend.recommendation.errors import DomainError
from backend.recommendation.weather import validate


def row(**changes):
    return {'track_id':'a','track_name':'곡','artists':'A;B;C','album_name':'앨범','duration_ms':'240000',
            'explicit':'False','energy':'.5999','mode':'0','acousticness':'.6099','tempo':'90',
            'time_signature':'4','instrumentalness':'.9','track_genre':'jazz','popularity':'0',
            'danceability':'.5','key':'0','loudness':'-5','speechiness':'.1','liveness':'.1','valence':'.5',**changes}


class ConversionTests(TestCase):
    def test_floor_and_false_preserved(self):
        n=normalize(row(),RAW_SCHEMA)
        self.assertEqual((n['energy'],n['acousticness'],n['mode']),(5,60,False))
        self.assertFalse(n['explicit']); self.assertTrue(n['instrumental'])
    def test_speed_half_up_boundaries(self):
        for tempo,expected in [('79.49','slow'),('79.5','medium'),('109.49','medium'),('109.5','fast'),('149.5','fastest')]:
            self.assertEqual(speed(tempo,None),expected)
        self.assertEqual(speed('120','3'),'medium')
        self.assertIsNone(speed(None,'3'))
    def test_review_false_and_clear(self):
        self.assertEqual(instrumental('.99',False),(False,'REVIEW'))
        self.assertEqual(instrumental('.8'),(True,'AUTO'))
        self.assertEqual(instrumental('.2'),(None,'AUTO'))
        self.assertEqual(instrumental('.199'),(False,'AUTO'))
        self.assertEqual(instrumental(None,None,False),(False,'PRESERVED'))
        self.assertEqual(instrumental(None),(None,'UNKNOWN'))
        self.assertFalse(normalize(row(),RAW_SCHEMA,{'instrumental_review_value':False})['instrumental'])
    def test_artist_slots(self):
        self.assertEqual(normalize(row(artists_id='idA;;idC'),RAW_SCHEMA)['artists_id'],'idA;;idC')
        with self.assertRaises(ValueError): normalize(row(artists_id='idA;idC'),RAW_SCHEMA)
    def test_null_and_invalid_inputs(self):
        for changes in [{'explicit':''},{'mode':'2'},{'energy':'1.1'},{'duration_ms':True},{'track_name':''}]:
            with self.assertRaises(ValueError): normalize(row(**changes),RAW_SCHEMA)
        self.assertEqual(normalize(row(duration_ms='0'),RAW_SCHEMA)['duration_ms'],0)
    def test_normalized_input_not_rescaled(self):
        first=normalize(row(),RAW_SCHEMA)
        second=normalize(first,RESULT_SCHEMA)
        self.assertEqual(second['energy'],5);self.assertEqual(second['acousticness'],60)
    def test_genre_union_and_conflict_quarantine(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as tmp:
            path=Path(tmp)/'source.csv'
            with path.open('w',newline='',encoding='utf8') as out:
                writer=csv.DictWriter(out,fieldnames=list(row()));writer.writeheader()
                writer.writerows([row(),row(track_genre='classical'),row(track_id='bad'),row(track_id='bad',duration_ms='1')])
            result=convert(path,RAW_SCHEMA)
            self.assertEqual(len(result['tracks']),1)
            self.assertEqual(result['tracks'][0]['genre'],'classical;jazz')
            self.assertEqual(result['conflicting_track_ids'],['bad'])


class PolicyTests(TestCase):
    def test_profiles_and_scores(self):
        self.assertEqual(profile(6,None),'MIXED');self.assertEqual(profile(7,None),'SNOW')
        track={'energy':4,'acousticness':60,'mode':True,'theme_codes':[]}
        for pty,sky in [(0,1),(1,None)]:
            result=score(track,DEFAULTS,[{'pty':pty,'sky':sky,'overlap_ms':10800000}])
            self.assertEqual(result['W'],95);self.assertEqual(result['S'],95)
    def test_active_group_denominator(self):
        t={'energy':4,'acousticness':60,'mode':True,'theme_codes':[]}
        o={**DEFAULTS,'selected_theme_codes':['CALM'],'selected_genre_codes':['JAZZ'],'tempo_preference':'slow'}
        s=score(t,o,[{'pty':0,'sky':1,'overlap_ms':10800000}])
        self.assertEqual(s['P'],Fraction(200,3))
        self.assertEqual(s['S'],Fraction(1055,12))
    def test_mode_null_no_redistribution(self):
        s=score({'energy':6,'acousticness':40,'mode':None,'theme_codes':[]},DEFAULTS,[{'pty':0,'sky':1,'overlap_ms':10800000}])
        self.assertEqual(s['W'],95)
    def test_mixed_first_speed_block_only_auto_fast(self):
        mixed=[{'pty':0,'sky':1},{'pty':1,'sky':4}]
        self.assertEqual(initial_speeds('slow',mixed),['slow'])
        with self.assertRaises(DomainError): initial_speeds('auto',mixed)
        self.assertEqual(initial_speeds('fast',[{'pty':1,'sky':4}]),['fast'])
        self.assertEqual(initial_speeds('fast',[{'pty':4,'sky':4}]),['fast','fastest'])
    def test_genres(self):
        self.assertEqual(groups(['j-rock']),['J-POP','ROCK'])
        self.assertEqual(groups(['ambient','study']),[])
        self.assertEqual(len(groups(['jazz','jazz'])),1)
        track={'track_id':'x','duration_ms':1,'energy':4,'acousticness':60,'genre_group_codes':['JAZZ'],
               'speed':'slow','instrumental':True,'instrumental_review_value':False}
        self.assertFalse(eligible(track,{**DEFAULTS,'vocal_option':'instrumental_only'},['JAZZ'],['slow'],[]))


class WeatherTests(TestCase):
    def bundle(self, start, segments):
        return {'as_of':start,'valid_until':'2026-10-15T12:05:00Z','segments':[
            {'start_at':left,'end_at':right,'pty':0,'sky':1,'status':'valid',
             'issued_at':'2026-10-15T00:00:00Z','received_at':'2026-10-15T00:00:00Z'} for left,right in segments]}
    def test_submillisecond_boundaries_preserve_full_weight(self):
        bundle=self.bundle('2026-10-15T09:00:00.123456Z',[
            ('2026-10-15T09:00:00Z','2026-10-15T10:00:00Z'),
            ('2026-10-15T10:00:00Z','2026-10-15T13:00:00Z')])
        rows=validate(bundle,datetime(2026,10,15,9,tzinfo=timezone.utc))
        self.assertEqual(sum(row['overlap_ms'] for row in rows),10800000)
        result=score({'energy':6,'acousticness':40,'mode':True,'theme_codes':[]},DEFAULTS,rows)
        self.assertEqual(result['W'],100)
    def test_offset_strings_are_sorted_by_absolute_instant(self):
        bundle=self.bundle('2026-10-15T09:00:00Z',[
            ('2026-10-15T10:00:00Z','2026-10-15T12:00:00Z'),
            ('2026-10-15T18:00:00+09:00','2026-10-15T19:00:00+09:00')])
        rows=validate(bundle,datetime(2026,10,15,9,tzinfo=timezone.utc))
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]['overlap_ms'],3600000)
    def test_non_string_instant_is_a_forecast_error(self):
        with self.assertRaises(DomainError) as error:
            validate({'as_of':1},datetime.now(timezone.utc))
        self.assertEqual(error.exception.code,'FORECAST_UNAVAILABLE')


class SolverTests(TestCase):
    def tracks(self,durations):
        return [{'track_id':str(i),'duration_ms':d,'scores':{'S':Fraction(100)}} for i,d in enumerate(durations)]
    def test_time_priority_excess_before_shorter(self):
        result=choose(self.tracks([10740000,10920000]),4,5)
        self.assertEqual(result[0]['duration_ms'],10920000)
    def test_exact_before_better_quality_and_canonical_tie(self):
        tracks=self.tracks([10800000,10800000,10900000]);tracks[2]['scores']['S']=Fraction(200)
        self.assertEqual(choose(tracks,4,5)[0]['track_id'],'0')
    def test_duration_boundaries(self):
        for value in [10560000,10800000,11040000]: self.assertEqual(len(choose(self.tracks([value]),2,5)),1)
        for value in [10559999,11040001]:
            with self.assertRaises(DomainError) as e: choose(self.tracks([value]),2,5)
            self.assertEqual(e.exception.code,'CANDIDATE_SHORTAGE')
    def test_limited_pool_is_not_shortage(self):
        with self.assertRaises(DomainError) as e: choose(self.tracks([100]*3),2,1)
        self.assertEqual(e.exception.code,'SEARCH_INCOMPLETE')
    def test_exact_quality_fraction(self):
        tracks=self.tracks([10800000,10800000]);tracks[1]['scores']['S']=Fraction(1000001,10000)
        self.assertEqual(choose(tracks,3,5)[0]['track_id'],'1')


class ProviderTests(TestCase):
    def test_novelty_49_floor_and_invalid_reasons(self):
        candidates=[{'track_id':str(i),'duration_ms':200000} for i in range(60)]
        ids=[str(i) for i in range(54)]
        proposal={'track_ids':ids,'summary':'설명','track_reasons':[{'track_id':x,'reason':'이유'} for x in ids]}
        with self.assertRaises(DomainError) as e: validate_proposal(proposal,candidates,[str(i) for i in range(49)])
        self.assertEqual(e.exception.code,'NO_MEANINGFUL_CHANGE')
        self.assertEqual(e.exception.details['required_new_count'],9)
        validate_proposal(proposal,candidates,[str(i) for i in range(40)])
        proposal['track_reasons'][0]['track_id']='missing'
        with self.assertRaises(DomainError) as e: validate_proposal(proposal,candidates,[])
        self.assertEqual(e.exception.code,'PROVIDER_RESPONSE_INVALID')
