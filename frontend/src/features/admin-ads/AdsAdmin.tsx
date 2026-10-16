import {useEffect,useRef,useState} from 'react';
import {api,canonical,key} from '../../shared/api';
import {Icon} from '../../components/Icons';

type Measurement={status?:string;impressions:number|null;clicks:number|null;as_of?:string|null;is_stale?:boolean};
type Ad={ad_id:string;title:string;asset_id:string;link_url:string;placement:'top'|'bottom';starts_at:string;ends_at:string;
  priority:number;daily_budget_tokens:number|null;total_budget_tokens:number|null;version:number;paused:boolean;
  status:'RESERVED'|'ACTIVE'|'ENDED'|'STOPPED';measurement?:Measurement};
type Summary={counts:Partial<Record<Ad['status'],number>>;measurement:Measurement;evaluated_at:string};
type Me={authenticated:boolean;role:string;allowed_menus:{path:string;label:string}[]};
const empty={title:'',asset_id:'',link_url:'',placement:'top' as 'top'|'bottom',starts_at:'',ends_at:'',priority:'1',daily_budget_tokens:'',total_budget_tokens:''};
const statusNames={ACTIVE:'게시 중',RESERVED:'예약',ENDED:'종료',STOPPED:'중단'};
const kst=(value:string)=>new Date(value).toLocaleString('sv-SE',{timeZone:'Asia/Seoul'}).replace(' ','T').slice(0,16);
const date=(value:string)=>kst(value).slice(0,10).replaceAll('-','.');
const utc=(value:string)=>new Date(value+(value.length===16?':00':'')+'+09:00').toISOString();
const count=(value:number|null|undefined)=>value===null||value===undefined?'연동 대기':value.toLocaleString('ko-KR');
const assetUrl=(id:string)=>'/api/admin/ad-assets/'+encodeURIComponent(id);

