import {afterEach, describe, expect, it, vi} from 'vitest';
import {ApiError} from '../../shared/api';
import {canVerifyNativeYoutubeMapping, canVerifyYoutubeMapping, canonicalYoutubeVideoUrl, reviewCsvTemplate, reviewFailureMessages, reviewSearchUrl, reviewTrackListParams, validateReviewCsv, youtubeReviewApi} from './youtubeReview';

afterEach(() => vi.unstubAllGlobals());

describe('keyless YouTube mapping review', () => {
  it('requires both explicit external-playback reports and a positive manually entered duration', () => {
    expect(canVerifyNativeYoutubeMapping(true, true, '243.5')).toBe(true);
    expect(canVerifyNativeYoutubeMapping(false, true, '243')).toBe(false);
    expect(canVerifyNativeYoutubeMapping(true, false, '243')).toBe(false);
    for (const duration of ['', '0', '-1', 'NaN', 'Infinity', '86401']) expect(canVerifyNativeYoutubeMapping(true, true, duration)).toBe(false);
    expect(canVerifyNativeYoutubeMapping(true, true, '240.261', {confirmed: true, note: '공식 영상 인트로 포함', originalSeconds: 213.226})).toBe(true);
    expect(canVerifyNativeYoutubeMapping(true, true, '240.261', {confirmed: true, note: '', originalSeconds: 213.226})).toBe(false);
    expect(canVerifyNativeYoutubeMapping(true, true, '274', {confirmed: true, note: '인트로', originalSeconds: 213.226})).toBe(false);
  });
  it('canonicalizes official video URLs while refusing spoofed hosts, credentials and unsafe protocols', () => {
    for (const value of ['https://youtu.be/testVID0001?t=12', 'https://www.youtube.com/watch?v=testVID0001&list=PL123', 'https://m.youtube.com/shorts/testVID0001', 'https://youtube.com/embed/testVID0001']) expect(canonicalYoutubeVideoUrl(value)).toBe('https://www.youtube.com/watch?v=testVID0001');
    for (const value of ['javascript:alert(1)', 'http://youtube.com/watch?v=testVID0001', 'https://www.youtube.com.evil.example/watch?v=testVID0001', 'https://foreign.example/testVID0001', 'https://user:pass@youtube.com/watch?v=testVID0001', 'https://youtube.com/watch?v=invalid', 'https://music.youtube.com/watch?v=testVID0001', 'https://youtube.com/live/testVID0001', 'https://youtu.be/testVID0001/extra', 'https://youtu.be/testVID0001/', 'https://youtube.com/embed/testVID0001/', 'https://youtube.com/watch?v=testVID0001&v=testVID0002', 'https://youtube.com/watch?v=testVID0001#part', 'https://youtube.com/\\foreign.example/watch?v=testVID0001']) expect(canonicalYoutubeVideoUrl(value)).toBeNull();
  });

  it('encodes multilingual title and artist together in the external operator search', () => {
    const url = new URL(reviewSearchUrl({track_name: '눈 & 비 #2', artists_name: '가수+A'}));
    expect(url.searchParams.get('search_query')).toBe('눈 & 비 #2 가수+A');
    expect(url.origin).toBe('https://www.youtube.com');
  });

  it('exports a UTF-8 template with per-track revisions and no invented video mapping', () => {
    expect(reviewCsvTemplate([{track_id: 'source-track', revision: 7}])).toBe('\uFEFFtrack_id,video_url,expected_revision,note\r\n"source-track","","7",""\r\n');
    const params = reviewTrackListParams('result-1', 'UNMAPPED', '비 & 눈', 2);
    expect(params.get('status')).toBe('UNMAPPED'); expect(params.get('q')).toBe('비 & 눈'); expect(params.get('page')).toBe('2');
    const csv = reviewCsvTemplate([{track_id: 'native-ready', revision: 3, mappings: [{video_url: 'https://youtu.be/testVID0001'}, {video_url: 'https://youtu.be/testVID0002', native_verified: true, note: '기존 검수 메모'}]}, {track_id: 'candidate', revision: 4, mappings: [{video_url: 'https://youtu.be/testVID0003'}]}, {track_id: 'unmapped', revision: 0, mappings: []}]);
    expect(csv).toContain('"native-ready","https://youtu.be/testVID0002","3","기존 검수 메모"');
    expect(csv).toContain('"candidate","https://youtu.be/testVID0003","4",""');
    expect(csv).toContain('"unmapped","","0",""');
  });

  it('accepts BOM, escaped quotes, quoted commas and multiline notes without splitting them into extra registrations', () => {
    const csv = '\uFEFFtrack_id,video_url,expected_revision,note\r\ntrack-a,https://youtu.be/testVID0001,0,"원곡, 확인\n메모 ""인용"""\r\n';
    expect(validateReviewCsv(csv)).toEqual([]);
  });

  it('returns row-specific errors and rejects oversized, invalid-header or malformed CSV atomically', () => {
    const csv = 'track_id,video_url,expected_revision,note\ntrack-a,https://foreign.example/testVID0001,-1,note\n,https://youtu.be/testVID0001,2,note';
    const errors = validateReviewCsv(csv);
    expect(errors.some(message => message.includes('2행') && message.includes('URL'))).toBe(true);
    expect(errors.some(message => message.includes('2행') && message.includes('revision'))).toBe(true);
    expect(errors.some(message => message.includes('3행') && message.includes('track_id'))).toBe(true);
    expect(validateReviewCsv('track_id,video_url,expected_revision\n' + Array.from({length: 501}, (_, index) => `${index},https://youtu.be/testVID0001,0`).join('\n'))).toEqual(['CSV는 한 번에 500행까지 등록할 수 있어요.']);
    expect(validateReviewCsv('track_id,video_url,expected_revision\na,"unterminated,0')[0]).toContain('따옴표');
    expect(validateReviewCsv('track_id,video_url,expected_revision,unsupported\na,b,0,x')[0]).toContain('헤더');
  });

  it('requires the selected video to have actual PLAYING, positive duration and an explicit original-recording confirmation', () => {
    const observed = {video_id: 'testVID0001', playing: true, duration_seconds: 180};
    expect(canVerifyYoutubeMapping(observed, 'testVID0001', true)).toBe(true);
    expect(canVerifyYoutubeMapping(observed, 'testVID0001', false)).toBe(false);
    expect(canVerifyYoutubeMapping(observed, 'testVID0002', true)).toBe(false);
    expect(canVerifyYoutubeMapping({...observed, playing: false}, 'testVID0001', true)).toBe(false);
    expect(canVerifyYoutubeMapping({...observed, duration_seconds: 0}, 'testVID0001', true)).toBe(false);
    expect(canVerifyYoutubeMapping({...observed, error: '150'}, 'testVID0001', true)).toBe(false);
  });

  it('sends the local code in a header with CSRF and keeps it out of the URL and request body', async () => {
    vi.stubGlobal('document', {cookie: 'csrftoken=fixture-csrf'});
    const fetch = vi.fn(async () => ({ok: true, json: async () => ({items: []})})); vi.stubGlobal('fetch', fetch);
    await youtubeReviewApi('/api/youtube-review/mappings', 'fixture-local-code', 'POST', {track_id: 'track-a', video_url: 'https://youtu.be/testVID0001', expected_revision: 0});
    const [url, options] = fetch.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).not.toContain('fixture-local-code'); expect(options.body).not.toContain('fixture-local-code');
    expect(options.headers).toMatchObject({'X-Youtube-Review-Code': 'fixture-local-code', 'X-CSRFToken': 'fixture-csrf'});
    expect(options.credentials).toBe('same-origin'); expect(options.cache).toBe('no-store');
  });

  it('preserves server row errors and revision-conflict messages for the operator', () => {
    const error = new ApiError('INVALID_CSV', '전체 등록을 보류했어요.', {row_errors: [{row: 3, field: 'video_url', message: '영상 URL 오류'}]}, 422);
    expect(reviewFailureMessages(error)).toEqual(['전체 등록을 보류했어요.', '3행 (video_url): 영상 URL 오류']);
    expect(reviewFailureMessages(new ApiError('CONFLICT', '최신 revision을 확인해 주세요.', {row: 4}, 409))).toEqual(['4행: 최신 revision을 확인해 주세요.']);
  });
});
