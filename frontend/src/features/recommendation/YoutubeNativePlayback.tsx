import {useEffect, useState} from 'react';
import {api} from '../../shared/api';
import type {PlaybackTrack} from './youtubePlayerController';
import './YoutubeNativePlayback.css';

export type NativeYoutubeQueue = {playlist_id: string; tracks: {track_id: string; video_id: string; source: string}[]; missing: {track_id: string; track_name: string; reason: string}[]; total_count: number; ready_count: number; url: string | null; is_complete: boolean};

export function checkedNativeQueueHref(queue: NativeYoutubeQueue, playlistId: string, tracks: PlaybackTrack[]): string | null {
  if (!queue || !Array.isArray(queue.tracks) || !Array.isArray(queue.missing)) return null;
  if (queue.playlist_id !== playlistId || queue.total_count !== tracks.length || queue.ready_count !== queue.tracks.length || !queue.ready_count || queue.ready_count + queue.missing.length !== queue.total_count) return null;
  if (queue.is_complete !== (queue.ready_count === queue.total_count && !queue.missing.length)) return null;
  const allIds = [...queue.tracks.map(track => track.track_id), ...queue.missing.map(track => track.track_id)];
  if (new Set(allIds).size !== tracks.length || allIds.some(id => !tracks.some(track => track.track_id === id))) return null;
  const ordered = tracks.filter(track => queue.tracks.some(item => item.track_id === track.track_id)).map(track => track.track_id);
  if (ordered.some((id, index) => queue.tracks[index].track_id !== id)) return null;
  const videoIds = queue.tracks.map(track => track.video_id);
  if (videoIds.some(id => !/^[A-Za-z0-9_-]{11}$/.test(id)) || new Set(videoIds).size !== videoIds.length || !queue.url) return null;
  try {
    const url = new URL(queue.url);
    if (url.protocol !== 'https:' || url.hostname !== 'www.youtube.com' || url.pathname !== '/watch_videos' || url.username || url.password || url.port || url.hash || [...url.searchParams.keys()].join(',') !== 'video_ids' || url.searchParams.get('video_ids') !== videoIds.join(',')) return null;
    return url.href;
  } catch {return null;}
}

export function YoutubeNativeQueueView({queue, tracks, playlistId, blockReason, onOpen}: {queue: NativeYoutubeQueue; tracks: PlaybackTrack[]; playlistId: string; blockReason?: string | null; onOpen?: () => void}) {
  const href = !blockReason ? checkedNativeQueueHref(queue, playlistId, tracks) : null;
  return <>
    <div className="youtube-native-ready"><strong>{queue.ready_count}/{queue.total_count}곡 외부 연결 준비</strong><span>{queue.is_complete ? '선곡표 전체 순서' : '연결된 곡의 원래 순서'}</span></div>
    {blockReason ? <p className="youtube-native-message" role="status">{blockReason}</p> : href ? <a className="youtube-native-cta" href={href} target="_blank" rel="noopener noreferrer" onClick={onOpen}>{queue.is_complete ? 'YouTube에서 연속 재생 ↗' : `연결된 ${queue.ready_count}곡만 YouTube에서 재생 (전체 ${queue.total_count}곡 중) ↗`}</a> : <p className="youtube-native-message" role="status">{queue.ready_count ? '영상 연결 정보를 다시 확인해 주세요.' : '아직 외부 재생을 확인한 영상이 없어요. 영상 연결 관리에서 등록·확인해 주세요.'}</p>}
    {!queue.is_complete && <p className="youtube-native-partial">원래 선곡표 {queue.total_count}곡은 유지됩니다. 연결되지 않은 곡을 빼고 열기 때문에 실제 재생시간이 짧아집니다.</p>}
    {!!queue.missing.length && <details className="youtube-native-missing"><summary>연결되지 않은 곡 {queue.missing.length}곡 확인</summary><ul>{queue.missing.map(track => <li key={track.track_id}><strong>{track.track_name}</strong><span>{track.reason}</span></li>)}</ul></details>}
    <small className="youtube-native-note">YouTube의 임시 목록을 새 탭에서 엽니다. 계정에 저장한 재생목록이 아니며, 실제 영상 순서·광고·재생 가능 여부는 YouTube에서 확인해 주세요. 영상판의 길이는 원본 곡 길이와 다를 수 있어요.</small>
  </>;
}

export function YoutubeNativePlayback({playlistId, tracks, blockReason, mappingRevision = 0, onOpen}: {playlistId: string; tracks: PlaybackTrack[]; blockReason?: string | null; mappingRevision?: number; onOpen?: () => void}) {
  const [queue, setQueue] = useState<NativeYoutubeQueue | null>(null), [error, setError] = useState(''), [retry, setRetry] = useState(0), [loading, setLoading] = useState(true);
  const queueKey = tracks.map(track => track.track_id).join('|');
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError(''); setQueue(null);
    void api<NativeYoutubeQueue>(`/api/playlists/${encodeURIComponent(playlistId)}/youtube-queue`, 'GET', undefined, undefined, controller.signal).then(result => {
      if (!controller.signal.aborted) {if (result.playlist_id !== playlistId) throw new Error('선곡표의 영상 연결 정보가 일치하지 않아요.'); setQueue(result);}
    }).catch(reason => {if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : '영상 연결을 확인해 주세요.');}).finally(() => {if (!controller.signal.aborted) setLoading(false);});
    return () => controller.abort();
  }, [playlistId, queueKey, mappingRevision, retry]);
  const currentQueue = queue?.playlist_id === playlistId ? queue : null;
  return <section className="youtube-native-playback" aria-label="YouTube 외부 연속 재생">
    <h3>YouTube에서 음악을 이어 들으세요</h3>
    {loading ? <p className="youtube-native-message" role="status">선곡표의 영상 연결을 확인하고 있어요.</p> : error ? <p className="youtube-native-message" role="alert">{error}</p> : currentQueue ? <YoutubeNativeQueueView queue={currentQueue} tracks={tracks} playlistId={playlistId} blockReason={blockReason} onOpen={onOpen}/> : null}
    <button className="youtube-native-refresh" type="button" disabled={loading || !!blockReason} onClick={() => setRetry(value => value + 1)}>영상 연결 다시 확인</button>
  </section>;
}
