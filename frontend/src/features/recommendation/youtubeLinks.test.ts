import {describe, expect, it} from 'vitest';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import type {Track} from '../../shared/types';
import {checkedTrackLinks, nativeYoutubePlaylistUrl, stopMusicEventPropagation, youtubeTrackDestination, youtubeTemporaryQueueUrl} from './youtubeDestinations';
import {YoutubePlaylistLinks, YoutubeTrackLink} from './YoutubeLinks';

// Synthetic IDs here exercise URL validation only; they are never catalog mappings.

describe('YouTube dashboard destinations', () => {
  it('preserves multilingual title and artist as one encoded search query', () => {
    const track = {track_name: '눈 & 비 / "밤" #1', artists_name: 'A+B; 가수'};
    const destination = youtubeTrackDestination(track)!;
    const url = new URL(destination.href);
    expect(destination.kind).toBe('search');
    expect(url.origin + url.pathname).toBe('https://www.youtube.com/results');
    expect(url.searchParams.get('search_query')).toBe('눈 & 비 / "밤" #1 A+B; 가수');
    expect([...url.searchParams.keys()]).toEqual(['search_query']);
    expect(url.hash).toBe('');
  });

  it('opens a video only when both the ID and mapping status are verified', () => {
    const base = {track_name: 'Fixture', artists_name: 'Artist', youtube_video_id: 'testVID0001'};
    expect(youtubeTrackDestination(base)?.kind).toBe('search');
    expect(youtubeTrackDestination({...base, youtube_match_status: 'CANDIDATE'})?.kind).toBe('search');
    expect(youtubeTrackDestination({...base, youtube_match_status: 'VERIFIED'})?.href).toBe('https://www.youtube.com/watch?v=testVID0001');
    expect(youtubeTrackDestination({...base, youtube_video_id: 'bad&list=other', youtube_match_status: 'VERIFIED'})?.kind).toBe('search');
  });

  it('does not invent a search for missing metadata', () => {
    expect(youtubeTrackDestination({track_name: '', artists_name: ' '})).toBeNull();
  });

  it('accepts official native playlist URLs and strips unrelated parameters', () => {
    expect(nativeYoutubePlaylistUrl('https://youtube.com/playlist?list=PLfixture123456&unrelated=1')).toBe('https://www.youtube.com/playlist?list=PLfixture123456');
    for (const url of ['javascript:alert(1)', 'https://youtube.com.evil.example/playlist?list=PLfixture123456', 'http://youtube.com/playlist?list=PLfixture123456', 'https://www.youtube.com/watch?v=testVID0001', 'https://foreign.example/playlist?list=PLfixture123456']) expect(nativeYoutubePlaylistUrl(url)).toBeNull();
  });

  it('isolates the link click without preventing native navigation or changing music state', () => {
    let stopped = 0;
    stopMusicEventPropagation({stopPropagation: () => { stopped += 1; }});
    expect(stopped).toBe(1);
  });

  it('builds a native temporary queue in exact order only for fully verified tracks', () => {
    const tracks = [
      {track_name: 'First', artists_name: 'Artist', youtube_video_id: 'testVID0002', youtube_match_status: 'VERIFIED'},
      {track_name: 'Second', artists_name: 'Artist', youtube_video_id: 'testVID0001', youtube_match_status: 'VERIFIED'},
    ];
    expect(youtubeTemporaryQueueUrl(tracks)).toBe('https://www.youtube.com/watch_videos?video_ids=testVID0002,testVID0001');
    expect(youtubeTemporaryQueueUrl([])).toBeNull();
    expect(youtubeTemporaryQueueUrl([tracks[0], {...tracks[1], youtube_match_status: 'CANDIDATE'}])).toBeNull();
    expect(youtubeTemporaryQueueUrl([tracks[0], {...tracks[1], youtube_video_id: null}])).toBeNull();
    expect(youtubeTemporaryQueueUrl([tracks[0], {...tracks[1], youtube_video_id: 'bad'}])).toBeNull();
    expect(youtubeTemporaryQueueUrl([tracks[0], tracks[0]])).toBeNull();
  });

  const verifiedTracks: Track[] = [1, 2].map(n => ({track_id: `fixture-${n}`, track_name: `Song ${n}`, artists_name: 'Artist', album_name: 'Album', cover_image_url: null, genre_group_codes: [], theme_codes: [], scores: {W: null, P: null, S: null}, youtube_video_id: `testVID000${n}`, youtube_match_status: 'VERIFIED'}));

  it('renders a native temporary queue without requiring approval, and holds for pending changes', () => {
    const render = (blockReason?: string) => renderToStaticMarkup(createElement(YoutubePlaylistLinks, {tracks: verifiedTracks, excludedIds: [], blockReason}));
    expect(render()).toContain('watch_videos?video_ids=testVID0001,testVID0002');
    expect(render()).toContain('임시 목록');
    for (const reason of ['선택 조건 변경', '제외 변경 미저장', '저장 중', '생성 중', '저장 실패', '제외 초안 미반영']) {
      expect(render(reason)).not.toContain('watch_videos');
      expect(render(reason)).toContain(reason);
    }
  });

  it('never opens a shortened or partially mapped queue', () => {
    const excluded = renderToStaticMarkup(createElement(YoutubePlaylistLinks, {tracks: verifiedTracks, excludedIds: ['fixture-1']}));
    expect(excluded).not.toContain('watch_videos');
    const missing = renderToStaticMarkup(createElement(YoutubePlaylistLinks, {tracks: [verifiedTracks[0], {...verifiedTracks[1], youtube_video_id: undefined}], excludedIds: []}));
    expect(missing).not.toContain('watch_videos');
    expect(missing).toContain('1곡');
    const oldExclusion = renderToStaticMarkup(createElement(YoutubePlaylistLinks, {tracks: verifiedTracks, excludedIds: ['older-result-track']}));
    expect(oldExclusion).toContain('watch_videos');
  });

  it('renders separate search and verified video links with isolated new-tab navigation', () => {
    const direct = renderToStaticMarkup(createElement(YoutubeTrackLink, {track: verifiedTracks[0]}));
    expect(direct).toContain('YouTube에서 듣기');
    expect(direct).toContain('target="_blank"');
    expect(direct).toContain('rel="noopener noreferrer"');
    const search = renderToStaticMarkup(createElement(YoutubeTrackLink, {track: {...verifiedTracks[0], youtube_video_id: undefined, youtube_match_status: undefined}}));
    expect(search).toContain('YouTube에서 찾기');
    expect(search).toContain('/results?search_query=');
    const excluded = renderToStaticMarkup(createElement(YoutubeTrackLink, {track: verifiedTracks[0], excluded: true}));
    expect(excluded).not.toContain('href=');
  });
});

