import {describe, expect, it, vi} from 'vitest';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {checkedNativeQueueHref, YoutubeNativePlayback, YoutubeNativeQueueView, type NativeYoutubeQueue} from './YoutubeNativePlayback';

const tracks = [1, 2, 3].map(index => ({track_id: `track-${index}`, track_name: `Song ${index}`, artists_name: 'Artist'}));
const complete: NativeYoutubeQueue = {playlist_id: 'result-1', tracks: tracks.map((track, index) => ({track_id: track.track_id, video_id: `testVID000${index + 1}`, source: 'OPERATOR_NATIVE_REPORTED_PLAYING'})), missing: [], total_count: 3, ready_count: 3, is_complete: true, url: 'https://www.youtube.com/watch_videos?video_ids=testVID0001,testVID0002,testVID0003'};
const partial: NativeYoutubeQueue = {...complete, tracks: [complete.tracks[0], complete.tracks[2]], missing: [{track_id: 'track-2', track_name: 'Song 2', reason: '외부 재생 확인 대기'}], ready_count: 2, is_complete: false, url: 'https://www.youtube.com/watch_videos?video_ids=testVID0001,testVID0003'};

describe('native YouTube default playback', () => {
  it('accepts a preloaded official queue URL in exact result order', () => {
    expect(checkedNativeQueueHref(complete, 'result-1', tracks)).toBe(complete.url);
    expect(checkedNativeQueueHref(partial, 'result-1', tracks)).toBe(partial.url);
  });

  it('rejects altered origins, parameters, IDs, track order and ownership/result mismatches', () => {
    for (const url of [complete.url!.replace('www.youtube.com', 'www.youtube.com.evil.example'), complete.url + '&autoplay=1', complete.url + '#fragment', 'javascript:alert(1)', complete.url!.replace('testVID0001,testVID0002', 'testVID0002,testVID0001')]) expect(checkedNativeQueueHref({...complete, url}, 'result-1', tracks)).toBeNull();
    expect(checkedNativeQueueHref(complete, 'other-result', tracks)).toBeNull();
    expect(checkedNativeQueueHref({...complete, tracks: [...complete.tracks].reverse()}, 'result-1', tracks)).toBeNull();
    expect(checkedNativeQueueHref({...complete, tracks: [complete.tracks[0], complete.tracks[0], complete.tracks[2]]}, 'result-1', tracks)).toBeNull();
  });

  it('rejects missing-count inconsistencies, duplicate videos and a partial result labelled as complete', () => {
    expect(checkedNativeQueueHref({...partial, is_complete: true}, 'result-1', tracks)).toBeNull();
    expect(checkedNativeQueueHref({...partial, missing: []}, 'result-1', tracks)).toBeNull();
    expect(checkedNativeQueueHref({...complete, ready_count: 2}, 'result-1', tracks)).toBeNull();
    expect(checkedNativeQueueHref({...complete, tracks: [complete.tracks[0], {...complete.tracks[1], video_id: complete.tracks[0].video_id}, complete.tracks[2]]}, 'result-1', tracks)).toBeNull();
  });

  it('labels a partial queue with both counts, missing songs and reduced actual playback time', () => {
    const html = renderToStaticMarkup(createElement(YoutubeNativeQueueView, {queue: partial, tracks, playlistId: 'result-1'}));
    expect(html).toContain('연결된 2곡만 YouTube에서 재생 (전체 3곡 중)');
    expect(html).toContain('Song 2'); expect(html).toContain('외부 재생 확인 대기');
    expect(html).toContain('실제 재생시간이 짧아집니다'); expect(html).toContain('원래 선곡표');
    expect(html).toContain('target="_blank"'); expect(html).toContain('rel="noopener noreferrer"');
  });

  it('gates a ready external link for pending conditions without changing the stored queue', () => {
    const html = renderToStaticMarkup(createElement(YoutubeNativeQueueView, {queue: complete, tracks, playlistId: 'result-1', blockReason: '선택 조건 변경 미반영'}));
    expect(html).toContain('선택 조건 변경 미반영'); expect(html).not.toContain('href=');
    expect(complete.tracks).toHaveLength(3);
  });

  it('renders the full queue action and account-storage caveat without a default iframe', () => {
    const html = renderToStaticMarkup(createElement(YoutubeNativeQueueView, {queue: complete, tracks, playlistId: 'result-1', onOpen: vi.fn()}));
    expect(html).toContain('YouTube에서 선곡표 연속 재생'); expect(html).toContain('계정에 저장한 재생목록이 아니며');
    expect(html).toContain('aria-label="새 탭에서 YouTube 선곡표 연속 재생"');
    expect(html).not.toContain('<iframe'); expect(html).not.toContain('iframe_api');
    const initial = renderToStaticMarkup(createElement(YoutubeNativePlayback, {playlistId: 'result-1', tracks}));
    expect(initial).not.toContain('<iframe'); expect(initial).not.toContain('embed/');
  });
});
