import {describe, expect, it, vi} from 'vitest';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {YoutubePlayer} from './YoutubePlayer';
import {YoutubePlaybackController, type PlaybackCandidate, type PlaybackResolution, type PlaybackSnapshot} from './youtubePlayerController';

const tracks = [1, 2, 3].map(index => ({track_id: `track-${index}`, track_name: `Song ${index}`, artists_name: 'Artist'}));
const candidate = (index: number): PlaybackCandidate => ({video_id: `testVID000${index}`, title: `Recording ${index}`, channel_title: 'Official channel', duration_seconds: 180, source: 'CATALOG_MAPPING', match_status: 'VERIFIED'});
const ready = (id: string, values = [candidate(1)]): PlaybackResolution => ({track_id: id, status: 'READY', candidates: values});
const settle = async () => {for (let n = 0; n < 12; n++) await Promise.resolve();};

function harness(resolve = vi.fn(async (id: string, _excluded: string[], _signal: AbortSignal) => ready(id))) {
  const adapter = {load: vi.fn(), play: vi.fn(), pause: vi.fn()};
  const states: PlaybackSnapshot[] = [];
  const controller = new YoutubePlaybackController(tracks, adapter, resolve, state => states.push(state));
  return {controller, adapter, resolve, states};
}

describe('embedded YouTube queue controller', () => {
  it('loads automatically but advances only after the actual current recording played and ended', async () => {
    const {controller, adapter, resolve} = harness();
    await controller.start();
    expect(adapter.load).toHaveBeenCalledWith('testVID0001');
    controller.onPlayerState(0);
    expect(resolve).toHaveBeenCalledTimes(1);
    controller.onPlayerState(1); controller.onPlayerState(0); controller.onPlayerState(0);
    await settle();
    expect(resolve.mock.calls.map(call => call[0])).toEqual(['track-1', 'track-2']);
    expect(controller.snapshot().index).toBe(1);
  });

  it('keeps a blocked autoplay on its current song until a user initiates play', async () => {
    const {controller, adapter, resolve} = harness();
    await controller.start(); controller.onAutoplayBlocked();
    expect(controller.snapshot().phase).toBe('blocked');
    expect(controller.snapshot().skipped).toEqual([]);
    expect(resolve).toHaveBeenCalledTimes(1);
    controller.play(); expect(adapter.play).toHaveBeenCalledTimes(1);
    controller.onPlayerState(1); expect(controller.snapshot().phase).toBe('playing');
  });

  it('does not misreport a zero-time loading delay as a browser autoplay block or skip a song', async () => {
    const {controller, resolve} = harness(); await controller.start(); controller.onLoadingDelayed();
    expect(controller.snapshot().phase).toBe('loading'); expect(controller.snapshot().message).toContain('길어지고');
    expect(controller.snapshot().message).not.toContain('브라우저'); expect(controller.snapshot().skipped).toEqual([]);
    expect(resolve).toHaveBeenCalledTimes(1);
    controller.onPlayerState(1); controller.onLoadingDelayed(); expect(controller.snapshot().phase).toBe('playing');
  });

  it('skips unmapped or pending registrations with explicit omissions while continuing to a reviewed registry recording', async () => {
    const resolver = vi.fn(async (id: string): Promise<PlaybackResolution> => id === 'track-3' ? ready(id, [{...candidate(3), source: 'MAPPING_REGISTRY'}]) : {track_id: id, status: 'MAPPING_REQUIRED', reason: id === 'track-1' ? 'UNMAPPED' : 'PENDING', candidates: []});
    const {controller, adapter} = harness(resolver); await controller.start(); await settle();
    expect(controller.snapshot().index).toBe(2); expect(controller.snapshot().skipped.map(item => item.track_id)).toEqual(['track-1', 'track-2']);
    expect(controller.snapshot().candidate?.source).toBe('MAPPING_REGISTRY'); expect(adapter.load).toHaveBeenCalledWith('testVID0003');
  });

  it('refreshes the current mapping without losing earlier omissions or resetting the queue', async () => {
    const {controller, resolve} = harness(); await controller.start(1); controller.retry(); await settle();
    expect(resolve.mock.calls.map(call => call[0])).toEqual(['track-2', 'track-2']); expect(controller.snapshot().index).toBe(1);
  });

  it('tries an alternate recording on 150, then re-resolves once with exclusions before skipping', async () => {
    const resolver = vi.fn(async (id: string, _excluded: string[], _signal: AbortSignal) => ready(id, [candidate(1), candidate(2)]));
    const {controller, adapter} = harness(resolver);
    await controller.start(); controller.onPlayerError(150);
    expect(adapter.load.mock.calls.map(call => call[0])).toEqual(['testVID0001', 'testVID0002']);
    controller.onPlayerError(101); await settle();
    expect(resolver.mock.calls[1][1]).toEqual(['testVID0001', 'testVID0002']);
    expect(controller.snapshot().skipped[0].track_id).toBe('track-1');
    expect(controller.snapshot().index).toBe(1);
  });

  it('does not make an environment error or unavailable search skip the rest of the queue', async () => {
    const {controller, resolve} = harness(); await controller.start(); controller.onPlayerError(153);
    expect(controller.snapshot().phase).toBe('error'); expect(controller.snapshot().skipped).toEqual([]);
    expect(resolve).toHaveBeenCalledTimes(1);
    const unavailable = harness(vi.fn(async (id: string) => ({track_id: id, status: 'SEARCH_UNAVAILABLE', candidates: [], message: '검색 연결 준비 중'})));
    await unavailable.controller.start(); await settle();
    expect(unavailable.resolve).toHaveBeenCalledTimes(1);
    expect(unavailable.controller.snapshot().phase).toBe('error');
    expect(unavailable.controller.snapshot().index).toBe(0);
  });

  it('records an actually blocked recording when its alternative search is unavailable, then holds on the next unmapped song', async () => {
    const resolver = vi.fn(async (id: string, excluded: string[], _signal: AbortSignal): Promise<PlaybackResolution> => id === 'track-1' && !excluded.length ? ready(id) : {track_id: id, status: 'SEARCH_UNAVAILABLE', candidates: []});
    const {controller} = harness(resolver);
    await controller.start(); controller.onPlayerError(150); await settle();
    expect(controller.snapshot().skipped.map(item => item.track_id)).toEqual(['track-1']);
    expect(controller.snapshot().index).toBe(1); expect(controller.snapshot().phase).toBe('error');
    expect(resolver).toHaveBeenCalledTimes(3);
  });

  it('lists no-match songs and never reports successful full playback when all fail', async () => {
    const {controller} = harness(vi.fn(async (id: string) => ({track_id: id, status: 'NO_MATCH', candidates: []})));
    await controller.start(); await settle();
    expect(controller.snapshot().skipped.map(item => item.track_id)).toEqual(tracks.map(track => track.track_id));
    expect(controller.snapshot().phase).toBe('unavailable');
    expect(controller.snapshot().message).not.toContain('완료');
  });

  it('aborts in-flight mapping and prevents an old response from playing after pending condition changes', async () => {
    let deliver: ((value: PlaybackResolution) => void) | null = null;
    const {controller, adapter, resolve} = harness(vi.fn((id: string, _excluded: string[], _signal: AbortSignal) => new Promise<PlaybackResolution>(accept => {deliver = accept;})));
    const started = controller.start(); controller.setBlocked('변경 조건 미반영');
    expect(resolve.mock.calls[0][2].aborted).toBe(true);
    deliver!(ready('track-1')); await started;
    expect(adapter.load).not.toHaveBeenCalled(); expect(controller.snapshot().phase).toBe('blocked');
    controller.play(); expect(adapter.play).not.toHaveBeenCalled();
    controller.setBlocked(null); expect(controller.snapshot().phase).toBe('paused');
  });

  it('pauses synchronously on a result gate and requires a fresh play gesture to resume', async () => {
    const {controller, adapter} = harness(); await controller.start(); controller.onPlayerState(1);
    controller.setBlocked('제외 저장 중');
    expect(adapter.pause).toHaveBeenCalled(); expect(controller.snapshot().phase).toBe('blocked');
    controller.setBlocked(null); expect(controller.snapshot().phase).toBe('paused');
    expect(adapter.play).not.toHaveBeenCalled(); controller.play(); expect(adapter.play).toHaveBeenCalledTimes(1);
  });

  it('rejects a resolver result for a different track and drops duplicate or invalid video IDs', async () => {
    const mismatch = harness(vi.fn(async () => ready('other-track'))); await mismatch.controller.start();
    expect(mismatch.adapter.load).not.toHaveBeenCalled(); expect(mismatch.controller.snapshot().phase).toBe('error');
    const valid = harness(vi.fn(async (id: string) => ready(id, [candidate(1), {...candidate(1)}, {...candidate(2), video_id: 'bad'}])));
    await valid.controller.start(); valid.controller.onPlayerError(150); await settle();
    expect(valid.adapter.load.mock.calls.map(call => call[0]).filter(id => id === 'bad')).toEqual([]);
    expect(valid.resolve.mock.calls[1][1]).toEqual(['testVID0001']);
  });

  it('stops a stale async result after destruction and cleans up media immediately', async () => {
    let deliver: ((value: PlaybackResolution) => void) | null = null;
    const {controller, adapter} = harness(vi.fn(() => new Promise<PlaybackResolution>(accept => {deliver = accept;})));
    const started = controller.start(); controller.destroy(); deliver!(ready('track-1')); await started;
    expect(adapter.pause).toHaveBeenCalled(); expect(adapter.load).not.toHaveBeenCalled();
  });

  it('renders the original whole queue count and in-place playback controls without requiring approval or an LLM', () => {
    const html = renderToStaticMarkup(createElement(YoutubePlayer, {playlistId: 'result-1', tracks, blockReason: '변경 조건 미반영'}));
    expect(html).toContain('선곡표 연속 재생'); expect(html).toContain('Song 1');
    expect(html).toContain('1/3곡'); expect(html).toContain('YouTube 재생');
    expect(html).toContain('변경 조건 미반영'); expect(html).not.toContain('임시 목록');
  });
});
