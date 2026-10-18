import {useEffect, useRef, useState} from 'react';
import {api} from '../../shared/api';
import {loadYoutubeIframeApi, scopedYoutubeIframeEvents, watchYoutubeIframeReady, type YoutubeIframePlayer} from './youtubeIframeApi';
import {YoutubePlaybackController, type PlaybackResolution, type PlaybackSnapshot, type PlaybackTrack} from './youtubePlayerController';
import './YoutubePlayer.css';

export type YoutubePlayerProps = {playlistId: string; tracks: PlaybackTrack[]; blockReason?: string | null; mappingRevision?: number; onTrackChange?: (trackId: string | null) => void};
const initial: PlaybackSnapshot = {index: 0, phase: 'idle', message: 'YouTube 플레이어를 준비하고 있어요.', candidate: null, skipped: [], playedTrackIds: []};

export function YoutubePlayer({playlistId, tracks, blockReason, mappingRevision = 0, onTrackChange}: YoutubePlayerProps) {
  const host = useRef<HTMLDivElement>(null), engine = useRef<YoutubePlaybackController | null>(null), player = useRef<YoutubeIframePlayer | null>(null);
  const latest = useRef({blockReason, onTrackChange}); latest.current = {blockReason, onTrackChange};
  const [state, setState] = useState<PlaybackSnapshot>(initial), [bootError, setBootError] = useState(''), [reload, setReload] = useState(0);
  const queueKey = tracks.map(track => track.track_id).join('|');
  useEffect(() => {
    let disposed = false;
    let cancelReadyWait = () => {};
    setState(initial); setBootError('');
    const currentTracks = [...tracks];
    void loadYoutubeIframeApi().then(YT => {
      if (disposed || !host.current) return;
      const iframe = document.createElement('iframe');
      iframe.title = 'YouTube 선곡표 삽입 재생';
      iframe.src = `https://www.youtube.com/embed/?enablejsapi=1&playsinline=1&rel=0&origin=${encodeURIComponent(window.location.origin)}`;
      iframe.allow = 'autoplay; encrypted-media; fullscreen; picture-in-picture';
      iframe.allowFullscreen = true; iframe.referrerPolicy = 'strict-origin-when-cross-origin';
      host.current.replaceChildren(iframe);
      let ready = false, failed = false;
      const isCurrent = () => !disposed && player.current === instance;
      const instance = new YT.Player(iframe, {events: scopedYoutubeIframeEvents(isCurrent, {
        onReady: () => {
          if (ready || failed) return;
          ready = true; cancelReadyWait();
          const controller = new YoutubePlaybackController(currentTracks, {load: id => instance.loadVideoById(id), play: () => instance.playVideo(), pause: () => instance.pauseVideo()},
            (trackId, excludedVideoIds, signal) => api<PlaybackResolution>(`/api/playlists/${encodeURIComponent(playlistId)}/youtube-playback`, 'POST', {track_id: trackId, excluded_video_ids: excludedVideoIds}, undefined, signal),
            next => {if (!disposed) {setState(next); latest.current.onTrackChange?.(currentTracks[next.index]?.track_id || null);}});
          engine.current = controller;
          if (latest.current.blockReason) controller.setBlocked(latest.current.blockReason);
          else void controller.start();
        },
        onStateChange: event => engine.current?.onPlayerState(event.data),
        onError: event => {
          if (!ready) {
            failed = true; cancelReadyWait();
            setBootError(event.data === 153 ? 'YouTube가 이 페이지의 출처를 확인하지 못했어요(153). 대시보드를 새로고침해 주세요.' : `YouTube 플레이어를 준비하지 못했어요(오류 ${event.data}). 연결을 다시 확인해 주세요.`);
            return;
          }
          engine.current?.onPlayerError(event.data);
        },
        onAutoplayBlocked: () => engine.current?.onAutoplayBlocked(),
      })});
      player.current = instance;
      cancelReadyWait = watchYoutubeIframeReady(isCurrent, () => {
        if (!ready && !failed) {
          failed = true;
          setBootError('YouTube 플레이어가 응답하지 않아요. 연결을 다시 확인해 주세요.');
        }
      });
    }).catch(error => {if (!disposed) setBootError(error instanceof Error ? error.message : 'YouTube 플레이어 연결을 확인해 주세요.');});
    return () => {disposed = true; cancelReadyWait(); engine.current?.destroy(); engine.current = null; player.current?.destroy(); player.current = null; host.current?.replaceChildren();};
    // The immutable result ID and ordered track IDs identify the queue. An
    // approval/feedback re-fetch must not restart the current song.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playlistId, queueKey, reload]);
  useEffect(() => {engine.current?.setBlocked(blockReason || null);}, [blockReason]);
  useEffect(() => {
    if (state.phase !== 'loading') return;
    const timer = window.setTimeout(() => {if ((player.current?.getCurrentTime() || 0) === 0) engine.current?.onLoadingDelayed();}, 15000);
    return () => clearTimeout(timer);
  }, [state.phase, state.candidate?.video_id]);
  const track = tracks[state.index];
  const blocked = !!blockReason;
  const busy = state.phase === 'resolving' || state.phase === 'idle';
  const message = blockReason || bootError || state.message;
  return <section className="youtube-player" aria-label="선곡표 연속 재생">
    <div className="youtube-player-heading"><strong>YouTube 연속 재생</strong><span>{Math.min(state.index + 1, tracks.length)}/{tracks.length}곡</span></div>
    <div className="youtube-player-frame" ref={host}/>
    {track && <div className="youtube-player-track"><strong>{track.track_name}</strong><span>{track.artists_name}</span></div>}
    <p className="youtube-player-status" role="status">{message}</p>
    <div className="youtube-player-controls">
      <button type="button" disabled={blocked || busy || !state.index || !!bootError} onClick={() => engine.current?.previous()} aria-label="이전 곡">이전</button>
      {state.phase === 'playing' ? <button type="button" disabled={blocked} onClick={() => engine.current?.pause()} aria-label="재생 일시 정지">일시 정지</button> : <button type="button" disabled={blocked || busy || !!bootError} onClick={() => engine.current?.play()} aria-label="YouTube 재생">재생</button>}
      <button type="button" disabled={blocked || busy || state.index >= tracks.length - 1 || !!bootError} onClick={() => engine.current?.next()} aria-label="다음 곡">다음</button>
    </div>
    {(bootError || state.phase === 'error') && <button className="youtube-player-retry" type="button" disabled={blocked} onClick={() => bootError ? setReload(value => value + 1) : engine.current?.retry()}>연결 다시 확인</button>}
    {!bootError && <button className="youtube-player-retry" type="button" disabled={blocked || busy} onClick={() => engine.current?.retry()}>{mappingRevision > 0 ? '영상 연결 갱신 · 현재 곡 다시 확인' : '현재 곡 영상 연결 다시 확인'}</button>}
    {state.candidate && <small className="youtube-player-source">영상: {state.candidate.title} · {state.candidate.channel_title}</small>}
    {!!state.skipped.length && <details className="youtube-player-skipped"><summary>재생하지 못한 곡 {state.skipped.length}곡</summary><ul>{state.skipped.map(item => <li key={item.track_id}><strong>{item.track_name}</strong> — {item.reason}</li>)}</ul><p>건너뛴 곡만큼 실제 재생시간이 짧아집니다. 원래 선곡표는 유지됩니다.</p></details>}
    <small className="youtube-player-note">선곡표 순서대로 자동 연결합니다. 브라우저에서 자동 재생을 막으면 재생을 한 번 눌러 주세요. 광고·재생 가능 여부는 YouTube에 따릅니다.</small>
  </section>;
}
