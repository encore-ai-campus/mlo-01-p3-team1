import {ApiError} from '../../shared/api';

export type ReviewMappingStatus = 'CANDIDATE' | 'VERIFIED' | 'BLOCKED';
export type ReviewMapping = {video_id: string; video_url: string; status: ReviewMappingStatus; duration_seconds?: number | null; reason?: string; identity_confirmed?: boolean; playback_observed?: boolean; note?: string; source?: string; updated_at?: string; native_verified?: boolean; native_duration_seconds?: number | null; native_observed_at?: string | null; native_source?: string; native_reason?: string};
export type ReviewTrack = {track_id: string; track_name: string; artists_name: string; duration_ms: number; revision: number; mappings: ReviewMapping[]};
export type ReviewList = {items: ReviewTrack[]; total: number; page: number; page_size: number; summary: Record<string, number>};
export type ReviewFilter = 'ALL' | 'UNMAPPED' | 'PENDING' | 'VERIFIED' | 'BLOCKED';
export type ReviewStatus = {enabled: boolean; is_test: boolean; access_code_file?: string};
export type ReviewObservation = {video_id: string; playing: boolean; duration_seconds: number; error?: string};

export function canonicalYoutubeVideoUrl(value: string): string | null {
  try {
    if (!value || value.length > 2048 || /[\u0000-\u001f\u007f\\]/.test(value)) return null;
    const url = new URL(value.trim());
    if (url.protocol !== 'https:' || url.username || url.password || url.port || url.hash) return null;
    const host = url.hostname.toLowerCase();
    let videoId: string | null = null;
    if (host === 'youtu.be') videoId = url.pathname.match(/^\/([A-Za-z0-9_-]{11})$/)?.[1] || null;
    else if (['youtube.com', 'www.youtube.com', 'm.youtube.com'].includes(host)) {
      if (url.pathname === '/watch' && url.searchParams.getAll('v').length === 1) videoId = url.searchParams.get('v');
      else videoId = url.pathname.match(/^\/(?:embed|shorts)\/([A-Za-z0-9_-]{11})$/)?.[1] || null;
    }
    return videoId && /^[A-Za-z0-9_-]{11}$/.test(videoId) ? `https://www.youtube.com/watch?v=${videoId}` : null;
  } catch {return null;}
}

export function reviewSearchUrl(track: Pick<ReviewTrack, 'track_name' | 'artists_name'>) {
  return `https://www.youtube.com/results?search_query=${encodeURIComponent(`${track.track_name} ${track.artists_name}`.trim())}`;
}

export function reviewTrackListParams(playlistId: string, filter: ReviewFilter, query: string, page: number) {
  return new URLSearchParams({...(playlistId ? {playlist_id: playlistId} : {}), q: query, status: filter, page: String(page), page_size: '30'});
}

export function reviewCsvTemplate(tracks: (Pick<ReviewTrack, 'track_id' | 'revision'> & {mappings?: Pick<ReviewMapping, 'video_url' | 'native_verified' | 'note'>[]})[]) {
  const quote = (value: unknown) => `"${String(value).replaceAll('"', '""')}"`;
  return '\uFEFFtrack_id,video_url,expected_revision,note\r\n' + tracks.map(track => {
    const mapping = track.mappings?.find(item => item.native_verified) || track.mappings?.[0];
    return [track.track_id, mapping?.video_url || '', track.revision, mapping?.note || ''].map(quote).join(',');
  }).join('\r\n') + '\r\n';
}

