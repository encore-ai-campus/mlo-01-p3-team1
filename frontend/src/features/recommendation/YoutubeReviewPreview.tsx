import {useEffect, useRef, useState} from 'react';
import {loadYoutubeIframeApi, scopedYoutubeIframeEvents, watchYoutubeIframeReady, type YoutubeIframePlayer} from './youtubeIframeApi';
import type {ReviewObservation} from './youtubeReview';

export function YoutubeReviewPreview({videoId, onObservation, blocked = false}: {videoId: string; onObservation: (value: ReviewObservation) => void; blocked?: boolean}) {
  const host = useRef<HTMLDivElement>(null), player = useRef<YoutubeIframePlayer | null>(null), observer = useRef(onObservation); observer.current = onObservation;
  const gate = useRef(blocked); gate.current = blocked;
  const [message, setMessage] = useState('검수 미리보기를 준비하고 있어요.'), [reload, setReload] = useState(0);
  useEffect(() => {
    let disposed = false, ready = false, failed = false, cancelWait = () => {};
    let durationTimer: ReturnType<typeof setInterval> | undefined;
    setMessage('검수 미리보기를 준비하고 있어요.'); observer.current({video_id: videoId, playing: false, duration_seconds: 0});
    void loadYoutubeIframeApi().then(YT => {
      if (disposed || !host.current) return;
      const iframe = document.createElement('iframe'); iframe.title = '운영자 YouTube 원곡 검수 미리보기';
      iframe.src = `https://www.youtube.com/embed/?enablejsapi=1&playsinline=1&rel=0&origin=${encodeURIComponent(window.location.origin)}`;
      iframe.allow = 'autoplay; encrypted-media; fullscreen; picture-in-picture'; iframe.allowFullscreen = true; iframe.referrerPolicy = 'strict-origin-when-cross-origin';
      host.current.replaceChildren(iframe);
      const isCurrent = () => !disposed && player.current === instance;
      const observePlaying = () => {
        if (!isCurrent() || gate.current) return;
        const duration = instance.getDuration();
        if (Number.isFinite(duration) && duration > 0) {
          observer.current({video_id: videoId, playing: true, duration_seconds: duration});
          setMessage(`재생 시작과 영상 길이 ${Math.round(duration)}초를 확인했어요. 원곡과 일치하는지 직접 들어 확인해 주세요.`);
        } else setMessage('재생 중이에요. 영상 길이를 확인하고 있어요.');
      };
      const instance = new YT.Player(iframe, {events: scopedYoutubeIframeEvents(isCurrent, {
        onReady: () => {if (failed || ready) return; ready = true; cancelWait(); instance.loadVideoById(videoId); setMessage('미리보기 재생을 시도하고 있어요. 재생되지 않으면 아래 버튼을 눌러 주세요.');},
        onStateChange: event => {
          clearInterval(durationTimer); durationTimer = undefined;
          if (event.data === 1) {if (gate.current) instance.pauseVideo(); else {observePlaying(); durationTimer = setInterval(observePlaying, 1000);}}
          else if (event.data === 2) setMessage('미리보기를 일시 정지했어요. 확인한 재생 관측은 유지됩니다.');
          else if (event.data === 0) setMessage('미리보기가 끝났어요. 원곡 확인 후 검수를 완료할 수 있어요.');
        },
        onError: event => {
          if (!ready) failed = true;
          clearInterval(durationTimer); cancelWait();
          const error = event.data === 153 ? '페이지 출처 확인 오류(153)로 미리보기를 재생하지 못했어요.' : `이 영상의 삽입 재생을 확인하지 못했어요(오류 ${event.data}).`;
          setMessage(error); observer.current({video_id: videoId, playing: false, duration_seconds: 0, error});
        },
        onAutoplayBlocked: () => setMessage('자동 재생이 보류됐어요. [미리보기 재생]을 눌러 주세요.'),
      })});
      player.current = instance;
      cancelWait = watchYoutubeIframeReady(isCurrent, () => {if (!ready) {failed = true; setMessage('미리보기가 응답하지 않아요. 미리보기 다시 연결을 눌러 주세요.');}});
    }).catch(error => {if (!disposed) setMessage(error instanceof Error ? error.message : '미리보기 연결을 확인해 주세요.');});
    return () => {disposed = true; cancelWait(); clearInterval(durationTimer); player.current?.destroy(); player.current = null; host.current?.replaceChildren();};
  }, [videoId, reload]);
  useEffect(() => {if (blocked) player.current?.pauseVideo();}, [blocked]);
  return <div className="youtube-review-preview">
    <div className="youtube-review-frame" ref={host}/>
    <p role="status">{message}</p>
    <div className="youtube-review-actions"><button type="button" disabled={blocked} onClick={() => player.current?.playVideo()}>미리보기 재생</button><button type="button" onClick={() => player.current?.pauseVideo()}>미리보기 정지</button><button type="button" disabled={blocked} onClick={() => setReload(value => value + 1)}>미리보기 다시 연결</button></div>
  </div>;
}
