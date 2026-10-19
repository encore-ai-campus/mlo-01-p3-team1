import {useEffect,useRef,useState} from 'react';
import {api} from '../../shared/api';
import {AdminLayout,Badge,Metrics,NoAdminAccess,number,useAdminMutationKey,useAdminSession,useMusicLabels} from './AdminLayout';

type MusicRow={track_id:string;track_name:string;artists_name:string;revision:number;review_status:string;instrumental_review_value:boolean|null};
type Readiness={registered_count:number;approved_review_count:number;common_eligible_count:number;weather_counts:Record<string,number>;catalog_versions:{version:string;ready:boolean;is_test:boolean}[]};
function MusicReview({row,onDone}:{row:MusicRow;onDone:()=>void}){
  const mutationKey=useAdminMutationKey(),{options}=useMusicLabels();
  const [vocal,setVocal]=useState(''),[themes,setThemes]=useState<string[]>([]),[themesChanged,setThemesChanged]=useState(false),[instrument,setInstrument]=useState(''),[reason,setReason]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
  async function save(status:string){
    setBusy(true);setError('');
    const body={expected_revision:row.revision,review_status:status,reason:reason.trim(),
      ...(vocal?{instrumental_review_value:vocal==='clear'?null:vocal==='true'}:{}),
      ...(themesChanged?{mood_codes:themes}:{}),...(instrument.trim()?{instrument_codes:instrument.split(';').map(x=>x.trim()).filter(Boolean)}:{})};
    try{await api(`/api/admin/music/${encodeURIComponent(row.track_id)}/reviews`,'POST',body,mutationKey(row.track_id,body));onDone();}catch(e){setError((e as Error).message);}finally{setBusy(false);}
  }
  return <section className="admin-panel admin-detail-panel"><h2>음악 검수</h2><div className="admin-selected-track"><img src="/default-cover.svg" alt=""/><div><strong>{row.track_name}</strong><p>{row.artists_name}</p></div></div>
    <form className="admin-form" onSubmit={e=>e.preventDefault()}><label>보컬 검수<select disabled={busy} value={vocal} onChange={e=>setVocal(e.target.value)}><option value="">변경 안 함</option><option value="true">보컬 없음</option><option value="false">보컬 있음</option><option value="clear">확정 검수 해제</option></select></label>
      <div><p className="admin-muted">테마 검수 · 선택 시 기존 태그를 교체합니다.</p><div className="admin-chip-options">{options.filter(o=>o.type==='theme'&&o.enabled).map(o=><button disabled={busy} type="button" key={o.code} aria-pressed={themes.includes(o.code)} onClick={()=>{setThemesChanged(true);setThemes(current=>current.includes(o.code)?current.filter(x=>x!==o.code):[...current,o.code]);}}>{o.label}</button>)}</div></div>
      <details><summary>추가 검수 항목</summary><label>주 악기 코드 · 세미콜론 구분<input disabled={busy} value={instrument} onChange={e=>setInstrument(e.target.value)} placeholder="입력하지 않으면 변경하지 않습니다"/></label></details>
      <label>검수 근거<textarea required disabled={busy} value={reason} onChange={e=>setReason(e.target.value)} placeholder="검수 판단의 근거를 입력해 주세요."/></label>
      {error&&<p className="notice error" role="alert">{error}</p>}<div className="admin-actions equal"><button type="button" disabled={busy||!reason.trim()} onClick={()=>void save('draft')}>보류</button><button type="button" className="primary" disabled={busy||!reason.trim()} onClick={()=>void save('approved')}>{busy?'저장 중…':'승인'}</button></div>
    </form></section>;
}
export function MusicAdmin(){
  const path='/admin/music',session=useAdminSession(path),mutationKey=useAdminMutationKey();
  const [rows,setRows]=useState<MusicRow[]>([]),[readiness,setReadiness]=useState<Readiness|null>(null),[readinessError,setReadinessError]=useState(''),[loading,setLoading]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
  const [status,setStatus]=useState(''),[search,setSearch]=useState(''),[selected,setSelected]=useState<MusicRow|null>(null),[next,setNext]=useState<string|null>(null),[pages,setPages]=useState<string[]>(['']),[refresh,setRefresh]=useState(0);
  const [file,setFile]=useState<File|null>(null),[schema,setSchema]=useState('spotify-raw20-v1'),[busy,setBusy]=useState(false),[importResult,setImportResult]=useState<Record<string,unknown>|null>(null);
  const [version,setVersion]=useState(''),[source,setSource]=useState(''),[hash,setHash]=useState('');
  const upload=useRef<HTMLElement>(null),cursor=pages[pages.length-1];
  useEffect(()=>{if(!session.allowed)return;const c=new AbortController();setLoading(true);setError('');setSelected(null);
    const params=new URLSearchParams({...status?{status}:{},...cursor?{cursor}:{}});
    void api<{items:MusicRow[];next_cursor:string|null}>('/api/admin/music/reviews?'+params,'GET',undefined,undefined,c.signal).then(data=>{setRows(data.items);setNext(data.next_cursor);setSelected(data.items[0]||null);}).catch(e=>{if(!c.signal.aborted)setError(e.message);}).finally(()=>{if(!c.signal.aborted)setLoading(false);});return()=>c.abort();
  },[session.allowed,status,cursor,refresh]);
  useEffect(()=>{if(!session.allowed)return;const c=new AbortController();setReadinessError('');void api<Readiness>('/api/admin/music/readiness','GET',undefined,undefined,c.signal).then(setReadiness).catch(e=>{if(!c.signal.aborted)setReadinessError(e.message);});return()=>c.abort();},[session.allowed,refresh]);
  const reload=()=>setRefresh(x=>x+1);
  async function importCsv(){
    if(!file)return;setBusy(true);setError('');setNotice('');
    try{const bytes=await file.arrayBuffer(),digest=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(x=>x.toString(16).padStart(2,'0')).join('');
      const form=new FormData();form.append('file',file);form.append('source_schema_version',schema);form.append('source_sha256',digest);
      const token=document.cookie.split('; ').find(x=>x.startsWith('csrftoken='))?.slice(10)||'';
      const response=await fetch('/api/admin/music/imports',{method:'POST',credentials:'same-origin',headers:{'X-CSRFToken':token,'Idempotency-Key':mutationKey('import',{digest,schema})},body:form});
      const data=await response.json();if(!response.ok)throw new Error(data.message||'등록에 실패했습니다.');setImportResult(data);setSource(data.source_ref||'');setHash(data.source_sha256||'');setNotice('CSV 등록 결과를 확인해 주세요. 검수와 카탈로그 발행은 별도로 진행합니다.');reload();
    }catch(e){setError((e as Error).message);}finally{setBusy(false);}
  }
  async function publish(){setBusy(true);setError('');setNotice('');const body={version:version.trim(),source_ref:source.trim(),source_sha256:hash.trim()};try{await api('/api/admin/music/catalogs','POST',body,mutationKey('publish',body));setNotice('승인된 곡의 새 카탈로그를 발행했습니다.');reload();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
  const visible=rows.filter(row=>`${row.track_name} ${row.artists_name}`.toLocaleLowerCase().includes(search.toLocaleLowerCase()));
  return <AdminLayout me={session.me} path={path} title="음악 관리" subtitle="음악을 등록하고 검수한 뒤 추천 카탈로그로 발행하세요." error={session.error||error} onRetry={()=>{session.retry();reload();}}>
    {!session.allowed?<NoAdminAccess loaded={!!session.me}/>:<>
      <Metrics items={[{label:'등록된 음악',value:number(readiness?.registered_count),icon:'♫'},{label:'검수 승인',value:number(readiness?.approved_review_count),icon:'✓',tone:'green'},{label:'추천 적격 음악',value:number(readiness?.common_eligible_count),icon:'♬'},{label:'발행 카탈로그',value:readiness?number(readiness.catalog_versions.filter(x=>x.ready).length)+'개':'—',icon:'▤'}]}/>
      {notice&&<p className="notice" role="status">{notice}</p>}{readinessError&&<p className="notice error" role="alert">준비 현황: {readinessError} <button onClick={reload}>다시 확인</button></p>}
      <div className="admin-workspace"><div className="admin-stack"><section className="admin-panel"><div className="admin-panel-heading"><h2>음악 목록</h2><button className="primary" onClick={()=>{upload.current?.scrollIntoView({behavior:'smooth',block:'center'});upload.current?.querySelector('input')?.focus();}}>＋ CSV 등록</button></div>
        <div className="admin-searchbar"><input aria-label="현재 음악 목록 검색" placeholder="현재 페이지의 곡명 또는 아티스트 검색" value={search} onChange={e=>setSearch(e.target.value)}/><button disabled={loading} onClick={reload}>새로고침</button></div>
        <div className="segments" aria-label="음악 검수 상태">{[['','전체'],['draft','검수 대기'],['approved','승인']].map(([value,label])=><button disabled={loading} key={value} aria-pressed={status===value} onClick={()=>{setStatus(value);setPages(['']);}}>{label}</button>)}</div>
        <div className="admin-table-scroll"><table className="admin-table"><thead><tr><th>곡명 · 아티스트</th><th>보컬 검수</th><th>검수 상태</th><th>관리</th></tr></thead><tbody>{visible.map(row=><tr className={selected?.track_id===row.track_id?'selected':''} key={row.track_id}><td><div className="admin-track-cell"><img src="/default-cover.svg" alt=""/><div><strong>{row.track_name}</strong><small>{row.artists_name}</small></div></div></td><td><Badge tone="muted">{row.instrumental_review_value===true?'보컬 없음':row.instrumental_review_value===false?'보컬 있음':'미검수'}</Badge></td><td><Badge tone={row.review_status==='approved'?'green':'amber'}>{row.review_status==='approved'?'승인':'검수 대기'}</Badge></td><td><button onClick={()=>setSelected(row)} aria-label={`${row.track_name} 검수`}>검수</button></td></tr>)}</tbody></table></div>
        {(loading||!visible.length)&&<p className="admin-empty" role="status">{loading?'음악을 불러오는 중입니다.':'현재 목록에 해당하는 음악이 없습니다.'}</p>}
        <div className="admin-pagination"><span>{pages.length}페이지 · 현재 목록 {visible.length}곡</span><div className="admin-actions"><button disabled={loading||pages.length<=1} onClick={()=>setPages(x=>x.slice(0,-1))}>이전</button><button disabled={loading||!next} onClick={()=>next&&setPages(x=>[...x,next])}>다음</button></div></div>
      </section><section className="admin-panel" ref={upload}><h2>CSV 일괄 등록</h2><div className="admin-form"><label>입력 형식<select value={schema} disabled={busy} onChange={e=>setSchema(e.target.value)}><option value="spotify-raw20-v1">Spotify 원본 CSV</option><option value="music-normalized19-v1">변환 결과 CSV</option></select></label><label className="admin-upload-box">CSV 파일을 선택해 주세요.<input type="file" accept=".csv,text/csv" disabled={busy} onChange={e=>setFile(e.target.files?.[0]||null)}/></label><button className="primary" disabled={busy||!file} onClick={()=>void importCsv()}>{busy?'처리 중…':'등록 검사'}</button></div>
        {importResult&&<div className="admin-inline-note" role="status">등록 요청을 처리했습니다. {typeof importResult.source_ref==='string'&&<span>원본 참조: {importResult.source_ref}</span>}<details><summary>상세 등록 결과</summary><pre>{JSON.stringify(importResult,null,2)}</pre></details></div>}
      </section></div><div className="admin-stack">{selected?<MusicReview key={selected.track_id+':'+selected.revision} row={selected} onDone={reload}/>:<section className="admin-panel admin-empty">목록에서 검수할 음악을 선택해 주세요.</section>}
      <section className="admin-panel"><h2>카탈로그 발행</h2><p className="admin-muted">승인된 곡만 새 버전으로 발행합니다.</p><form className="admin-form" onSubmit={e=>{e.preventDefault();void publish();}}><label>카탈로그 버전<input value={version} disabled={busy} required onChange={e=>setVersion(e.target.value)} placeholder="새 버전명"/></label><details><summary>등록 원본 정보</summary><div className="admin-form"><label>등록 원본 참조<input value={source} disabled={busy} onChange={e=>setSource(e.target.value)}/></label><label>원본 SHA-256<input value={hash} disabled={busy} onChange={e=>setHash(e.target.value)}/></label></div></details><button className="primary" disabled={busy||!version.trim()||!source.trim()||!hash.trim()}>새 카탈로그 발행</button></form>
      <ul className="admin-catalog-list">{readiness?.catalog_versions.map(item=><li key={item.version}><span>{item.version}{item.is_test?' · 테스트':''}</span><Badge tone={item.ready?'green':'amber'}>{item.ready?'준비 완료':'준비 대기'}</Badge></li>)}</ul>
      </section></div></div>
    </>}
  </AdminLayout>;
}
