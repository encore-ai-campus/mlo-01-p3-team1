export type YoutubeTrackFields = {
  track_name: string;
  artists_name: string;
  youtube_video_id?: string | null;
  youtube_match_status?: string | null;
};

export type YoutubeLinkCandidate = {video_id: string; native_verified: boolean};
export type YoutubeTrackLinks = {track_id: string; revision: number; candidates: YoutubeLinkCandidate[]};
export type YoutubeMappingSnapshot = {playlist_id: string; mappingRevision: number; track_links: YoutubeTrackLinks[]};
export type YoutubeDestination = {kind: 'video' | 'candidate' | 'search'; href: string; label: string};

/** Accept only the exact owned result order. URLs are built locally from validated IDs. */
export function checkedTrackLinks(value: unknown, tracks: {track_id: string}[]): YoutubeTrackLinks[] | null {
  if (!Array.isArray(value) || value.length !== tracks.length) return null;
  for (let index = 0; index < value.length; index++) {
    const item = value[index];
    if (!item || item.track_id !== tracks[index].track_id || !Number.isSafeInteger(item.revision) || item.revision < 0 || !Array.isArray(item.candidates) || item.candidates.length > 10) return null;
    const ids = new Set<string>();
    for (const candidate of item.candidates) {
      if (!candidate || typeof candidate.video_id !== 'string' || !/^[A-Za-z0-9_-]{11}$/.test(candidate.video_id) || typeof candidate.native_verified !== 'boolean' || ids.has(candidate.video_id)) return null;
      ids.add(candidate.video_id);
    }
  }
  return value.map(item => ({track_id: item.track_id, revision: item.revision,
    candidates: item.candidates.map((candidate: YoutubeLinkCandidate) => ({video_id: candidate.video_id, native_verified: candidate.native_verified}))}));
}

/** Public navigation only. This does not authenticate, enqueue or change feedback. */
export function youtubeTrackDestination(track: YoutubeTrackFields, mappings?: YoutubeLinkCandidate[]): YoutubeDestination | null {
  // An authoritative empty registry must supersede stale immutable catalog fields.
  if (mappings !== undefined) {
    const candidate = mappings.find(item => item.native_verified) || mappings[0];
    if (candidate && /^[A-Za-z0-9_-]{11}$/.test(candidate.video_id)) {
      return {kind: candidate.native_verified ? 'video' : 'candidate',
        href: `https://www.youtube.com/watch?v=${candidate.video_id}`,
        label: candidate.native_verified ? 'YouTube에서 듣기' : '수집 영상 확인 (미검수)'};
    }
    return youtubeTrackDestination({...track, youtube_video_id: null, youtube_match_status: null});
  }
  if (track.youtube_match_status === 'VERIFIED' && typeof track.youtube_video_id === 'string' &&
      /^[A-Za-z0-9_-]{11}$/.test(track.youtube_video_id)) {
    const url = new URL('https://www.youtube.com/watch');
    url.searchParams.set('v', track.youtube_video_id);
    return {kind: 'video', href: url.href, label: 'YouTube에서 듣기'};
  }
  const query = [track.track_name, track.artists_name].map(value => value.trim()).filter(Boolean).join(' ');
  if (!query) return null;
  const url = new URL('https://www.youtube.com/results');
  url.searchParams.set('search_query', query);
  return {kind: 'search', href: url.href, label: 'YouTube에서 찾기'};
}

/** Ignore arbitrary remote URLs; a native playlist must be an official playlist page. */
export function nativeYoutubePlaylistUrl(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  try {
    const input = new URL(value);
    if (input.protocol !== 'https:' || !['www.youtube.com', 'youtube.com', 'm.youtube.com'].includes(input.hostname) ||
        input.port || input.username || input.password || input.pathname !== '/playlist') return null;
    const id = input.searchParams.get('list');
    if (!id || !/^[A-Za-z0-9_-]{10,100}$/.test(id)) return null;
    const output = new URL('https://www.youtube.com/playlist');
    output.searchParams.set('list', id);
    return output.href;
  } catch { return null; }
}

/** Native temporary queue observed in browser; not an account-saved playlist. */
export function youtubeTemporaryQueueUrl(tracks: YoutubeTrackFields[]): string | null {
  if (!tracks.length) return null;
  const ids: string[] = [];
  for (const track of tracks) {
    if (track.youtube_match_status !== 'VERIFIED' || typeof track.youtube_video_id !== 'string' ||
        !/^[A-Za-z0-9_-]{11}$/.test(track.youtube_video_id)) return null;
    ids.push(track.youtube_video_id);
  }
  // Do not shrink or silently deduplicate a playlist with conflicting mappings.
  if (new Set(ids).size !== ids.length) return null;
  return `https://www.youtube.com/watch_videos?video_ids=${ids.join(',')}`;
}

export function stopMusicEventPropagation(event: {stopPropagation: () => void}): void {
  event.stopPropagation();
}