export function AdsAdmin(){
  const [me,setMe]=useState<Me|null>(null),[rows,setRows]=useState<Ad[]>([]),[summary,setSummary]=useState<Summary|null>(null);
  const [form,setForm]=useState(empty),[editing,setEditing]=useState<Ad|null>(null),[file,setFile]=useState<File|null>(null);
  const [fileUrl,setFileUrl]=useState(''),[previewAsset,setPreviewAsset]=useState<{asset_id:string;title:string;placement:'top'|'bottom'}|null>(null);
  const [previewPlacement,setPreviewPlacement]=useState<'top'|'bottom'>('top'),[previewDevice,setPreviewDevice]=useState<'pc'|'mobile'>('pc');
  const [filters,setFilters]=useState({placement:'',status:''}),[next,setNext]=useState<string|null>(null);
  const [error,setError]=useState(''),[busy,setBusy]=useState(false),[loading,setLoading]=useState(false),[notice,setNotice]=useState('');
  const intent=useRef(new Map<string,string>()),formRef=useRef<HTMLElement>(null),loadGeneration=useRef(0);
  const allowed=me?.authenticated&&me.role==='ADMIN'&&me.allowed_menus.some(x=>x.path==='/admin/ads');
  function mutationKey(scope:string,body:unknown){
    const signature=scope+':'+canonical(body);
    if(!intent.current.has(signature))intent.current.set(signature,key());
    return intent.current.get(signature)!;
  }
  async function load(cursor?:string){
    const generation=++loadGeneration.current;setLoading(true);setError('');
    try{
      const query=new URLSearchParams(Object.entries(filters).filter(([,value])=>value));
      if(cursor)query.set('cursor',cursor);
      const [data,stats]=await Promise.all([
        api<{items:Ad[];next_cursor:string|null}>('/api/admin/ads?'+query),api<Summary>('/api/admin/ads/summary')]);
      if(generation!==loadGeneration.current)return;
      setRows(data.items);setNext(data.next_cursor);setSummary(stats);
    }catch(error){if(generation===loadGeneration.current)setError((error as Error).message);}
    finally{if(generation===loadGeneration.current)setLoading(false);}
  }
  useEffect(()=>{void api<Me>('/api/auth/me').then(setMe).catch(error=>setError(error.message));},[]);
  useEffect(()=>{if(allowed)void load();return()=>{loadGeneration.current++;};},[allowed,filters.placement,filters.status]);
  useEffect(()=>{
    if(!file){setFileUrl('');return;}
    const url=URL.createObjectURL(file);setFileUrl(url);return()=>URL.revokeObjectURL(url);
  },[file]);
  async function upload(){
    if(!file)return form.asset_id;
    if(file.size>2_000_000)throw new Error('이미지는 최대 2MB입니다.');
    const bytes=await file.arrayBuffer();const hash=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(x=>x.toString(16).padStart(2,'0')).join('');
    const body=new FormData();body.append('image',file);
    const token=document.cookie.split('; ').find(x=>x.startsWith('csrftoken='))?.slice(10)||'';
    const response=await fetch('/api/admin/ad-assets',{method:'POST',credentials:'same-origin',
      headers:{'X-CSRFToken':token,'Idempotency-Key':mutationKey('asset',hash)},body});
    const data=await response.json();if(!response.ok)throw new Error(data.message||'이미지 등록에 실패했습니다.');
    setForm(previous=>({...previous,asset_id:data.asset_id}));setFile(null);return data.asset_id as string;
  }
  async function submit(previewOnly=false){
    setBusy(true);setError('');setNotice('');
    try{
      if(!form.title.trim()||!form.starts_at||!form.ends_at||!form.link_url)throw new Error('제목·이동 링크·게시 기간을 입력해 주세요.');
      if(!/^https:\/\//.test(form.link_url))throw new Error('이동 링크는 HTTPS 주소여야 합니다.');
      if(!form.priority.trim()||!Number.isSafeInteger(Number(form.priority)))throw new Error('우선순위는 정수로 입력해 주세요.');
      if(!!form.daily_budget_tokens!==!!form.total_budget_tokens)throw new Error('예산은 일일·전체 한도를 함께 입력해 주세요.');
      const asset=await upload();if(!asset)throw new Error('배너 이미지를 선택해 주세요.');
      const body={title:form.title,asset_id:asset,link_url:form.link_url,placement:form.placement,
        starts_at:utc(form.starts_at),ends_at:utc(form.ends_at),priority:Number(form.priority),
        ...(form.daily_budget_tokens?{daily_budget_tokens:Number(form.daily_budget_tokens),total_budget_tokens:Number(form.total_budget_tokens)}:{})};
      if(previewOnly){
        const preview=await api<{asset_id:string;title:string;placement:'top'|'bottom'}>('/api/admin/ads/preview','POST',body);
        setPreviewAsset(preview);setPreviewPlacement(preview.placement);setNotice('미리보기를 갱신했습니다.');return;
      }
      const path=editing?'/api/admin/ads/'+encodeURIComponent(editing.ad_id):'/api/admin/ads';
      const payload=editing?{...body,version:editing.version}:body;
      await api<Ad>(path,editing?'PUT':'POST',payload,mutationKey(path,payload));
      setForm(empty);setEditing(null);setFile(null);setNotice(editing?'광고를 수정했습니다.':'광고를 등록했습니다.');await load();
    }catch(error){setError((error as Error).message);}finally{setBusy(false);}
  }
  function edit(ad:Ad){
    setEditing(ad);setFile(null);setNotice('');setPreviewAsset(ad);setPreviewPlacement(ad.placement);
    setForm({title:ad.title,asset_id:ad.asset_id,link_url:ad.link_url,placement:ad.placement,
      starts_at:kst(ad.starts_at),ends_at:kst(ad.ends_at),priority:String(ad.priority),
      daily_budget_tokens:ad.daily_budget_tokens===null?'':String(ad.daily_budget_tokens),total_budget_tokens:ad.total_budget_tokens===null?'':String(ad.total_budget_tokens)});
  }
  async function stop(ad:Ad){
    setBusy(true);setError('');setNotice('');
    const body={version:ad.version},path='/api/admin/ads/'+encodeURIComponent(ad.ad_id)+'/stop';
    try{
      const updated=await api<Ad>(path,'POST',body,mutationKey(path,body));
      if(editing?.ad_id===ad.ad_id)edit(updated);
      setNotice('광고 게시를 중단했습니다.');await load();
    }catch(error){setError((error as Error).message);}finally{setBusy(false);}
  }
  const shownPreview=previewAsset?.placement===previewPlacement?previewAsset:rows.find(ad=>ad.placement===previewPlacement);
  const selectedImage=fileUrl||(form.asset_id?assetUrl(form.asset_id):'');
  return <>
    <header className="header ads-header"><a className="brand" href="/">날씨 기반 <span>음악 선곡</span></a><span className="ads-admin-badge">관리자</span>
      <nav>{me?.allowed_menus.map(item=><a key={item.path} href={item.path} aria-current={item.path==='/admin/ads'?'page':undefined}>{item.label}</a>)}
        <span className="ads-account">관리자 계정</span>{me?.authenticated&&<button onClick={()=>void api('/api/auth/logout','POST',{}).then(()=>location.assign('/login')).catch(error=>setError(error.message))}>로그아웃</button>}</nav>
    </header>
    <main className="admin ads-admin"><h1>광고 관리</h1><p className="ads-subtitle">상·하단 배너 게시 상태를 관리하세요.</p>
      {error&&<p role="alert" className="notice error">{error} <button disabled={busy||loading} onClick={()=>void load()}>다시 확인</button></p>}
      {notice&&<p role="status" className="notice">{notice}</p>}
      {!allowed?<p>광고 관리 권한을 확인해 주세요. <a href="/login">로그인</a></p>:<>
        <section className="ads-metrics" aria-label="광고 요약">
          {[{title:'게시 중',value:summary?.counts.ACTIVE,icon:'▶',kind:'active'},
            {title:'예약',value:summary?.counts.RESERVED,icon:'◷',kind:'reserved'},
            {title:'오늘 노출',value:summary?.measurement.impressions,icon:'eye',kind:'impressions'},
            {title:'오늘 클릭',value:summary?.measurement.clicks,icon:'↖',kind:'clicks'}].map(item=><article key={item.title} className="card ads-metric">
              <span className={'ads-metric-icon '+item.kind}>{item.icon==='eye'?<Icon name="eye"/>:item.icon}</span>
              <div><h2>{item.title}</h2><strong>{count(item.value)}{item.value!==undefined&&item.value!==null&&['active','reserved'].includes(item.kind)?'개':''}</strong></div>
            </article>)}
        </section>
        {summary?.measurement.as_of&&<p className="ads-stats-basis">집계 기준 {kst(summary.measurement.as_of).replace('T',' ')} KST · 5분 주기{summary.measurement.is_stale?' · 집계 지연':''}</p>}
        <div className="ads-workspace"><div className="ads-left">
          <section className="card ads-list-panel"><h2>광고 목록</h2><div className="ads-list-tools">
            <div className="segments" aria-label="광고 위치 필터">{[['','전체'],['top','상단'],['bottom','하단']].map(([value,label])=><button key={value} disabled={busy} aria-pressed={filters.placement===value} onClick={()=>setFilters({...filters,placement:value})}>{label}</button>)}</div>
            <label className="ads-status-filter"><span className="sr-only">광고 상태</span><select aria-label="광고 상태" disabled={busy} value={filters.status} onChange={event=>setFilters({...filters,status:event.target.value})}><option value="">전체 상태</option>{Object.entries(statusNames).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
            <button className="primary" disabled={busy} onClick={()=>{setEditing(null);setForm(empty);setFile(null);setNotice('');formRef.current?.querySelector<HTMLInputElement>('input')?.focus();}}>＋ 새 광고 등록</button>
          </div>
          <div className="table-scroll"><table className="ads-table"><thead><tr><th>제목</th><th>위치</th><th>상태</th><th>게시 기간</th><th>누적 노출</th><th>누적 클릭</th><th><span className="sr-only">광고 관리</span></th></tr></thead>
            <tbody>{rows.map(ad=><tr key={ad.ad_id} className={editing?.ad_id===ad.ad_id?'selected':''}>
              <td><div className="ads-title-cell"><img src={assetUrl(ad.asset_id)} alt=""/><strong>{ad.title}</strong></div></td>
              <td>{ad.placement==='top'?'상단':'하단'}</td><td><span className={'ads-status '+ad.status}>● {statusNames[ad.status]}</span></td>
              <td className="ads-period">{date(ad.starts_at)} ~ {date(ad.ends_at)}</td><td>{count(ad.measurement?.impressions)}</td><td>{count(ad.measurement?.clicks)}</td>
              <td><div className="ads-row-actions"><button disabled={busy} onClick={()=>edit(ad)}>✎ 수정</button><button disabled={busy||ad.paused||ad.status==='ENDED'} onClick={()=>void stop(ad)}>Ⅱ 게시 중단</button></div></td>
            </tr>)}</tbody></table></div>
          {!rows.length&&<p className="ads-empty" role="status">{loading?'광고를 불러오는 중입니다.':error?'광고 저장소 연결을 확인해 주세요.':'등록된 광고가 없습니다.'}</p>}
          {next&&<button disabled={busy||loading} onClick={()=>void load(next)}>다음 목록</button>}
          </section>
          <section className="card ads-preview-panel"><div className="ads-panel-heading"><h2>배너 미리보기</h2>
            <div className="segments">{(['top','bottom'] as const).map(value=><button key={value} aria-pressed={previewPlacement===value} onClick={()=>setPreviewPlacement(value)}>{value==='top'?'상단':'하단'}</button>)}</div>
            <div className="segments">{(['pc','mobile'] as const).map(value=><button key={value} aria-pressed={previewDevice===value} onClick={()=>setPreviewDevice(value)}>{value==='pc'?'PC':'모바일'}</button>)}</div>
          </div>
          <div className={'ads-preview-device '+previewDevice} style={{height:previewPlacement==='top'?120:104}}>
            {shownPreview?<img src={assetUrl(shownPreview.asset_id)} alt={shownPreview.title}/>:<p>등록된 배너를 선택하거나 편집 중인 이미지를 미리 확인해 주세요.</p>}
          </div>
          <p className="ads-preview-note">ⓘ 미리보기는 노출·클릭 집계에 포함되지 않아요.</p>
          </section>
        </div>
        <section className="card ads-editor" ref={formRef}><h2>광고 등록·수정</h2><form onSubmit={event=>{event.preventDefault();void submit();}}><fieldset disabled={busy}>
          <label className="ads-field"><span>제목</span><input required value={form.title} onChange={event=>setForm({...form,title:event.target.value})}/></label>
          <div className="ads-field"><span>배너 이미지</span><div><div className="ads-editor-image">{selectedImage?<img src={selectedImage} alt="편집 중인 배너"/>:<p>배너 이미지를 선택해 주세요.</p>}</div>
            <label className="ads-image-upload">▧ 이미지 변경<input aria-label="배너 이미지" type="file" accept="image/png,image/jpeg,image/webp" onChange={event=>setFile(event.target.files?.[0]||null)}/></label><small>PNG/JPEG/WebP · 최대 2MB</small></div></div>
          <label className="ads-field"><span>이동 링크</span><input required type="url" pattern="https://.*" placeholder="https://" value={form.link_url} onChange={event=>setForm({...form,link_url:event.target.value})}/></label>
          <div className="ads-field"><span>노출 위치</span><div className="radio-options">{(['top','bottom'] as const).map(value=><label key={value}><input type="radio" name="placement" checked={form.placement===value} onChange={()=>setForm({...form,placement:value})}/>{value==='top'?'상단':'하단'}</label>)}</div></div>
          <div className="ads-field"><span>게시 기간</span><div className="ads-date-fields"><label><span className="sr-only">게시 시작 · KST</span><input aria-label="게시 시작 · KST" required type="datetime-local" value={form.starts_at} onChange={event=>setForm({...form,starts_at:event.target.value})}/></label><span>~</span><label><span className="sr-only">게시 종료 · KST</span><input aria-label="게시 종료 · KST" required type="datetime-local" value={form.ends_at} onChange={event=>setForm({...form,ends_at:event.target.value})}/></label></div></div>
          <label className="ads-field"><span>우선순위</span><input required type="number" step="1" value={form.priority} onChange={event=>setForm({...form,priority:event.target.value})}/></label>
          <details className="ads-budget"><summary>광고 예산 설정</summary><p>일일·전체 한도를 함께 설정합니다. 예산 미설정 광고는 공개 게시되지 않습니다.</p>{(['daily_budget_tokens','total_budget_tokens'] as const).map(field=><label key={field}>{field==='daily_budget_tokens'?'일일 한도':'전체 한도'}<input type="number" step="1" min="1" value={form[field]} onChange={event=>setForm({...form,[field]:event.target.value})}/></label>)}</details>
          {editing?.paused&&<p className="ads-paused-note">중단된 광고는 수정해도 게시가 재개되지 않습니다.</p>}
          <button type="button" className="ads-preview-button" onClick={()=>void submit(true)}>편집 내용 미리보기</button>
          <div className="ads-editor-actions"><button className="primary" type="submit">{busy?'처리 중…':'저장'}</button><button type="button" disabled={!editing||editing.paused||editing.status==='ENDED'} onClick={()=>editing&&void stop(editing)}>게시 중단</button></div>
        </fieldset></form></section></div>
      </>}
    </main>
  </>;
}
