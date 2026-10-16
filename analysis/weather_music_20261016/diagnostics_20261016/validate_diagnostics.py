"""Independent source/statistic reconciliation and diagnostic artifact checks."""
from __future__ import annotations
import csv,hashlib,json
from functools import lru_cache
from fractions import Fraction as F
from pathlib import Path
import numpy as np
import pandas as pd
D=Path(__file__).resolve().parent
ROOT=D.parents[2]
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_text(encoding="utf-8"))
profile=read(D/'profile_summary.json'); sensitivity=read(D/'sensitivity_summary.json')
manifest=read(D/'baseline_manifest.json'); policy=read(D.parent/'policy.json'); baseline=read(D.parent/'summary.json')
for rel,record in manifest['baseline_files'].items(): assert sha(ROOT/rel)==record['sha256'],rel
source=Path(baseline['source']['path']);assert sha(source)==profile['hashes']['source_sha256']==baseline['source']['sha256']
df=pd.read_csv(source).drop_duplicates('track_id');raw=pd.read_csv(source,dtype=str).drop_duplicates('track_id').set_index('track_id')
pools={w:pd.read_csv(D.parent/'pools'/f'{w}.csv') for w in policy['weather']};ids=set.union(*(set(v.track_id) for v in pools.values()))
base=df[df.track_id.isin(ids)].copy().sort_values('track_id').reset_index(drop=True)
assert len(df)==89741 and len(base)==61931
for r in profile['distribution']:
    cohort=base if r['cohort']=='BASE_ELIGIBLE_61931' else df
    x=cohort[r['feature']].to_numpy(float)
    assert len(x)==r['n'] and np.isclose(x.mean(),r['mean'],rtol=1e-12,atol=1e-12)
    assert np.isclose(x.std(ddof=0),r['std_population_ddof0'],rtol=1e-12,atol=1e-12)
    for q in [0,.01,.05,.25,.5,.75,.95,.99,1]: assert np.isclose(np.quantile(x,q),r[f'p{round(q*100):02d}'])
for r in profile['correlation_pearson']:
    cohort=base if r['cohort']=='BASE_ELIGIBLE_61931' else df
    val=np.corrcoef(cohort[r['feature_x']],cohort[r['feature_y']])[0,1]
    assert np.isclose(val,r['r'],rtol=1e-12,atol=1e-12)
for cohort_name,cohort in [('BASE_ELIGIBLE_61931',base),('SOURCE_UNIQUE_89741',df)]:
    expected=np.diag(np.linalg.inv(np.corrcoef(cohort[['energy','acousticness','valence','mode']].to_numpy(float).T)))
    got=[r['vif'] for r in profile['vif'] if r['cohort']==cohort_name]
    assert np.allclose(expected,got,rtol=1e-10,atol=1e-10)
flagset=set();flag_pairs=0
for criterion in profile['review_flags']['criteria']:
    x=base[criterion['feature']].to_numpy(float);q1,m,q3=np.quantile(x,[.25,.5,.75]);iqr=q3-q1;mad=np.median(abs(x-m))
    iqrflag=(x<q1-1.5*iqr)|(x>q3+1.5*iqr) if iqr else np.zeros(len(x),bool)
    madflag=abs(.6744897501960817*(x-m)/mad)>3.5 if mad else np.zeros(len(x),bool)
    assert int(iqrflag.sum())==criterion['iqr_flag_count'] and int(madflag.sum())==criterion['mad_flag_count']
    flag_pairs+=int((iqrflag|madflag).sum());flagset.update(base.loc[iqrflag|madflag,'track_id'])
assert len(flagset)==profile['review_flags']['unique_flagged_tracks']==37922
assert flag_pairs==profile['review_flags']['flagged_feature_track_pairs']==53691
assert profile['review_flags']['automatic_deleted_count']==0
# Independent exact source-string recomputation of decisive threshold scenarios.
parts={}
for w,weather in policy['weather'].items():
    for pat in weather['patterns']:parts[pat['pattern_id']]={**pat,'weights':weather['weights']}
