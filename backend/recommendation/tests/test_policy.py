import csv
import tempfile
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch, MagicMock
from django.test import override_settings
from pipeline.music.normalize import normalize, speed, instrumental, convert, RAW_SCHEMA, RESULT_SCHEMA
from backend.recommendation.policy import score, initial_speeds, groups, eligible, profile, weather_fit, precompute_scores, theme_affinity, THEMES, WEATHER_WEIGHTS
from backend.recommendation.inputs import DEFAULTS, options
from backend.recommendation.provider import validate_proposal, candidate_window, propose
from backend.recommendation.solver import choose, choose_preview, representatives
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
    def test_all_selected_codes_are_equivalent_to_none(self):
        from backend.recommendation.policy import THEMES, GENRES
        self.assertEqual(options({'selected_theme_codes':list(THEMES),'selected_genre_codes':list(GENRES)}),DEFAULTS)
    def test_off_theme_formula_and_no_weather(self):
        track={'energy':7,'mode':False,'speed':'fast','genre_group_codes':['JAZZ'],'theme_codes':[]}
        off={**DEFAULTS,'weather_influence_mode':'OFF','selected_theme_codes':['CALM']}
        self.assertEqual(score(track,off)['P'],Fraction(7550,95))
        self.assertIsNone(score(track,off)['W'])
        self.assertEqual(score(track,{**off,'tempo_preference':'fast'})['P'],Fraction(8300,95))
    def test_primary_core_gate_does_not_reuse_its_higher_score(self):
        evidence=weather_fit({'raw_energy':'.843','raw_acousticness':'.5','raw_valence':'.53','mode':False},'CLOUDY')
        self.assertEqual(evidence['pattern'],'CLOUDY_SUPPORT')
        self.assertEqual(evidence['W'],Fraction(376,5))
        self.assertEqual(evidence['attempts'][0]['E'],19)
        self.assertFalse(evidence['attempts'][0]['core_pass'])
    def test_mixed_weather_requires_both_pools(self):
        track={'raw_energy':'.2','raw_acousticness':'.8','raw_valence':'.5','mode':True}
        evidence=weather_fit(track,'MIXED')
        self.assertEqual(len(evidence['patterns']),2)
        self.assertEqual(evidence['W'],min(x['W'] for x in evidence['patterns']))
    def test_profiles_and_scores(self):
        self.assertEqual(profile(6,None),'MIXED');self.assertEqual(profile(7,None),'SNOW')
        track={'energy':6,'raw_energy':'.6','raw_acousticness':'.5','raw_valence':'.7',
               'mode':True,'speed':'slow','genre_group_codes':['JAZZ'],'theme_codes':[]}
        result=score(track,DEFAULTS,'CLEAR')
        self.assertEqual(result['W'],100);self.assertEqual(result['S'],100)
        self.assertIsNone(score(track,DEFAULTS,'RAIN'))
    def test_active_group_denominator(self):
        t={'energy':6,'raw_energy':'.6','raw_acousticness':'.5','raw_valence':'.7','mode':True,'theme_codes':[],
           'speed':'slow','genre_group_codes':['JAZZ']}
        o={**DEFAULTS,'selected_theme_codes':['CALM'],'selected_genre_codes':['JAZZ'],'tempo_preference':'slow'}
        s=score(t,o,'CLEAR')
        self.assertEqual(s['P'],(200+theme_affinity(t,'CALM'))/3)
        self.assertEqual(s['S'],Fraction(3,4)*s['W']+Fraction(1,4)*s['P'])
        self.assertGreater(s['P'],Fraction(200,3))
    def test_published_scores_match_live_formula_and_do_not_invent_mood(self):
        t={'energy':6,'raw_energy':'.6','raw_acousticness':'.5','raw_valence':'.7','mode':True,
           'speed':'slow','genre_group_codes':['JAZZ'],'theme_codes':[],'mood':None,'main_inst':None}
        cached=precompute_scores(t)
        self.assertEqual(set(cached['score_cache']['weather']),set(WEATHER_WEIGHTS))
        self.assertEqual(set(cached['score_cache']['theme']),set(THEMES))
        self.assertIsNone(cached['mood']);self.assertIsNone(cached['main_inst'])
        for weather in (*WEATHER_WEIGHTS,'MIXED'):
            for selected in ([],['CALM'],['CALM','BRIGHT']):
                options={**DEFAULTS,'selected_theme_codes':selected}
                self.assertEqual(score(cached,options,weather),score(t,options,weather))
        off={**DEFAULTS,'weather_influence_mode':'OFF','selected_theme_codes':['CALM','BRIGHT']}
        self.assertEqual(score(cached,off),score(t,off))
        with (patch('backend.recommendation.policy.weather_fit',side_effect=AssertionError('recomputed weather')),
              patch('backend.recommendation.policy.off_preference_details',side_effect=AssertionError('recomputed theme'))):
            self.assertEqual(score(cached,{**DEFAULTS,'selected_theme_codes':['CALM']},'CLEAR')['W'],100)
            self.assertIsNotNone(score(cached,off)['P'])
    def test_mode_null_no_redistribution(self):
        t={'raw_energy':'.6','raw_acousticness':'.5','raw_valence':'.7','mode':None,'theme_codes':[]}
        self.assertEqual(score(t,DEFAULTS,'CLEAR')['W'],95)
    def test_mixed_first_speed_block_only_auto_fast(self):
        self.assertEqual(initial_speeds('slow','MIXED'),['slow'])
        self.assertEqual(initial_speeds('auto','MIXED'),['fast','fastest','medium','slow'])
        self.assertEqual(initial_speeds('fast','RAIN'),['fast'])
        self.assertEqual(initial_speeds('fast','CLEAR'),['fast','fastest'])
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
        result=score({'raw_energy':'.6','raw_acousticness':'.4','raw_valence':'.7','mode':True,'theme_codes':[]},DEFAULTS,'CLEAR')
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
    def test_off_selected_genres_100_percent_precedes_exact_time(self):
        selected={'track_id':'selected','duration_ms':10680000,'genre_group_codes':['JAZZ'],'scores':{'S':Fraction(80)}}
        other={'track_id':'other','duration_ms':120000,'genre_group_codes':['POP'],'scores':{'S':Fraction(100)}}
        result=choose([selected,other],2,5,'OFF',['JAZZ'])
        self.assertEqual([t['track_id'] for t in result],['selected'])
    def test_off_80_percent_fallback_and_distinct_representatives(self):
        tracks=[{'track_id':'j','duration_ms':4320000,'genre_group_codes':['JAZZ'],'scores':{'S':Fraction(80)}},
                {'track_id':'p','duration_ms':4320000,'genre_group_codes':['POP'],'scores':{'S':Fraction(80)}},
                {'track_id':'other','duration_ms':2160000,'genre_group_codes':['ROCK'],'scores':{'S':Fraction(100)}}]
        result=choose(tracks,3,5,'OFF',['JAZZ','POP'])
        self.assertEqual({t['track_id'] for t in result},{'j','p','other'})
        self.assertIsNone(representatives([{'track_id':'one','genre_group_codes':['JAZZ','POP']}],['JAZZ','POP']))
        tracks[1]['duration_ms']-=1
        tracks[2]['duration_ms']+=1
        with self.assertRaises(DomainError) as failure: choose(tracks,3,5,'OFF',['JAZZ','POP'])
        self.assertEqual(failure.exception.code,'CANDIDATE_SHORTAGE')
    def test_window_failure_expands_before_reporting_shortage(self):
        tiny=[{'track_id':f't{i:03}','duration_ms':1,'genre_group_codes':['JAZZ'],'scores':{'S':Fraction(100)}}
              for i in range(200)]
        full={'track_id':'last','duration_ms':10800000,'genre_group_codes':['JAZZ'],'scores':{'S':Fraction(0)}}
        diagnostics={}
        self.assertEqual(choose(tiny+[full],0,5,'ON',(),'',diagnostics)[0]['track_id'],'last')
        self.assertEqual(diagnostics['window_size'],201)
        with self.assertRaises(DomainError) as failure: choose(tiny+[full],200,5,'ON')
        self.assertEqual(failure.exception.code,'SEARCH_INCOMPLETE')
    def test_csv_preview_reset_keeps_genre_and_adds_twenty_percent_new_tracks(self):
        jazz=[{'track_id':f'j{i}','duration_ms':204000,'genre_group_codes':['JAZZ'],
               'scores':{'S':Fraction(100)}} for i in range(52)]
        other=[{'track_id':f'o{i}','duration_ms':60000,'genre_group_codes':['POP'],
                'scores':{'S':Fraction(80)}} for i in range(20)]
        parent={t['track_id'] for t in jazz}
        tracks,diagnostics=choose_preview(jazz+other,'OFF',['JAZZ'],'retry-seed',parent)
        total=sum(t['duration_ms'] for t in tracks)
        selected=sum(t['duration_ms'] for t in tracks if 'JAZZ' in t['genre_group_codes'])
        self.assertGreaterEqual(len({t['track_id'] for t in tracks}-parent),len(parent)//5)
        self.assertGreaterEqual(100*selected,80*total)
        self.assertTrue(10560000<=total<=11040000)
        self.assertEqual(diagnostics['genre_share_stage'],80)
    def test_csv_preview_expands_when_top_200_cannot_fill_duration(self):
        tracks=[{'track_id':f't{i:03}','duration_ms':1,'genre_group_codes':['JAZZ'],
                 'scores':{'S':Fraction(100)}} for i in range(200)]
        tracks.append({'track_id':'last','duration_ms':10800000,'genre_group_codes':['JAZZ'],
                       'scores':{'S':Fraction(0)}})
        result,diagnostics=choose_preview(tracks,'ON')
        self.assertIn('last',{t['track_id'] for t in result})
        self.assertEqual(diagnostics['window_size'],201)


class ProviderTests(TestCase):
    @override_settings(GEMINI_MAX_CANDIDATES=200)
    def test_large_csv_window_is_bounded_and_reserves_new_and_genre_tracks(self):
        tracks=[{'track_id':str(i),'genre_group_codes':['JAZZ' if i<299 else 'POP'],
                 'scores':{'S':Fraction(300-i)}} for i in range(300)]
        context={'options':{**DEFAULTS,'selected_genre_codes':['JAZZ','POP']},'seed':'fixed'}
        window=candidate_window(tracks,context,[str(i) for i in range(200)])
        self.assertEqual(len(window),200)
        self.assertIn('299',{t['track_id'] for t in window})
        self.assertGreaterEqual(len({t['track_id'] for t in window}-{str(i) for i in range(200)}),40)
        self.assertEqual(window,candidate_window(tracks,context,[str(i) for i in range(200)]))

    @override_settings(GEMINI_ENABLED=True,GEMINI_TIMEOUT_MS=60000,GEMINI_MAX_CANDIDATES=200)
    @patch.dict('os.environ',{'GEMINI_API_KEY':'test-key','GEMINI_MAX_OUTPUT_TOKENS':'8192'})
    def test_provider_busy_reports_safe_failure_without_retry(self):
        error=type('BusyError',(Exception,),{'code':503})('test-key must not appear')
        client=MagicMock();client.models.generate_content.side_effect=error
        context={'options':{**DEFAULTS,'weather_influence_mode':'OFF'}}
        with patch('google.genai.Client',return_value=client),self.assertRaises(DomainError) as failure:
            propose([],context,[])
        self.assertEqual(failure.exception.code,'PROVIDER_BUSY')
        self.assertEqual(failure.exception.details,{'provider_status':503})
        self.assertNotIn('test-key',failure.exception.message)
        client.models.generate_content.assert_called_once()

    def test_model_cannot_return_unoffered_ids_from_full_catalog(self):
        track={'track_id':'not-offered','duration_ms':10800000}
        proposal={'track_ids':['not-offered'],'summary':'explanation',
                  'track_reasons':[{'track_id':'not-offered','reason':'reason'}]}
        with self.assertRaises(DomainError) as failure:
            validate_proposal(proposal,[],['parent'],DEFAULTS,all_candidates=[track])
        self.assertEqual(failure.exception.code,'PROVIDER_RESPONSE_INVALID')

    def test_novelty_49_floor_and_invalid_reasons(self):
        candidates=[{'track_id':str(i),'duration_ms':200000} for i in range(60)]
        ids=[str(i) for i in range(54)]
        proposal={'track_ids':ids,'summary':'설명','track_reasons':[{'track_id':x,'reason':'이유'} for x in ids]}
        with self.assertRaises(DomainError) as e: validate_proposal(proposal,candidates,[str(i) for i in range(49)],DEFAULTS)
        self.assertEqual(e.exception.code,'NO_MEANINGFUL_CHANGE')
        self.assertEqual(e.exception.details['required_new_count'],9)
        validate_proposal(proposal,candidates,[str(i) for i in range(40)],DEFAULTS)
        proposal['track_reasons'][0]['track_id']='missing'
        with self.assertRaises(DomainError) as e: validate_proposal(proposal,candidates,[],DEFAULTS)
        self.assertEqual(e.exception.code,'PROVIDER_RESPONSE_INVALID')
