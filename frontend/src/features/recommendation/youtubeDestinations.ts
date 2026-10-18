export type YoutubeTrackFields = {
  track_name: string;
  artists_name: string;
  youtube_video_id?: string | null;
  youtube_match_status?: string | null;
};

export type YoutubeDestination = {kind: 'video' | 'search'; href: string; label: string};

/** Public navigation only. This does not authenticate, enqueue or change feedback. */
export function youtubeTrackDestination(track: YoutubeTrackFields): YoutubeDestination | null {
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