@lru_cache(None)
def component(pid,name,x):
    lo,hi,h=map(lambda v:F(str(v)),parts[pid][name]);value=F(x)
    return 100*max(F(0),1-max(lo-value,F(0),value-hi)/h)
threshold_result={t:{w:set() for w in policy['weather']} for t in [77,80]}
for row in base.itertuples():
    values=raw.loc[row.track_id]
    for w,weather in policy['weather'].items():
        for pat in weather['patterns']:
            pid=pat['pattern_id']; e=component(pid,'energy',values.energy); a=component(pid,'acousticness',values.acousticness)
            if e<20 or a<20:continue
            v=component(pid,'valence',values.valence);m=100 if int(values['mode'])==pat['preferred_mode'] else 0
            score=F(pat['ceiling'],10000)*sum(weather['weights'][name]*value for name,value in [('energy',e),('acousticness',a),('valence',v),('mode',m)])
            for t in [77,80]:
                if score>=t: threshold_result[t][w].add(row.track_id)
for t,sets in threshold_result.items():
    scenario=next(r for r in sensitivity['scenarios'] if r['configuration']['id']==f'THRESHOLD_{t}')
    assert {w:len(x) for w,x in sets.items()}=={w:r['pool_count'] for w,r in scenario['weather'].items()}
    assert len(ids-set.union(*sets.values()))==scenario['overview']['unmatched_count']
assert sensitivity['scenario_count_including_baseline']==len(sensitivity['scenarios'])==81
for r in sensitivity['scenarios']:
    o=r['overview'];assert sum(o['passing_weather_count_distribution'].values())==61931
    assert o['union_count']+o['unmatched_count']==61931
    assert o['union_count_lower_numeric_bound']<=o['union_count']<=o['union_count_upper_numeric_bound']
    for w,v in r['weather'].items():
        assert v['pool_count']==v['baseline_count']+v['added']-v['removed']
        assert np.isclose(v['jaccard_vs_v2'],(v['baseline_count']-v['removed'])/(v['baseline_count']+v['added']))
        assert v['pool_count_lower_numeric_bound']<=v['pool_count']<=v['pool_count_upper_numeric_bound']
        assert v['top200_retained_count']==200 and v['existing_example_all_tracks_still_eligible']
flags=pd.read_csv(D/'pertrack_sensitivity_flags.csv');assert len(flags)==flags.track_id.nunique()==61931 and set(flags.track_id)==ids
assert int(flags.any_weather_changed_count.gt(0).sum())==sensitivity['pertrack_flags']['tracks_with_any_flip']
for w,frame in pools.items():
    ex=pd.read_csv(D.parent/'examples'/f'{w}_180min.csv')
    assert ex.track_id.is_unique and set(ex.track_id)<=set(frame.track_id) and ex.duration_ms.sum()==10800000
sample_path=D/'llm_review_sample.csv'
if sample_path.exists():
    sample=pd.read_csv(sample_path);assert len(sample)==sample.track_id.nunique()==500 and set(sample.track_id)<=ids
result={'status':'PASS','analysis_version':'WEATHER_DIAGNOSTICS_20261016_V1','checks':{'baseline_14_artifact_hashes_unchanged':True,'source_sha256_unchanged':True,'full_distribution_moments_and_quantiles_recomputed':True,'full_pearson_matrix_recomputed':True,'vif_independent_inverse_correlation_check':True,'all_global_iqr_mad_counts_recomputed':True,'threshold77_and80_independent_full_fraction_recalculation':True,'all81_scenario_count_and_jaccard_reconciled':True,'flags_base_id_set_equal':True,'five_original_examples_exact180min':True,'review_sample_500_unique':sample_path.exists()},'base_tracks':61931,'global_flagged_tracks':len(flagset),'global_flagged_feature_pairs':flag_pairs,'threshold_unmatched':{str(t):len(ids-set.union(*sets.values())) for t,sets in threshold_result.items()},'profile_summary_sha256':sha(D/'profile_summary.json'),'sensitivity_summary_sha256':sha(D/'sensitivity_summary.json'),'nonlinear_limit':'sqrt(.5) SNOW 3 qualification decisions unresolved within declared1e-8 interval; kept as bounds, not silently accepted as exact'}
(D/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))
