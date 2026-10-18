import {afterEach, describe, expect, it, vi} from 'vitest';

function browserFixture() {
  const scripts: {id: string; src: string; async: boolean; remove: () => void; addEventListener: ReturnType<typeof vi.fn>}[] = [];
  const target: {YT?: {Player: () => void}; onYouTubeIframeAPIReady?: () => void; setTimeout: typeof setTimeout} = {setTimeout};
  const document = {
    scripts,
    getElementById: (id: string) => scripts.find(script => script.id === id),
    createElement: () => {
      const script = {id: '', src: '', async: false, remove: () => {const index = scripts.indexOf(script); if (index >= 0) scripts.splice(index, 1);}, addEventListener: vi.fn()};
      return script;
    },
    head: {appendChild: (script: typeof scripts[number]) => scripts.push(script)},
  };
  vi.stubGlobal('window', target); vi.stubGlobal('document', document);
  return {target, document, scripts};
}

afterEach(() => {vi.unstubAllGlobals(); vi.useRealTimers(); vi.resetModules();});

describe('YouTube IFrame API loader', () => {
  it('ignores every late event from a disposed or replaced iframe', async () => {
    const {scopedYoutubeIframeEvents} = await import('./youtubeIframeApi');
    let live = true;
    const handlers = {onReady: vi.fn(), onStateChange: vi.fn(), onError: vi.fn(), onAutoplayBlocked: vi.fn()};
    const scoped = scopedYoutubeIframeEvents(() => live, handlers);
    scoped.onReady(); scoped.onStateChange({data: 1}); scoped.onError({data: 150}); scoped.onAutoplayBlocked();
    live = false;
    scoped.onReady(); scoped.onStateChange({data: 0}); scoped.onError({data: 153}); scoped.onAutoplayBlocked();
    for (const callback of Object.values(handlers)) expect(callback).toHaveBeenCalledTimes(1);
    expect(handlers.onStateChange).toHaveBeenCalledWith({data: 1});
  });

  it('reports a player that never becomes ready and cancels the wait after ready or unmount', async () => {
    vi.useFakeTimers(); browserFixture();
    const {watchYoutubeIframeReady} = await import('./youtubeIframeApi');
    const timeout = vi.fn(); watchYoutubeIframeReady(() => true, timeout);
    await vi.advanceTimersByTimeAsync(20000); expect(timeout).toHaveBeenCalledTimes(1);
    const cancelled = vi.fn(), cancel = watchYoutubeIframeReady(() => true, cancelled); cancel();
    watchYoutubeIframeReady(() => false, cancelled);
    await vi.advanceTimersByTimeAsync(20000); expect(cancelled).not.toHaveBeenCalled();
  });

  it('loads one script for concurrent players and preserves another integration ready callback', async () => {
    const {target, scripts} = browserFixture();
    const previous = vi.fn(); target.onYouTubeIframeAPIReady = previous;
    const {loadYoutubeIframeApi} = await import('./youtubeIframeApi');
    const first = loadYoutubeIframeApi(), second = loadYoutubeIframeApi();
    expect(first).toBe(second); expect(scripts).toHaveLength(1);
    target.YT = {Player: vi.fn()}; target.onYouTubeIframeAPIReady!();
    expect(await first).toBe(target.YT); expect(previous).toHaveBeenCalledTimes(1);
    expect(target.onYouTubeIframeAPIReady).toBe(previous);
    expect(await loadYoutubeIframeApi()).toBe(target.YT); expect(scripts).toHaveLength(1);
  });

  it('uses an existing official API script rather than appending a duplicate', async () => {
    const {target, scripts, document} = browserFixture();
    const script = document.createElement(); script.src = 'https://www.youtube.com/iframe_api'; document.head.appendChild(script);
    const {loadYoutubeIframeApi} = await import('./youtubeIframeApi'); const pending = loadYoutubeIframeApi();
    expect(scripts).toHaveLength(1);
    target.YT = {Player: vi.fn()}; target.onYouTubeIframeAPIReady!(); await pending;
    expect(scripts[0]).toBe(script);
  });

  it('removes its timed-out script so the visible retry can really reconnect', async () => {
    vi.useFakeTimers();
    const {target, scripts} = browserFixture();
    const {loadYoutubeIframeApi} = await import('./youtubeIframeApi');
    const failure = expect(loadYoutubeIframeApi()).rejects.toThrow('시간이 초과');
    await vi.advanceTimersByTimeAsync(20000); await failure;
    expect(scripts).toHaveLength(0);
    const retry = loadYoutubeIframeApi(); expect(scripts).toHaveLength(1);
    target.YT = {Player: vi.fn()}; target.onYouTubeIframeAPIReady!(); await retry;
  });
});
