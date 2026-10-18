import {useEffect,useRef,useState} from 'react';
import {api,canonical,key} from '../../shared/api';
import {Header} from '../../components/Header';
import {Icon,WeatherIcon} from '../../components/Icons';
type Menu={path:string;label:string};
type Me={authenticated:boolean;role?:string;allowed_menus:Menu[]};
function useMutationKeys(){
  const cache=useRef(new Map<string,string>());
  return (scope:string,body:unknown)=>{
    const signature=scope+':'+canonical(body);
    if(!cache.current.has(signature))cache.current.set(signature,key());
    return cache.current.get(signature)!;
  };
}
export function Login(){
  const [username,setUsername]=useState(''),[password,setPassword]=useState(''),[show,setShow]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
  useEffect(()=>{void api('/api/auth/me').catch(()=>setError('로그인 서비스 연결을 기다리고 있어요.'));},[]);
  return <><Header login/><main className="login-layout"><section className="card login-card" aria-labelledby="login-title">
    <div className="login-symbol"><WeatherIcon pty={0} sky={3}/><Icon name="music"/></div>
    <h1 id="login-title">로그인</h1><p className="login-description">계정으로 로그인해 주세요.</p>
    <form onSubmit={async e=>{
      e.preventDefault();setBusy(true);setError('');
      try{
        const response=await api<{role:string;landing_path:string;allowed_menus:Menu[]}>('/api/auth/login','POST',{username,password});
        if(response.role!=='ADMIN'||!['/admin/ads','/admin/music','/admin/music/youtube','/admin/feedback/exclusions'].includes(response.landing_path)||!response.allowed_menus.some(menu=>menu.path===response.landing_path))throw new Error('계정 권한을 확인해 주세요.');
        location.assign(response.landing_path);
      }catch(error){setError((error as Error).message);}
      finally{setBusy(false);setPassword('');}
    }}>
      <label htmlFor="username">아이디</label>
      <input id="username" autoComplete="username" placeholder="아이디를 입력해 주세요" required value={username}
        onChange={e=>setUsername(e.target.value)} disabled={busy}/>
      <label htmlFor="password">비밀번호</label>
      <div className="password-field"><input id="password" type={show?'text':'password'} autoComplete="current-password"
        placeholder="비밀번호를 입력해 주세요" required value={password} onChange={e=>setPassword(e.target.value)} disabled={busy}/>
        <button type="button" aria-label={show?'비밀번호 숨기기':'비밀번호 표시'} aria-pressed={show} disabled={busy}
          onClick={()=>setShow(value=>!value)}><Icon name={show?'eye-off':'eye'}/></button>
      </div>
      {error&&<p className="notice error" role="alert">{error}</p>}
      <button className="primary" disabled={busy}>{busy?'로그인 중…':'로그인'}</button>
    </form>
    <a className="guest-link" href="/"><Icon name="home"/>로그인 없이 선곡 이용하기</a>
    <p className="login-caption">관리자 계정의 권한에 맞는 관리 페이지로 이동합니다.</p>
  </section></main></>;
}
function ReviewEditor({row,onDone}:{row:Record<string,unknown>;onDone:()=>void}){
  const mutationKey=useMutationKeys();
  const [review,setReview]=useState(''),[mood,setMood]=useState(''),[instrument,setInstrument]=useState(''),[reason,setReason]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  const id=String(row.track_id);
  return <details><summary>{String(row.track_name||id)} · {String(row.artists_name||'')}</summary><form onSubmit={e=>e.preventDefault()}><label>보컬 검수<select value={review} onChange={e=>setReview(e.target.value)}><option value="">변경 안 함</option><option value="true">보컬 없음</option><option value="false">보컬 있음</option><option value="clear">확정 검수 해제</option></select></label><label>mood 코드 (세미콜론 구분)<input value={mood} onChange={e=>setMood(e.target.value)}/></label><label>주 악기 코드<input value={instrument} onChange={e=>setInstrument(e.target.value)}/></label><label>검수 근거<textarea required value={reason} onChange={e=>setReason(e.target.value)}/></label><div className="segments">{['draft','approved'].map(status=><button key={status} disabled={busy||!reason} onClick={async()=>{setBusy(true);setError('');try{await api(`/api/admin/music/${encodeURIComponent(id)}/reviews`,'POST',{
        expected_revision:row.revision,review_status:status,reason,
        ...(review?{instrumental_review_value:review==='clear'?null:review==='true'}:{}),
        ...(mood?{mood_codes:mood.split(';').filter(Boolean)}:{}),...(instrument?{instrument_codes:instrument.split(';').filter(Boolean)}:{})},mutationKey(id,{revision:row.revision,status,reason,review,mood,instrument}));onDone();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}}>{status==='approved'?'승인':'보류'}</button>)}</div>{error&&<p role="alert">{error}</p>}</form></details>;
}
export function AdminPage({path}:{path:string}){
  const mutationKey=useMutationKeys();
  const [me,setMe]=useState<Me|null>(null),[error,setError]=useState(''),[loading,setLoading]=useState(false),[rows,setRows]=useState<Record<string,unknown>[]>([]),[readiness,setReadiness]=useState<unknown>(null),[detail,setDetail]=useState<unknown>(null),[next,setNext]=useState<string|null>(null),[asOf,setAsOf]=useState<string|null>(null),[retry,setRetry]=useState(0);
  const [filters,setFilters]=useState({from:'',to:'',track_id:'',selected_theme_code:'',selected_genre_code:'',track_theme_code:'',track_genre_code:'',action:'',state:''});
  const [catalogVersion,setCatalogVersion]=useState(''),[sourceRef,setSourceRef]=useState(''),[sourceHash,setSourceHash]=useState('');
  const queryRef=useRef('');const [file,setFile]=useState<File|null>(null),[schema,setSchema]=useState('spotify-raw20-v1'),[importResult,setImportResult]=useState<unknown>(null);
  const music=path==='/admin/music';const allowed=me?.authenticated&&me.role==='ADMIN'&&me.allowed_menus?.some(m=>m.path===path);
  useEffect(()=>{api<Me>('/api/auth/me').then(setMe).catch(e=>setError(e.message));},[retry]);
  async function load(cursor?:string,signal?:AbortSignal){
    setLoading(true);setError('');
    try{
      const qs=cursor?new URLSearchParams(queryRef.current):new URLSearchParams(Object.entries(filters).filter(([,v])=>v));
      if(cursor){qs.set('cursor',cursor);if(asOf)qs.set('as_of',asOf);}else queryRef.current=qs.toString();
      const data=await api<{items:Record<string,unknown>[];next_cursor:string|null;as_of:string}>(music?'/api/admin/music/reviews':`/api/admin/feedback/exclusions?${qs}`,'GET',undefined,undefined,signal);
      setRows(data.items);setNext(data.next_cursor);setAsOf(data.as_of);
      if(music)setReadiness(await api('/api/admin/music/readiness','GET',undefined,undefined,signal));
    }catch(e){if(!signal?.aborted)setError((e as Error).message);}finally{setLoading(false);}
  }
  useEffect(()=>{if(!allowed)return;const controller=new AbortController();void load(undefined,controller.signal);return()=>controller.abort();},[allowed]);
  return <><header className="header"><a className="brand" href="/">café<span>운영 관리</span></a><nav>{me?.allowed_menus?.map(m=><a key={m.path} href={m.path}>{m.label}</a>)}{me?.authenticated&&<button onClick={()=>void api('/api/auth/logout','POST',{}).then(()=>location.assign('/login')).catch(e=>setError(e.message))}>로그아웃</button>}</nav></header><main className="admin"><span className="eyebrow">ADMIN WORKSPACE</span><h1>{music?'음악 등록 · 검수':'곡 제외 피드백 이력'}</h1>{error&&<p className="notice error" role="alert">{error}<button onClick={()=>setRetry(x=>x+1)}>연결 다시 확인</button></p>}
    {!allowed?<p>관리자 인증과 해당 메뉴의 권한 확인이 필요합니다. <a href="/login">로그인</a></p>:<>
      {music?<section className="card"><h2>CSV 일괄 등록</h2><p>등록 후 검수·카탈로그 발행을 별도로 진행합니다.</p><label>입력 형식<select value={schema} onChange={e=>setSchema(e.target.value)}><option value="spotify-raw20-v1">원본 20개＋행 인덱스</option><option value="music-normalized19-v1">변환 결과 19개</option></select></label><input type="file" accept=".csv,text/csv" onChange={e=>setFile(e.target.files?.[0]||null)}/><button disabled={!file||loading} onClick={async()=>{
        if(!file)return;setLoading(true);setError('');
        try{
          const bytes=await file.arrayBuffer();const hash=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(x=>x.toString(16).padStart(2,'0')).join('');
          const form=new FormData();form.append('file',file);form.append('source_schema_version',schema);form.append('source_sha256',hash);
          const token=document.cookie.split('; ').find(x=>x.startsWith('csrftoken='))?.slice(10)||'';
          const response=await fetch('/api/admin/music/imports',{method:'POST',credentials:'same-origin',headers:{'X-CSRFToken':token,'Idempotency-Key':mutationKey('import',{hash,schema})},body:form});
          const data=await response.json();if(!response.ok)throw new Error(data.message||'등록에 실패했어요.');setImportResult(data);setSourceRef(data.source_ref);setSourceHash(data.source_sha256);await load();
        }catch(e){setError((e as Error).message);}finally{setLoading(false);}
      }}>등록 검사</button>{importResult!=null&&<pre>{JSON.stringify(importResult,null,2)}</pre>}<section><h3>승인 카탈로그 발행</h3><label>카탈로그 버전<input value={catalogVersion} onChange={e=>setCatalogVersion(e.target.value)}/></label><label>등록 원본 참조<input value={sourceRef} onChange={e=>setSourceRef(e.target.value)}/></label><label>원본 SHA-256<input value={sourceHash} onChange={e=>setSourceHash(e.target.value)}/></label><button disabled={loading||!catalogVersion||!sourceRef||!sourceHash} onClick={async()=>{setLoading(true);try{setReadiness(await api('/api/admin/music/catalogs','POST',{version:catalogVersion,source_ref:sourceRef,source_sha256:sourceHash},mutationKey('publish',{catalogVersion,sourceRef,sourceHash})));await load();}catch(e){setError((e as Error).message);}finally{setLoading(false);}}}>승인된 곡만 새 버전 발행</button></section></section>:<form className="filter-form" onSubmit={e=>{e.preventDefault();void load();}}>
        {Object.entries(filters).map(([k,v])=><label key={k}>{{from:'시작일 (KST)',to:'종료일 · 미포함 (KST)',track_id:'곡 ID',selected_theme_code:'당시 선택 테마',selected_genre_code:'당시 선택 장르',track_theme_code:'곡 테마',track_genre_code:'곡 장르',action:'제외 / 취소',state:'상태'}[k]}<input type={k==='from'||k==='to'?'date':'text'} value={v} onChange={e=>setFilters(f=>({...f,[k]:e.target.value}))}/></label>)}<button disabled={loading}>검색</button>
      </form>}
      {loading&&<p role="status">불러오는 중…</p>}
      {music?<><section className="card"><h2>검수 대기</h2>{rows.map(r=><ReviewEditor key={String(r.track_id)} row={r} onDone={()=>void load()}/>)}</section><section className="card"><h2>음악 준비 현황</h2><pre>{JSON.stringify(readiness,null,2)}</pre></section></>:<section className="card"><p>조회 기준: {asOf?new Date(asOf).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'}):'—'} · 읽기 전용</p><div className="table-scroll"><table><thead><tr><th>발생 시각</th><th>곡</th><th>행동</th><th>당시 선택</th><th>곡 태그</th><th>상세</th></tr></thead><tbody>{rows.map(r=><tr key={String(r.event_id)}><td>{String(r.occurred_at)}</td><td>{String(r.track_name)}</td><td>{String(r.event_type)}</td><td>{JSON.stringify(r.selected_theme_codes)} {JSON.stringify(r.selected_genre_codes)}</td><td>{JSON.stringify(r.track_theme_codes)} {JSON.stringify(r.track_genre_codes)}</td><td><button onClick={async()=>{try{setDetail(await api(`/api/admin/feedback/exclusions/${encodeURIComponent(String(r.event_id))}`));}catch(e){setError((e as Error).message);}}}>보기</button></td></tr>)}</tbody></table></div>{!rows.length&&!loading&&<p>조회된 이력이 없습니다.</p>}{next&&<button disabled={loading} onClick={()=>void load(next)}>다음 목록 →</button>}</section>}
      {detail!=null&&<section className="card"><h2>당시 조건 · 곡 · 취소 연결</h2><pre>{JSON.stringify(detail,null,2)}</pre><button onClick={()=>setDetail(null)}>상세 닫기</button></section>}
    </>}</main></>;
}
