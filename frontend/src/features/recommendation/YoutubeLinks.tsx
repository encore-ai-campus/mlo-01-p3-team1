import type {Track} from '../../shared/types';
import {stopMusicEventPropagation, youtubeTrackDestination, youtubeTemporaryQueueUrl, type YoutubeTrackFields} from './youtubeDestinations';
import './YoutubeLinks.css';

type LinkedTrack = Track & YoutubeTrackFields;

export function YoutubeTrackLink({track, excluded = false}: {track: LinkedTrack; excluded?: boolean}) {
  const destination = youtubeTrackDestination(track);
  if (!destination || excluded) return <span className="youtube-track-link youtube-link-unavailable" aria-disabled="true">YouTube에서 찾기</span>;
  return <a className="youtube-track-link" href={destination.href} target="_blank" rel="noopener noreferrer"
    onClick={stopMusicEventPropagation} aria-label={`${track.track_name} · ${destination.label} (새 탭)`}
    title={destination.kind === 'search' ? '곡명과 아티스트로 검색합니다. 검색 결과에서 영상을 선택해 주세요.' : '확인한 YouTube 영상을 새 탭에서 엽니다.'}>
    {destination.label}<span aria-hidden="true"> ↗</span>
  </a>;
}

export function YoutubePlaylistLinks({tracks, excludedIds, blockReason}: {
  tracks: LinkedTrack[];
  excludedIds: string[];
  blockReason?: string | null;
}) {
  const active = tracks.filter(track => !excludedIds.includes(track.track_id));
  const ready = tracks.filter(track => youtubeTrackDestination(track)?.kind === 'video').length;
  const pendingExclusions = active.length !== tracks.length;
  const nativeUrl = !blockReason && !pendingExclusions ? youtubeTemporaryQueueUrl(tracks) : null;
  const unavailable = blockReason || (pendingExclusions ? '제외한 곡을 반영한 새 선곡표를 먼저 받아 주세요.' : ready < tracks.length ? `아직 ${tracks.length - ready}곡의 YouTube 영상이 확인되지 않았어요. 곡별 검색으로 영상을 선택할 수 있어요.` : '같은 영상에 연결된 곡이 있어 전체 목록 연결을 보류했어요. 영상 확인이 필요해요.');
  return <section className="youtube-playlist-links" aria-label="YouTube에서 선곡표 열기">
    <div className="youtube-playlist-heading"><strong>YouTube 연결</strong><span>{ready}/{tracks.length}곡 영상 확인</span></div>
    {nativeUrl ? <a className="youtube-native-playlist" href={nativeUrl} target="_blank" rel="noopener noreferrer" onClick={stopMusicEventPropagation}>선곡표를 YouTube 임시 목록으로 열기 ↗</a> :
      <p>{unavailable}</p>}
    <small>{nativeUrl ? '계정에 저장한 재생목록이 아닙니다. 실제 재생과 영상 순서는 YouTube에서 확인해 주세요.' : '확인된 전곡이 있어야 전체 목록을 열 수 있어요. 검색 링크는 자동 연속 재생이 아닙니다.'}</small>
  </section>;
}
