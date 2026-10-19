import {useEffect, useRef, useState} from 'react';
import {api} from '../../shared/api';
import {Badge,Metrics,number} from '../admin/AdminLayout';
import {YoutubeReviewPreview} from './YoutubeReviewPreview';
import {canVerifyNativeYoutubeMapping, canVerifyYoutubeMapping, canonicalYoutubeVideoUrl, reviewCsvTemplate, reviewFailureMessages, reviewSearchUrl, reviewTrackListParams, validateReviewCsv, youtubeReviewApi, type ReviewFilter, type ReviewList, type ReviewMapping, type ReviewObservation, type ReviewStatus, type ReviewTrack} from './youtubeReview';
import './YoutubeReviewPanel.css';

export function YoutubeReviewPanel({playlistId, onUpdated, onPreviewActive, blocked = false, adminSession = false}: {playlistId: string; onUpdated: () => void; onPreviewActive: (active: boolean) => void; blocked?: boolean; adminSession?: boolean}) {
  const [status, setStatus] = useState<ReviewStatus | null>(null), [codeInput, setCodeInput] = useState(''), [code, setCode] = useState('');
  const [filter, setFilter] = useState<ReviewFilter>('ALL'), [queryInput, setQueryInput] = useState(''), [query, setQuery] = useState(''), [page, setPage] = useState(1);
  const [data, setData] = useState<ReviewList | null>(null), [selected, setSelected] = useState<ReviewTrack | null>(null);
  const [url, setUrl] = useState(''), [note, setNote] = useState(''), [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false), [refresh, setRefresh] = useState(0), [errors, setErrors] = useState<string[]>([]), [notice, setNotice] = useState('');
  const [preview, setPreview] = useState<ReviewMapping | null>(null), [observation, setObservation] = useState<ReviewObservation | null>(null), [confirmed, setConfirmed] = useState(false);
  const [nativeReview, setNativeReview] = useState<ReviewMapping | null>(null), [nativePlayed, setNativePlayed] = useState(false), [nativeIdentity, setNativeIdentity] = useState(false), [nativeDuration, setNativeDuration] = useState('');
  const [nativeDifference, setNativeDifference] = useState(false);
  const [csv, setCsv] = useState(''), [csvName, setCsvName] = useState(''), [csvErrors, setCsvErrors] = useState<string[]>([]);
  const previewCallback = useRef(onPreviewActive); previewCallback.current = onPreviewActive;
  const base = adminSession ? '/api/admin/youtube-review' : '/api/youtube-review';
  const authorized = adminSession || !!code;
  function reviewRequest<T>(suffix: string, method = 'GET', body?: unknown, signal?: AbortSignal): Promise<T> {
    return adminSession ? api<T>(base + suffix, method, body, undefined, signal) : youtubeReviewApi<T>(base + suffix, code, method, body, signal);
  }
  useEffect(() => {
    const controller = new AbortController();
    void api<ReviewStatus>(base + '/status', 'GET', undefined, undefined, controller.signal).then(setStatus).catch(error => {if (!controller.signal.aborted) setErrors(reviewFailureMessages(error));});
    return () => controller.abort();
  }, [base]);
  useEffect(() => {previewCallback.current(!!preview); return () => previewCallback.current(false);}, [!!preview]);
  useEffect(() => {
    setPreview(null); setObservation(null); setConfirmed(false); setNativeReview(null); setNativePlayed(false); setNativeIdentity(false); setNativeDuration(''); setNativeDifference(false); setSelected(null); setPage(1);
  }, [playlistId]);
  useEffect(() => {
    if (!authorized || !status?.enabled) return;
    const controller = new AbortController(); setBusy(true); setErrors([]);
    const params = reviewTrackListParams(playlistId, filter, query, page);
    void reviewRequest<ReviewList>(`/tracks?${params}`, 'GET', undefined, controller.signal).then(result => {
      if (controller.signal.aborted) return;
      setData(result); setSelected(current => result.items.find(track => track.track_id === current?.track_id) || current || result.items[0] || null);
    }).catch(error => {if (!controller.signal.aborted) setErrors(reviewFailureMessages(error));}).finally(() => {if (!controller.signal.aborted) setBusy(false);});
    return () => controller.abort();
  }, [playlistId, code, adminSession, status?.enabled, query, filter, page, refresh]);
  function choose(track: ReviewTrack) {setSelected(track); setPreview(null); setObservation(null); setConfirmed(false); setNativeReview(null); setNativePlayed(false); setNativeIdentity(false); setNativeDuration(''); setNativeDifference(false); setReason(''); setUrl(''); setNote(''); setNotice('');}
  function showPreview(mapping: ReviewMapping) {setNativeReview(null); setPreview(mapping); setObservation(null); setConfirmed(false); setReason(''); setNote(mapping.note || ''); setNotice('');}
  function showNativeReview(mapping: ReviewMapping) {setPreview(null); setObservation(null); setNativeReview(mapping); setNativePlayed(false); setNativeIdentity(false); setNativeDuration(''); setNativeDifference(false); setReason(''); setNote(mapping.note || ''); setNotice('');}
  async function mutate(path: string, body: Record<string, unknown>, success: string) {
    if (busy || !authorized) return;
    setBusy(true); setErrors([]); setNotice('');
    try {
      const response = await reviewRequest<{items?: Pick<ReviewTrack, 'track_id' | 'revision' | 'mappings'>[]; track_id?: string; revision?: number; mappings?: ReviewMapping[]}>(`/${path}`, 'POST', {...body, ...(!adminSession && playlistId ? {playlist_id: playlistId} : {})});
      const updates = response.items || (response.track_id && response.revision !== undefined && response.mappings ? [{track_id: response.track_id, revision: response.revision, mappings: response.mappings}] : []);
      setSelected(current => {const update = updates.find(item => item.track_id === current?.track_id); return current && update ? {...current, ...update} : current;});
      if (path === 'verify' || path === 'block') {setPreview(null); setObservation(null);}
      if (path === 'native-verify' || path === 'native-block') {setNativeReview(null); setNativePlayed(false); setNativeIdentity(false); setNativeDuration(''); setNativeDifference(false);}
      setNotice(success); onUpdated(); setRefresh(value => value + 1); setConfirmed(false);
    } catch (error) {setErrors(reviewFailureMessages(error));}
    finally {setBusy(false);}
  }
  async function downloadTemplate() {
    if (!authorized || busy) return;
    setBusy(true); setErrors([]);
    try {
      const tracks: ReviewTrack[] = [];
      for (let current = 1; ; current++) {
        const params = reviewTrackListParams(playlistId, filter, query, current);
        const result = await reviewRequest<ReviewList>(`/tracks?${params}`);
        tracks.push(...result.items.slice(0, 500 - tracks.length));
        if (tracks.length >= result.total || !result.items.length || tracks.length >= 500) break;
      }
      const blob = new Blob([reviewCsvTemplate(tracks)], {type: 'text/csv;charset=utf-8'}), href = URL.createObjectURL(blob), anchor = document.createElement('a');
      anchor.href = href; anchor.download = 'youtube-mapping-template.csv'; anchor.click(); URL.revokeObjectURL(href);
      setNotice('현재 검수 목록의 곡 ID·revision·기존 영상 URL을 담은 양식을 내려받았어요. 비어 있는 URL을 보완하거나 대체할 URL을 수정해 주세요.');
    } catch (error) {setErrors(reviewFailureMessages(error));}
    finally {setBusy(false);}
  }
  async function readCsv(file: File | undefined) {
    if (!file) return;
    setCsvName(file.name);
    if (file.size > 1024 * 1024) {setCsv(''); setCsvErrors(['CSV 파일은 1MB까지 등록할 수 있어요.']); return;}
    try {const content = new TextDecoder('utf-8', {fatal: true}).decode(await file.arrayBuffer()); setCsv(content); setCsvErrors(validateReviewCsv(content));}
    catch {setCsv(''); setCsvErrors(['UTF-8 CSV 파일로 저장한 뒤 다시 선택해 주세요.']);}
  }
  const registrationForm = selected ? <form className="youtube-review-register" onSubmit={event => {event.preventDefault(); const canonical = canonicalYoutubeVideoUrl(url); if (!canonical) {setErrors(['올바른 https YouTube 영상 URL을 입력해 주세요.']); return;} void mutate('mappings', {track_id: selected.track_id, video_url: canonical, expected_revision: selected.revision, note}, '영상 후보를 등록했어요. 아래 후보를 미리보기로 검수해 주세요.');}}>
          <label>YouTube 영상 URL<input type="url" value={url} onChange={event => setUrl(event.target.value)} placeholder="https://www.youtube.com/watch?v=…" required/></label>
          <label>등록·검수 메모<input value={note} onChange={event => setNote(event.target.value)} maxLength={1000}/></label><button type="submit" disabled={busy}>영상 후보 등록</button>
        </form> : null;
  const csvImport = <details className="youtube-review-import"><summary>CSV로 영상 후보 일괄 등록</summary><p>현재 검색·상태 필터에 해당하는 검수 목록을 내려받습니다. 기존 URL은 채워지며 없는 URL만 보완해 UTF-8로 저장해 주세요. 최대 500행이며 한 행이라도 잘못되면 전체 등록을 보류합니다. 등록 후 각 영상의 검수가 필요합니다.</p><button type="button" disabled={busy || !data?.total} onClick={() => void downloadTemplate()}>현재 검수 목록 CSV 양식 다운로드</button><label>UTF-8 CSV 파일<input type="file" accept=".csv,text/csv" onChange={event => void readCsv(event.target.files?.[0])}/></label>{csvName && <small>{csvName}</small>}<label>CSV 내용<textarea value={csv} rows={5} onChange={event => {setCsv(event.target.value); setCsvErrors(validateReviewCsv(event.target.value));}} placeholder="track_id,video_url,expected_revision,note"/></label>{!!csvErrors.length && <ul className="youtube-review-errors">{csvErrors.slice(0, 50).map((error, index) => <li key={index}>{error}</li>)}</ul>}<button type="button" disabled={busy || !csv.trim() || !!csvErrors.length} onClick={() => {const failures = validateReviewCsv(csv); setCsvErrors(failures); if (!failures.length) void mutate('import', {csv_text: csv}, 'CSV의 모든 행을 영상 후보로 등록했어요. 각 영상의 재생과 원곡을 검수해 주세요.');}}>CSV 전체 후보 등록</button></details>;
  const canVerify = !!preview && canVerifyYoutubeMapping(observation, preview.video_id, confirmed);
  if (!status) return <section className="youtube-review-panel"><p role="status">영상 연결 관리 설정을 확인하고 있어요.</p>{errors.map((error, index) => <p role="alert" key={index}>{error}</p>)}</section>;
  if (!status.enabled) return <section className="youtube-review-panel"><p>이 환경에서는 로컬 영상 연결 관리가 열려 있지 않아요.</p></section>;
  return <section className={'youtube-review-panel'+(adminSession?' youtube-review-admin':'')} aria-label="영상 연결 관리">
    {!adminSession&&<><div className="youtube-review-heading"><h2>영상 연결 관리</h2><span>운영자 로컬 검수</span></div>
    <p className="youtube-review-intro">곡의 YouTube 주소를 직접 등록하고, 외부 YouTube 재생과 원곡 정보를 확인합니다. 대시보드 삽입 재생 검수는 별도이며 등록만으로 완료되지는 않아요.</p></>}
    {!authorized ? <form className="youtube-review-login" onSubmit={event => {event.preventDefault(); setCode(codeInput.trim()); setCodeInput(''); setErrors([]);}}>
      <label>로컬 검수 접근 코드<input type="password" autoComplete="off" value={codeInput} onChange={event => setCodeInput(event.target.value)} required/></label><button type="submit">영상 연결 관리 열기</button>
      <small>이 실행에서 발급한 로컬 코드입니다. Google 비밀번호나 API 키를 입력하지 마세요. 코드는 이 패널의 메모리에만 보관합니다.</small>
      {status.access_code_file && <details><summary>접근 코드 파일 위치</summary><code>{status.access_code_file}</code></details>}
    </form> : <>
      {adminSession&&<Metrics items={[{label:'미연결',value:number(data?.summary.unmapped)+'곡',icon:'↗'},{label:'검수 대기',value:number(data?.summary.pending)+'곡',icon:'◷'},{label:'검수 완료 · 외부 또는 삽입',value:number(data?.summary.verified)+'곡',icon:'✓',tone:'green'},{label:'차단',value:number(data?.summary.blocked)+'곡',icon:'⊘'}]}/>}
      <div className="youtube-review-toolbar"><form onSubmit={event => {event.preventDefault(); setQuery(queryInput); setPage(1);}}><label>곡 검색<input value={queryInput} onChange={event => setQueryInput(event.target.value)} placeholder="곡명 · 아티스트"/></label><button disabled={busy} type="submit">검색</button></form>
        <label>연결 상태<select value={filter} onChange={event => {setFilter(event.target.value as ReviewFilter); setPage(1);}}><option value="ALL">전체</option><option value="UNMAPPED">미연결</option><option value="PENDING">검수 대기</option><option value="VERIFIED">검수 완료</option><option value="BLOCKED">차단</option></select></label>
        {!adminSession && <button type="button" onClick={() => {setCode(''); setData(null); setSelected(null); setPreview(null); setObservation(null); setConfirmed(false); setNativeReview(null); setNativePlayed(false); setNativeIdentity(false); setNativeDuration(''); setErrors([]);}}>관리 잠그기</button>}</div>
      {data && <div className="youtube-review-counts">전체 {data.summary.total ?? data.total}곡 · 미연결 {data.summary.unmapped ?? 0} · 검수 대기 {data.summary.pending ?? 0} · 검수 완료 {data.summary.verified ?? 0} · 차단 {data.summary.blocked ?? 0}<br/>현재 필터 {data.total}곡 · {page}페이지 · 등록/검수는 추천 결과와 점수를 바꾸지 않습니다.</div>}
      <div className="youtube-review-grid"><div className="youtube-review-track-list">{adminSession?<><div className="admin-panel-heading"><h2>영상 연결 목록</h2><button type="button" className="primary" onClick={()=>document.querySelector<HTMLDetailsElement>('.youtube-review-admin .youtube-review-import')?.setAttribute('open','')}>＋ CSV 등록</button></div><div className="admin-table-scroll"><table className="admin-table"><thead><tr><th>곡명 · 아티스트</th><th>외부 재생</th><th>삽입 재생</th><th>관리</th></tr></thead><tbody>{data?.items.map(track=>{
        const native=track.mappings.some(m=>m.native_verified)?'승인':!track.mappings.length?'미연결':track.mappings.every(m=>!!m.native_reason)?'차단':'검수 대기';
        const embed=track.mappings.some(m=>m.status==='VERIFIED')?'승인':!track.mappings.length?'미연결':track.mappings.every(m=>m.status==='BLOCKED')?'차단':'검수 대기';
        const tone=(state:string)=>state==='승인'?'green':state==='차단'?'red':state==='미연결'?'muted':'amber';
        return <tr key={track.track_id} className={selected?.track_id===track.track_id?'selected':''}><td><div className="admin-track-cell"><img src="/default-cover.svg" alt=""/><div><strong>{track.track_name}</strong><small>{track.artists_name}</small></div></div></td><td><Badge tone={tone(native)}>{native}</Badge></td><td><Badge tone={tone(embed)}>{embed}</Badge></td><td><button type="button" aria-label={`${track.track_name} 영상 검수`} onClick={()=>choose(track)}>검수</button></td></tr>;
      })}</tbody></table></div></>:<ul>{data?.items.map(track => <li key={track.track_id} className={selected?.track_id === track.track_id ? 'selected' : ''}><button type="button" onClick={() => choose(track)}><strong>{track.track_name}</strong><span>{track.artists_name}</span><small>{track.mappings.length ? `외부 ${track.mappings.filter(mapping => mapping.native_verified).length}개 · 삽입 ${track.mappings.filter(mapping => mapping.status === 'VERIFIED').length}개 확인 · ${track.mappings.length}개 후보` : '미연결'}</small></button></li>)}</ul>}
        {data?.total === 0 && <p>이 조건에 해당하는 곡이 없어요.</p>}
        <div className="youtube-review-actions"><button type="button" disabled={busy || page <= 1} onClick={() => setPage(value => value - 1)}>이전 페이지</button><button type="button" disabled={busy || !data || page * data.page_size >= data.total} onClick={() => setPage(value => value + 1)}>다음 페이지</button><button type="button" disabled={busy} onClick={() => setRefresh(value => value + 1)}>목록 새로 확인</button></div>
        {adminSession&&<><div className="admin-detail-section"><h3>영상 후보 등록</h3>{registrationForm||<p>목록에서 곡을 선택해 주세요.</p>}</div>{csvImport}</>}
      </div><div className="youtube-review-detail">{selected ? <>
        {adminSession&&<h2>선택한 영상 검수</h2>}
        <h3>{selected.track_name}</h3><p>{selected.artists_name} · 원본 {Math.round(selected.duration_ms / 1000)}초</p>
        <a href={reviewSearchUrl(selected)} target="_blank" rel="noopener noreferrer">이 곡을 YouTube에서 검색 ↗</a><small className="youtube-review-help">검색 결과에서 원곡 영상을 찾아 주소를 복사해 주세요. 외부에서 열기만 하면 검수가 완료되지는 않습니다.</small>
        {!adminSession&&registrationForm}
        <ul className="youtube-review-mappings">{selected.mappings.map(mapping => <li key={mapping.video_id}><div><strong>외부 {mapping.native_verified ? '확인됨' : mapping.native_reason ? '차단' : '확인 대기'} · 삽입 {mapping.status === 'VERIFIED' ? '확인됨' : mapping.status === 'BLOCKED' ? '차단' : '확인 대기'}</strong> <a href={mapping.video_url} target="_blank" rel="noopener noreferrer">{mapping.video_id} ↗</a></div>{mapping.native_verified && <p>외부 길이 {mapping.native_duration_seconds ?? '미기록'}초 · {mapping.native_source === 'LEGACY_NATIVE_METADATA_REVIEW' ? '기존 외부 목록·메타데이터 확인 자료' : mapping.native_source === 'OPERATOR_NATIVE_REPORTED_PLAYING' ? '운영자 외부 재생 확인 보고' : mapping.native_source || '외부 확인 자료'}</p>}{mapping.native_reason && <p>외부 연결 차단 사유: {mapping.native_reason}</p>}{mapping.reason && <p>삽입 재생 사유: {mapping.reason}</p>}{mapping.note && <p>{mapping.note}</p>}<div className="youtube-review-actions"><button type="button" disabled={busy} onClick={() => showNativeReview(mapping)}>외부 재생 확인</button><button type="button" disabled={busy} onClick={() => showPreview(mapping)}>삽입 재생 검수 (보조)</button></div></li>)}</ul>
        {!selected.mappings.length && <p>등록된 영상이 없어요. URL 또는 CSV로 후보를 등록해 주세요.</p>}
        {nativeReview && <div className="youtube-review-check"><div className="youtube-review-heading"><h4>외부 재생 확인 · {nativeReview.video_id}</h4><button type="button" onClick={() => setNativeReview(null)}>외부 확인 닫기</button></div>
          <a className="youtube-review-native-open" href={nativeReview.video_url} target="_blank" rel="noopener noreferrer">YouTube에서 열어 확인 ↗</a>
          <p className="youtube-review-help">새 탭에서 직접 재생한 뒤 아래 항목을 확인해 주세요. 이 대시보드는 외부 탭의 실제 재생 상태를 자동으로 확인하지 않습니다.</p>
          <label className="youtube-review-confirm"><input type="checkbox" checked={nativePlayed} onChange={event => setNativePlayed(event.target.checked)}/>외부 YouTube에서 재생을 확인했어요.</label>
          <label className="youtube-review-confirm"><input type="checkbox" checked={nativeIdentity} onChange={event => setNativeIdentity(event.target.checked)}/>곡·아티스트·버전이 원곡 정보와 일치함을 확인했어요.</label>
          <label>외부 영상에서 확인한 전체 길이 (초)<input type="number" min="0.001" max="86400" step="any" value={nativeDuration} onChange={event => setNativeDuration(event.target.value)} placeholder="예: 243"/></label>
          <label className="youtube-review-confirm"><input type="checkbox" checked={nativeDifference} onChange={event => setNativeDifference(event.target.checked)}/>원곡과 길이가 다른 공식 영상판임을 확인했어요. (메모 필수)</label>
          <label>외부 재생 확인 메모<input value={note} maxLength={1000} onChange={event => setNote(event.target.value)} placeholder="공식 영상판의 인트로 등 차이의 근거"/></label>
          {nativeDifference && <p className="youtube-review-help">원본과 60초 이내의 차이만 별도로 확인할 수 있어요. 원래 추천 시간은 바뀌지 않으며 실제 영상 재생시간은 달라집니다.</p>}
          <button type="button" disabled={busy || !canVerifyNativeYoutubeMapping(nativePlayed, nativeIdentity, nativeDuration, {confirmed: nativeDifference, note, originalSeconds: selected.duration_ms / 1000})} onClick={() => void mutate('native-verify', {track_id: selected.track_id, video_id: nativeReview.video_id, expected_revision: selected.revision, identity_confirmed: true, playback_observed: true, duration_seconds: Number(nativeDuration), note, ...(nativeDifference ? {duration_difference_confirmed: true} : {})}, '운영자 외부 재생 확인을 저장했어요. 중앙의 영상 연결을 갱신합니다.')}>외부 재생 확인 저장</button>
          <div className="youtube-review-block"><label>외부 연결 차단 사유<input value={reason} maxLength={1000} onChange={event => setReason(event.target.value)} placeholder="다른 곡, 삭제, 국내 재생 불가 등"/></label><button type="button" disabled={busy || !reason.trim()} onClick={() => void mutate('native-block', {track_id: selected.track_id, video_id: nativeReview.video_id, expected_revision: selected.revision, reason: reason.trim()}, '이 영상의 외부 연결을 차단했어요. 삽입 재생 상태는 별도로 유지합니다.')}>외부 연결 차단</button></div>
        </div>}
        {preview && <div className="youtube-review-check"><div className="youtube-review-heading"><h4>원곡 검수 · {preview.video_id}</h4><button type="button" onClick={() => {setPreview(null); setObservation(null); setConfirmed(false);}}>미리보기 닫기</button></div><YoutubeReviewPreview videoId={preview.video_id} onObservation={value => {setObservation(value); if (!value.playing || value.error) setConfirmed(false);}} blocked={blocked}/>
          <label className="youtube-review-confirm"><input type="checkbox" disabled={!observation?.playing || observation.duration_seconds <= 0 || !!observation.error} checked={confirmed} onChange={event => setConfirmed(event.target.checked)}/>곡·아티스트·버전이 원곡 정보와 일치함을 확인했어요.</label>
          <p className="youtube-review-help">{observation?.playing && observation.duration_seconds > 0 ? `재생 시작 관측 · ${Math.round(observation.duration_seconds)}초` : '실제 삽입 재생 시작과 영상 길이를 확인해야 완료할 수 있어요.'} 길이 차이가 크면 서버에서 검수를 보류합니다.</p>
          <button type="button" disabled={busy || !canVerify} onClick={() => void mutate('verify', {track_id: selected.track_id, video_id: preview.video_id, expected_revision: selected.revision, identity_confirmed: true, playback_observed: true, duration_seconds: observation!.duration_seconds, note}, '원곡 확인과 삽입 재생 검수를 완료했어요. 현재 곡의 연결을 다시 확인할 수 있습니다.')}>이 영상 검수 완료</button>
          <div className="youtube-review-block"><label>삽입 재생 차단 사유<input value={reason} maxLength={1000} onChange={event => setReason(event.target.value)} placeholder="삽입 불가 등"/></label><button type="button" disabled={busy || !reason.trim()} onClick={() => void mutate('block', {track_id: selected.track_id, video_id: preview.video_id, expected_revision: selected.revision, reason: reason.trim()}, '이 영상의 삽입 재생을 차단했어요. 외부 재생 확인과는 별도로 관리합니다.')}>삽입 재생 차단</button></div>
        </div>}
      </> : <p>왼쪽에서 곡을 선택해 주세요.</p>}</div></div>
      {!adminSession&&csvImport}
    </>}
    {!!errors.length && <div className="youtube-review-errors" role="alert"><strong>등록 내용을 확인해 주세요.</strong><ul>{errors.slice(0, 50).map((error, index) => <li key={index}>{error}</li>)}</ul><p>실패한 입력은 유지됩니다. revision 충돌이면 목록을 새로 확인하고 변경 내용을 다시 적용해 주세요.</p></div>}
    {notice && <p className="youtube-review-notice" role="status">{notice}</p>}
    {busy && <p role="status">영상 연결 정보를 확인하고 있어요…</p>}
  </section>;
}
