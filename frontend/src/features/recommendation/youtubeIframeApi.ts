export type YoutubeIframePlayer = {loadVideoById: (id: string) => void; playVideo: () => void; pauseVideo: () => void; destroy: () => void; getCurrentTime: () => number; getDuration: () => number};
export type YoutubeIframeOptions = {events: {onReady: () => void; onStateChange: (event: {data: number}) => void; onError: (event: {data: number}) => void; onAutoplayBlocked: () => void}};
export type YoutubeIframeApi = {Player: new (element: HTMLIFrameElement, options: YoutubeIframeOptions) => YoutubeIframePlayer};
type YoutubeWindow = Window & {YT?: YoutubeIframeApi; onYouTubeIframeAPIReady?: () => void};
let loading: Promise<YoutubeIframeApi> | null = null;

export function scopedYoutubeIframeEvents(isCurrent: () => boolean, events: YoutubeIframeOptions['events']): YoutubeIframeOptions['events'] {
  return {
    onReady: () => {if (isCurrent()) events.onReady();},
    onStateChange: event => {if (isCurrent()) events.onStateChange(event);},
    onError: event => {if (isCurrent()) events.onError(event);},
    onAutoplayBlocked: () => {if (isCurrent()) events.onAutoplayBlocked();},
  };
}

export function watchYoutubeIframeReady(isCurrent: () => boolean, onTimeout: () => void) {
  const timer = window.setTimeout(() => {if (isCurrent()) onTimeout();}, 20000);
  return () => clearTimeout(timer);
}

export function loadYoutubeIframeApi(): Promise<YoutubeIframeApi> {
  const target = window as YoutubeWindow;
  if (target.YT?.Player) return Promise.resolve(target.YT);
  if (loading) return loading;
  loading = new Promise((resolve, reject) => {
    const previous = target.onYouTubeIframeAPIReady;
    let owned = false;
    let script: HTMLScriptElement | null = null;
    const fail = (message: string) => {
      clearTimeout(timeout);
      if (owned) script?.remove();
      if (target.onYouTubeIframeAPIReady === finish) target.onYouTubeIframeAPIReady = previous;
      loading = null;
      reject(new Error(message));
    };
    const finish = () => {
      clearTimeout(timeout);
      if (target.onYouTubeIframeAPIReady === finish) target.onYouTubeIframeAPIReady = previous;
      try {previous?.();} finally {
        if (target.YT?.Player) resolve(target.YT);
        else fail('YouTube 플레이어 준비를 확인할 수 없어요.');
      }
    };
    target.onYouTubeIframeAPIReady = finish;
    const timeout = window.setTimeout(() => fail('YouTube 플레이어 연결 시간이 초과됐어요. 연결을 다시 확인해 주세요.'), 20000);
    script = document.getElementById('cafe-youtube-iframe-api') as HTMLScriptElement | null || Array.from(document.scripts).find(item => /^https:\/\/www\.youtube\.com\/(iframe_api|player_api)$/.test(item.src)) || null;
    if (!script) {
      owned = true;
      script = document.createElement('script'); script.id = 'cafe-youtube-iframe-api'; script.src = 'https://www.youtube.com/iframe_api'; script.async = true;
      script.addEventListener('error', () => fail('YouTube 플레이어를 불러오지 못했어요. 연결을 다시 확인해 주세요.'), {once: true});
      document.head.appendChild(script);
    }
  });
  return loading;
}