describe('current collected URL links', () => {
  const track: Track = {track_id: 'owned-track', track_name: 'O Sopro do Fole', artists_name: 'Maria Bethânia', album_name: 'Noturno', cover_image_url: null, genre_group_codes: [], theme_codes: [], scores: {W: null, P: null, S: null}};
  const candidate = {video_id: 'ZeQCSNL_Xxw', native_verified: false};
  it('uses a collected candidate directly without changing its approval or the snapshot', () => {
    const before = JSON.stringify(track);
    expect(youtubeTrackDestination(track, [candidate])).toEqual({kind: 'candidate', href: 'https://www.youtube.com/watch?v=ZeQCSNL_Xxw', label: '수집 영상 확인 (미검수)'});
    const html = renderToStaticMarkup(createElement(YoutubeTrackLink, {track, mappings: [candidate, {video_id: 'alternative', native_verified: false}]}));
    expect(html).toContain('수집 영상 확인 (미검수)'); expect(html).toContain('watch?v=ZeQCSNL_Xxw');
    expect(html).toContain('다른 수집 영상 1개'); expect(html).toContain('watch?v=alternative');
    expect(html).not.toContain('/results?'); expect(JSON.stringify(track)).toBe(before); expect(candidate.native_verified).toBe(false);
  });
  it('prefers native approval and never restores a revoked snapshot ID', () => {
    expect(youtubeTrackDestination(track, [candidate, {video_id: 'approved001', native_verified: true}])?.href).toContain('approved001');
    expect(youtubeTrackDestination({...track, youtube_video_id: 'oldVideo001', youtube_match_status: 'VERIFIED'}, [])?.kind).toBe('search');
    const html = renderToStaticMarkup(createElement(YoutubeTrackLink, {track, mappings: [candidate], excluded: true}));
    expect(html).not.toContain('href=');
  });
  it('validates exact result membership/order, candidate limits, revisions and IDs', () => {
    const items = [{track_id: track.track_id, revision: 1, candidates: [candidate]}];
    expect(checkedTrackLinks(items, [track])).toEqual(items);
    for (const value of [null, [], [{...items[0], track_id: 'foreign'}], [{...items[0], revision: -1}], [{...items[0], candidates: Array(11).fill(candidate)}], [{...items[0], candidates: [candidate, candidate]}], [{...items[0], candidates: [{...candidate, native_verified: 'true'}]}], [{...items[0], candidates: [{...candidate, video_id: 'bad&list=x'}]}]]) expect(checkedTrackLinks(value, [track])).toBeNull();
  });
});
