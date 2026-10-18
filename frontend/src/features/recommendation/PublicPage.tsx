import {useEffect,useRef,useState} from 'react';
import {api,ApiError,canonical,key,setCsrf,wait} from '../../shared/api';
import type {Choices,Option,Playlist,Exclusions} from '../../shared/types';
import {Guide} from '../onboarding/Guide';
import {Banner} from '../ad-banners/Banner';
import {useFeedback} from '../feedback/Feedback';
import {Header} from '../../components/Header';
import {WeatherPanel} from '../region-weather/WeatherPanel';
import type {Weather} from '../region-weather/WeatherPanel';
import type {RegionOption} from '../region-weather/RegionPicker';
import {Icon} from '../../components/Icons';
import {TagPicker} from '../music-options/TagPicker';

const defaults:Choices={region_id:'',vocal_option:'any',tempo_preference:'auto',weather_influence_mode:'ON',selected_theme_codes:[],selected_genre_codes:[],option_version:''};
function Cover({url,small=false}:{url?:string|null;small?:boolean}){
  return <img className={small?'track-cover':'album-cover'} src={url||'/default-cover.svg'} alt={small?'':'현재 선곡표 첫 곡의 앨범 이미지'} onError={e=>{e.currentTarget.onerror=null;e.currentTarget.src='/default-cover.svg';}}/>;
}
export function PublicPage(){
  const [choices,setChoices]=useState(defaults),[options,setOptions]=useState<Option[]>([]),[regions,setRegions]=useState<RegionOption[]>([]);
  const [result,setResult]=useState<Playlist|null>(null),[excluded,setExcluded]=useState<Exclusions|null>(null),[draft,setDraft]=useState<string[]>([]);
  const [weather,setWeather]=useState<Weather|null>(null),[weatherError,setWeatherError]=useState(''),[error,setError]=useState(''),[saveError,setSaveError]=useState('');
  const [busy,setBusy]=useState(false),[saving,setSaving]=useState(false),[approving,setApproving]=useState(false),[guide,setGuide]=useState(false),[widget,setWidget]=useState(true),[expanded,setExpanded]=useState(false);
  const [isDemo,setDemo]=useState(false),[initRetry,setInitRetry]=useState(0),[weatherRetry,setWeatherRetry]=useState(0);
  const [musicSource,setMusicSource]=useState<string>();
  const [adContextReady,setAdContextReady]=useState(false);
  const [contextReady,setContextReady]=useState(false);
  const [regionLoading,setRegionLoading]=useState(true),[regionError,setRegionError]=useState(''),[regionRetry,setRegionRetry]=useState(0);
  const [saveIntent,setSaveIntent]=useState<{ids:string[];body:unknown;id:string}|null>(null);
  const [jobIntent,setJobIntent]=useState<{path:string;body:unknown;id:string}|null>(null);
  const abort=useRef<AbortController|null>(null);
  const feedback=useFeedback(result?.playlist_id);
  useEffect(()=>{
    const controller=new AbortController();setError('');setContextReady(false);
    async function boot(){
      const opts=await api<{option_version:string;items:Option[]}>('/api/recommendation-options','GET',undefined,undefined,controller.signal);
      setOptions(opts.items);setChoices(c=>({...c,option_version:opts.option_version}));
      if(import.meta.env.VITE_C_DEMO==='1'){
        const context=await api<{csrf_token:string;regions:typeof regions;music_source?:{kind:string}}>('/api/c-demo/context','GET',undefined,undefined,controller.signal);
        setCsrf(context.csrf_token);setRegions(context.regions);setMusicSource(context.music_source?.kind);setDemo(true);setContextReady(true);
      }else{
        await api('/api/auth/me','GET',undefined,undefined,controller.signal);
        setContextReady(true);
        // Region loading has its own retry and does not block OFF recommendations.
      }
    }
    void boot().catch(e=>{if(!controller.signal.aborted)setError(e.message);});
    return()=>controller.abort();
  },[initRetry]);
  useEffect(()=>{
    if(!contextReady)return;
    if(import.meta.env.VITE_C_DEMO==='1'){setRegionLoading(!contextReady);return;}
    const controller=new AbortController();setRegionLoading(true);setRegionError('');
    void api<{items:RegionOption[]}>('/api/regions/tree','GET',undefined,undefined,controller.signal).then(data=>{
      if(controller.signal.aborted)return;setRegions(data.items);
      let stored='';try{stored=localStorage.getItem('cafe-region')||'';}catch{/* optional */}
      if(data.items.some(row=>row.region_id===stored))setChoices(c=>c.region_id?c:{...c,region_id:stored});
    }).catch(()=>{if(!controller.signal.aborted)setRegionError('지역 목록을 불러오지 못했어요.');})
      .finally(()=>{if(!controller.signal.aborted)setRegionLoading(false);});
    return()=>controller.abort();
  },[regionRetry,contextReady]);
  useEffect(()=>()=>abort.current?.abort(),[]);
  useEffect(()=>{
    setWeather(null);setWeatherError('');if(!choices.region_id)return;
    const controller=new AbortController();
    const refresh=()=>api<Weather>(`/api/weather?region_id=${encodeURIComponent(choices.region_id)}`,'GET',undefined,undefined,controller.signal).then(data=>{if(!controller.signal.aborted){setWeather(data);setWeatherError('');}}).catch(e=>{if(!controller.signal.aborted){setWeather(null);setWeatherError(e.message);}});
    void refresh();
    const interval=setInterval(()=>void refresh(),Math.max(1000,Number(import.meta.env.VITE_WEATHER_POLL_MS||30000)));
    return()=>{controller.abort();clearInterval(interval);};
  },[choices.region_id,weatherRetry,isDemo]);
  useEffect(()=>{if(choices.region_id&&!isDemo)try{localStorage.setItem('cafe-region',choices.region_id);}catch{/* optional */}},[choices.region_id,isDemo]);
  function normalized(value:Choices){
    const result={...value};
    for(const [type,field] of [['theme','selected_theme_codes'],['genre','selected_genre_codes']] as const){
      const all=options.filter(o=>o.type===type&&o.enabled).map(o=>o.code);
      if(all.length&&all.every(code=>result[field].includes(code)))result[field]=[];
    }
    return {...result,region_id:result.region_id||null,
      weather_influence_mode:result.region_id?result.weather_influence_mode:'OFF' as const};
  }
  const effectiveMode=choices.region_id?choices.weather_influence_mode:'OFF';
  const changed=!!result&&canonical(normalized(choices))!==canonical(result.context.options);
  const dirty=!!excluded&&canonical(draft)!==canonical(excluded.excluded_track_ids);
  const locked=busy||saving||approving;
  const canRegenerate=!!result&&!locked&&!changed&&!dirty&&!saveError;
  const weatherMismatch=!!result&&result.context.options.weather_influence_mode==='ON'&&!!weather?.weather_code&&result.context.weather_code!==weather.weather_code;
  const canApprove=canRegenerate&&!weatherMismatch&&canonical(result!.context.excluded_track_ids)===canonical(excluded?.excluded_track_ids);
  const refreshed=useRef('');
  useEffect(()=>{
    if(!weatherMismatch||!result||!weather||!excluded||busy||saving||approving||changed||dirty||!weather.recommendation_ready)return;
    const identity=result.playlist_id+'/'+weather.bundle_version;
    if(refreshed.current===identity)return;refreshed.current=identity;
    const controller=new AbortController();abort.current=controller;setBusy(true);setError('');
    async function refresh(){
      try{
        const accepted=await api<{job_id?:string}>('/api/playlists/'+result!.playlist_id+'/weather-refresh','POST',{exclusion_revision:excluded!.revision},key(),controller.signal);
        if(!accepted.job_id)return;
        const start=performance.now();
        for(;;){
          if(performance.now()-start>Number(import.meta.env.VITE_JOB_POLL_TIMEOUT_MS||120000))throw new Error('날씨 갱신 작업이 지연되고 있어요. 기존 선곡표는 유지됩니다.');
          const job=await api<{status:string;playlist_id:string;error?:{message:string}}>('/api/recommendation-jobs/'+accepted.job_id,'GET',undefined,undefined,controller.signal);
          if(job.status==='SUCCEEDED'){await loadResult(job.playlist_id,controller.signal);break;}
          if(job.status==='FAILED'||job.status==='EXPIRED')throw new Error(job.error?.message||'새 날씨에 맞춘 선곡표를 만들지 못했어요.');
          await wait(1000,controller.signal);
        }
      }catch(e){if(!controller.signal.aborted)setError((e as Error).message);}
      finally{if(!controller.signal.aborted)setBusy(false);}
    }
    void refresh();
  },[weather?.bundle_version,result?.playlist_id,weatherMismatch,busy,saving,approving,changed,dirty]);
  function toggleOption(option:Option){
    const field=option.type==='genre'?'selected_genre_codes':'selected_theme_codes';
    setChoices(c=>({...c,[field]:c[field].includes(option.code)?c[field].filter(x=>x!==option.code):[...c[field],option.code].sort()}));
  }
  async function loadResult(id:string,signal?:AbortSignal){
    const p=await api<Playlist>(`/api/playlists/${id}`,'GET',undefined,undefined,signal);
    const ex=await api<Exclusions>(`/api/playlist-families/${p.family_id}/exclusions`,'GET',undefined,undefined,signal);
    setResult(p);setExcluded(ex);setDraft(ex.excluded_track_ids);setSaveError('');setSaveIntent(null);
  }
  async function generate(regenerate=false,retry=false){
    if(busy)return;
    const intent=retry?jobIntent:{path:regenerate?`/api/playlists/${result!.playlist_id}/regenerations`:'/api/recommendation-jobs',
      body:regenerate?{exclusion_revision:excluded!.revision}:normalized(choices),id:key()};
    if(!intent)return;
    setBusy(true);setError('');setJobIntent(intent);abort.current?.abort();const controller=new AbortController();abort.current=controller;
    try{
      const job=await api<{job_id:string}>(intent.path,'POST',intent.body,intent.id,controller.signal);
      const started=performance.now();
      for(;;){
        if(performance.now()-started>Number(import.meta.env.VITE_JOB_POLL_TIMEOUT_MS||120000))throw new Error('작업 조회를 잠시 멈췄어요. 같은 요청 다시 확인으로 진행 상태를 확인해 주세요.');
        const status=await api<{status:string;playlist_id:string|null;error:{message:string}|null}>(`/api/recommendation-jobs/${job.job_id}`,'GET',undefined,undefined,controller.signal);
        if(status.status==='SUCCEEDED'){await loadResult(status.playlist_id!,controller.signal);setJobIntent(null);break;}
        if(status.status==='FAILED'||status.status==='EXPIRED'){setJobIntent(null);throw new Error(status.error?.message||'선곡표 생성에 실패했어요.');}
        await wait(performance.now()-started<5000?300:1000,controller.signal);
      }
    }catch(e){if(!controller.signal.aborted){setError((e as Error).message);if(e instanceof ApiError)setJobIntent(null);}}
    finally{if(!controller.signal.aborted)setBusy(false);}
  }
  async function saveExclusions(ids:string[],retry=false){
    if(!result||!excluded||saving)return;
    const intent=retry?saveIntent:{ids:[...ids].sort(),body:{source_playlist_id:result.playlist_id,expected_revision:excluded.revision,excluded_track_ids:ids},id:key()};
    if(!intent)return;
    setDraft(intent.ids);setSaving(true);setSaveError('');setSaveIntent(intent);
    try{
      await api(`/api/playlist-families/${result.family_id}/exclusions`,'PUT',intent.body,intent.id);
      const ex=await api<Exclusions>(`/api/playlist-families/${result.family_id}/exclusions`);
      setExcluded(ex);setDraft(ex.excluded_track_ids);setSaveIntent(null);
    }catch(e){setSaveError((e as Error).message);}
    finally{setSaving(false);}
  }
  const approvalIntent=useRef<{playlist:string;body:unknown;id:string}|null>(null);
  async function approve(){
    if(!result||!excluded||!canApprove)return;
    setApproving(true);setError('');
    const body={approval_revision:result.approval_revision,exclusion_revision:excluded.revision};
    const cached=approvalIntent.current;
    const intent=cached&&cached.playlist===result.playlist_id&&canonical(cached.body)===canonical(body)?cached:{playlist:result.playlist_id,body,id:key()};
    approvalIntent.current=intent;
    try{await api(`/api/playlists/${result.playlist_id}/approval`,'POST',body,intent.id);await loadResult(result.playlist_id);approvalIntent.current=null;}
    catch(e){setError((e as Error).message);}finally{setApproving(false);}
  }
  const first=result?.items[0];
  const applied=!!result&&canonical(result.context.excluded_track_ids)===canonical(excluded?.excluded_track_ids);
  const approvedCurrent=!!result&&!changed&&!dirty&&applied&&result.approved_playlist_id===result.playlist_id;
  const status=busy?'새 선곡표를 준비하고 있어요.':weatherMismatch?'날씨가 변경됐어요 · 갱신 전 선곡표':changed||dirty||!applied&&result?'변경 사항 미반영 · 변경 전 결과':
    result?.approved_playlist_id===result?.playlist_id&&result?result.preview_only?'CSV 검증용 선곡표를 승인했어요.':'승인한 선곡표예요.':
    result?.preview_only?'실제 CSV 곡을 보여주는 검증용 선곡표예요.':result?'선곡표를 확인해 주세요.':effectiveMode==='OFF'?'지역 없이 취향으로 선곡표를 받아 보세요.':'지역을 선택하고 선곡표를 받아 보세요.';
  return <>
    <div inert={guide}>
      <Header showGuide={()=>setGuide(true)} isDemo={isDemo} musicSource={musicSource} weatherIsTest={weather?.is_test}/>
      <Banner placement="top" blocked={guide} onReady={()=>setAdContextReady(true)}/>
      <main className="public-main">
        <WeatherPanel region={choices.region_id} regions={regions}
          regionLoading={regionLoading} regionError={regionError} onRegionsRetry={()=>setRegionRetry(x=>x+1)}
          onRegion={id=>setChoices(c=>({...c,region_id:id}))} locked={locked} weather={weather} error={weatherError}
          onRetry={()=>setWeatherRetry(x=>x+1)} widget={widget} onGuide={()=>setGuide(true)} onHideWidget={()=>setWidget(false)}/>
        {error&&<div role="alert" className="notice error">{error}{jobIntent?
          <button onClick={()=>void generate(false,true)} disabled={locked}>같은 요청 다시 확인</button>:
          <button onClick={()=>{refreshed.current='';setWeatherRetry(x=>x+1);setInitRetry(x=>x+1);}} disabled={locked}>연결 다시 확인</button>}</div>}
        <div className="music-grid">
          <section className="selection card" aria-labelledby="selection-title" data-guide="selection">
            <h2 id="selection-title">음악 선택</h2>
            <fieldset disabled={locked}><legend>날씨 반영</legend><div className="radio-options weather-mode-options">
              <label><input type="radio" name="weather-influence" checked={effectiveMode==='ON'} disabled={!choices.region_id}
                onChange={()=>setChoices(c=>({...c,weather_influence_mode:'ON'}))}/>반영</label>
              <label><input type="radio" name="weather-influence" checked={effectiveMode==='OFF'}
                onChange={()=>setChoices(c=>({...c,weather_influence_mode:'OFF'}))}/>반영하지 않음</label>
            </div>{!choices.region_id&&<small>지역 미설정 · 날씨를 제외하고 선곡합니다.</small>}</fieldset>
            <fieldset disabled={locked}><legend>보컬</legend><div className="radio-options">
              {[['any','제한 없음'],['instrumental_only','연주곡만']].map(([value,label])=>
                <label key={value}><input type="radio" name="vocal" value={value} checked={choices.vocal_option===value}
                  onChange={()=>setChoices(c=>({...c,vocal_option:value}))}/>{label}</label>)}
            </div></fieldset>
            <fieldset disabled={locked}><legend>빠르기</legend><div className="radio-options tempo-options">
              {[['auto',effectiveMode==='ON'?'날씨에 맡기기':'제한 없음'],['slow','느린 곡 우선'],['fast','빠른 곡 우선']].map(([value,label])=>
                <label key={value}><input type="radio" name="tempo" value={value} checked={choices.tempo_preference===value}
                  onChange={()=>setChoices(c=>({...c,tempo_preference:value}))}/>{label}</label>)}
            </div></fieldset>
            <fieldset className="tag-fieldset" disabled={locked}><legend>테마 · 장르 <small>복수 선택 가능</small></legend>
              <TagPicker options={options} choices={choices} disabled={locked} onToggle={toggleOption}/>
            </fieldset>
            <div className="selection-bottom">
              <button className="primary" disabled={!contextReady||!choices.option_version||(effectiveMode==='ON'&&(!weather||weather.recommendation_ready===false))||locked||!!jobIntent}
                onClick={()=>void generate()}>{busy?'선곡표 준비 중…':'선곡표 받기'}</button>
            </div>
          </section>
          <section className="representative card" aria-labelledby="cover-title">
            <div className="cover-heading"><h2 id="cover-title">곡 · 앨범 이미지</h2>{!first?.cover_image_url&&<span className="badge">기본 이미지</span>}</div>
            <div className="cover-wrap"><Cover url={first?.cover_image_url}/></div>
            <h3>{first?.track_name||'오늘의 음악을 만나 보세요'}</h3>
            <p>{first?.artists_name||'선곡표를 받으면 첫 곡을 보여드려요.'}</p>
          </section>
          <section className="playlist card" aria-labelledby="playlist-title" data-guide="playlist">
            <div className="list-heading"><h2 id="playlist-title">{(result?.context.options.weather_influence_mode||effectiveMode)==='OFF'?'취향에 맞춘 선곡표':'날씨에 맞춘 선곡표'}</h2><span className="count">{result?result.items.length+'곡':'준비 전'}</span></div>
            <div aria-live="polite" className={'playlist-status'+(result&&!busy&&!changed&&!dirty&&applied&&result.approved_playlist_id!==result.playlist_id?' sr-only':'')}>{status}</div>
            {result&&!result.preview_only&&<p className="playlist-summary">{result.summary} <span className="badge">{result.generation_method==='RULE_BASED'?'기본 추천':'재설정'}</span></p>}
            {!result&&<div className="list-meta">{effectiveMode==='OFF'?'날씨와 관계없이 취향에 맞는 음악을 준비해 드려요.':'지역에 맞는 음악을 준비해 드려요.'}</div>}
            <ol className="tracks" aria-label="추천 곡 목록">{result?.items.map(track=>{
              const isExcluded=draft.includes(track.track_id);
              const reaction=feedback.feedback?.track_reactions.find(r=>r.track_id===track.track_id)?.value;
              const feedbackReady=!!feedback.feedback?.track_reactions.some(r=>r.track_id===track.track_id);
              return <li key={track.track_id} className={isExcluded?'excluded':''}>
                <Cover url={track.cover_image_url} small/>
                <div className="track-info"><strong title={track.track_name}>{track.track_name}</strong><span>{track.artists_name}{isExcluded?' · 제외됨':''}</span></div>
                  <div className="reactions">
                    <button aria-label={track.track_name+' 좋아요'} aria-pressed={reaction==='LIKE'}
                      disabled={!feedbackReady||feedback.pending.includes(track.track_id)}
                      onClick={()=>void feedback.save(track.track_id,reaction==='LIKE'?null:'LIKE')}><Icon name="thumb-up"/>좋아요</button>
                    <button aria-label={track.track_name+' 싫어요'} aria-pressed={reaction==='DISLIKE'}
                      disabled={!feedbackReady||feedback.pending.includes(track.track_id)}
                      onClick={()=>void feedback.save(track.track_id,reaction==='DISLIKE'?null:'DISLIKE')}><Icon name="thumb-down"/>싫어요</button>
                  </div>
                <button className="exclude" disabled={locked||!!saveError}
                  onClick={()=>void saveExclusions(isExcluded?draft.filter(id=>id!==track.track_id):[...draft,track.track_id])}>{isExcluded?'제외 취소':'제외'}</button>
              </li>;
            })||<li className="empty"><Icon name="music"/><h3>{effectiveMode==='OFF'?'취향에 어울리는 음악':'날씨에 어울리는 음악'}</h3><p>{effectiveMode==='OFF'?'지역 없이 선곡표를 받아 보세요.':'지역을 선택하고 선곡표를 받아 보세요.'}</p></li>}</ol>
            {draft.length>0&&<div className="excluded-list">
              <button aria-expanded={expanded} onClick={()=>setExpanded(!expanded)}>이번 제외 곡 {draft.length}개 · {expanded?'접기 ▴':'보기 ▾'}</button>
              {expanded&&draft.map(id=>{const track=excluded?.items.find(x=>x.track_id===id)||result?.items.find(x=>x.track_id===id);
                return <div key={id}>{track?.track_name||id} <button disabled={locked||!!saveError} onClick={()=>void saveExclusions(draft.filter(x=>x!==id))}>제외 취소</button></div>;})}
              <small>다음 선곡표를 요청하면 반영돼요.</small>
            </div>}
            {saving&&<p role="status" className="save-status">제외 설정 저장 중…</p>}
            {dirty&&!saving&&!saveError&&<button onClick={()=>void saveExclusions(draft)}>변경 저장</button>}
            {saveError&&<div role="alert" className="notice error">{saveError}
              <button disabled={locked} onClick={()=>void saveExclusions(draft,true)}>다시 저장</button>
              <button disabled={locked} onClick={async()=>{if(result){const ex=await api<Exclusions>('/api/playlist-families/'+result.family_id+'/exclusions').catch(()=>null);
                if(ex){setExcluded(ex);setSaveIntent(null);setSaveError('');}}}}>최신 목록 확인</button>
            </div>}
            {result&&<div className="rating">
              <div className="rating-heading"><strong>이 선곡표 만족도</strong><span className="badge">{feedback.feedback?.playlist_rating.value?feedback.feedback.playlist_rating.value+'점':'미평가'}</span></div>
              <div className="stars"><div className="star-options" role="radiogroup" aria-label="선곡표 별점" onKeyDown={event=>{
                if(!feedback.feedback||feedback.pending.includes('rating')||!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home','End'].includes(event.key))return;
                event.preventDefault();const value=Number((event.target as HTMLElement).dataset.rating)||1;
                const next=event.key==='Home'?1:event.key==='End'?5:((value-1+(['ArrowLeft','ArrowUp'].includes(event.key)?-1:1)+5)%5)+1;
                event.currentTarget.querySelector<HTMLButtonElement>('[data-rating="'+next+'"]')?.focus();void feedback.save('rating',next);
              }}>{[1,2,3,4,5].map(n=>
                <button key={n} role="radio" data-rating={n} aria-label={n+'점'} aria-checked={feedback.feedback?.playlist_rating.value===n}
                  tabIndex={(Number(feedback.feedback?.playlist_rating.value)||1)===n?0:-1}
                  disabled={!feedback.feedback||feedback.pending.includes('rating')} onClick={()=>void feedback.save('rating',n)}>{Number(feedback.feedback?.playlist_rating.value)>=n?'★':'☆'}</button>)}</div>
                <button className="rating-clear" onClick={()=>void feedback.save('rating',null)}
                  disabled={!feedback.feedback||feedback.pending.includes('rating')}>평가 취소</button>
              </div>
            </div>}
            {feedback.error&&<div role="alert" className="notice feedback-notice">{feedback.error}{feedback.retry&&<button onClick={()=>void feedback.retry?.()}>{feedback.retryLabel}</button>}</div>}
            <div className="playlist-actions">
              <button disabled={!canRegenerate||!!jobIntent} onClick={()=>void generate(true)}>다른 선곡표 요청</button>
              <button className="primary" disabled={!canApprove||!!jobIntent||approvedCurrent} onClick={()=>void approve()}>{approving?'승인 중…':approvedCurrent?'승인 완료':'이 선곡표 승인'}</button>
            </div>
            <small className="playlist-hint">{result?.preview_only?'CSV 검증용 결과입니다. 좋아요·싫어요·별점·제외·승인은 이 PC의 로컬 데이터에 저장돼요.':'조건을 바꾸면 새 선곡표를 받아 확인해 주세요.'}</small>
          </section>
        </div>
      </main>
      <Banner placement="bottom" blocked={guide} enabled={adContextReady}/>
    </div>
    {guide&&<Guide close={()=>setGuide(false)}/>}
  </>;
}