export function validateReviewCsv(text: string): string[] {
  const rows: string[][] = [], errors: string[] = [];
  let row: string[] = [], field = '', quoted = false, closed = false;
  const input = text.replace(/^\uFEFF/, '');
  for (let index = 0; index < input.length; index++) {
    const char = input[index];
    if (quoted) {
      if (char === '"' && input[index + 1] === '"') {field += '"'; index++;}
      else if (char === '"') {quoted = false; closed = true;}
      else field += char;
    } else if (char === ',' || char === '\n' || char === '\r') {
      row.push(field); field = ''; closed = false;
      if (char !== ',') {
        if (char === '\r' && input[index + 1] === '\n') index++;
        if (row.some(value => value.trim())) rows.push(row);
        row = [];
      }
    } else if (char === '"' && !field && !closed) quoted = true;
    else if (closed || char === '"') return ['CSV 따옴표 형식을 확인해 주세요.'];
    else field += char;
  }
  if (quoted) return ['CSV에 닫히지 않은 따옴표가 있어요.'];
  row.push(field); if (row.some(value => value.trim())) rows.push(row);
  if (rows.length < 2) return ['헤더와 등록할 영상 행이 필요해요.'];
  if (rows.length - 1 > 500) return ['CSV는 한 번에 500행까지 등록할 수 있어요.'];
  const header = rows[0].map(value => value.trim());
  const required = ['track_id', 'video_url', 'expected_revision'];
  if (required.some(key => !header.includes(key)) || header.some(key => ![...required, 'note'].includes(key)) || new Set(header).size !== header.length) return ['CSV 헤더는 track_id,video_url,expected_revision,note를 사용해 주세요.'];
  for (let index = 1; index < rows.length; index++) {
    const values = rows[index], line = index + 1;
    if (values.length !== header.length) {errors.push(`${line}행: 열 개수가 헤더와 달라요.`); continue;}
    if (!values[header.indexOf('track_id')].trim()) errors.push(`${line}행: track_id가 비어 있어요.`);
    if (!canonicalYoutubeVideoUrl(values[header.indexOf('video_url')])) errors.push(`${line}행: 올바른 YouTube 영상 URL이 필요해요.`);
    if (!/^(0|[1-9]\d*)$/.test(values[header.indexOf('expected_revision')].trim())) errors.push(`${line}행: expected_revision은 0 이상의 정수여야 해요.`);
  }
  return errors;
}

export function canVerifyYoutubeMapping(observation: ReviewObservation | null, videoId: string, identityConfirmed: boolean) {
  return !!identityConfirmed && !!observation?.playing && observation.video_id === videoId && Number.isFinite(observation.duration_seconds) && observation.duration_seconds > 0 && !observation.error;
}

export function canVerifyNativeYoutubeMapping(played: boolean, identityConfirmed: boolean, duration: string, difference?: {confirmed: boolean; note: string; originalSeconds: number}) {
  const seconds = Number(duration);
  const basic = played && identityConfirmed && duration.trim() !== '' && Number.isFinite(seconds) && seconds > 0 && seconds <= 86400;
  return basic && (!difference?.confirmed || difference.note.trim() !== '' && Number.isFinite(difference.originalSeconds) && difference.originalSeconds > 0 && Math.abs(seconds - difference.originalSeconds) <= 60);
}

export async function youtubeReviewApi<T>(path: string, accessCode: string, method = 'GET', body?: unknown, signal?: AbortSignal): Promise<T> {
  const token = document.cookie.split('; ').find(value => value.startsWith('csrftoken='))?.slice(10) || '';
  const response = await fetch(path, {method, credentials: 'same-origin', cache: 'no-store', signal,
    headers: {'Content-Type': 'application/json', 'X-Youtube-Review-Code': accessCode, ...(token ? {'X-CSRFToken': token} : {})},
    body: body === undefined ? undefined : JSON.stringify(body)});
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(data?.code || 'REVIEW_UNAVAILABLE', data?.message || '영상 연결 관리 요청을 확인해 주세요.', data?.details || {}, response.status);
  return data;
}

export function reviewFailureMessages(error: unknown): string[] {
  if (!(error instanceof ApiError)) return [error instanceof Error ? error.message : '영상 연결 관리 요청을 확인해 주세요.'];
  const details = error.details;
  const rows = details.row_errors || details.errors;
  const messages = Array.isArray(rows) ? rows.map(row => {
    const value = row as {row?: unknown; line?: unknown; message?: unknown; error?: unknown; field?: unknown};
    return `${value.row || value.line || '?'}행${value.field ? ` (${value.field})` : ''}: ${String(value.message || value.error || '입력값을 확인해 주세요.')}`;
  }) : [];
  return [details.row ? `${String(details.row)}행: ${error.message}` : error.message, ...messages];
}
