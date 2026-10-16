export type PlaybackTrack = {track_id: string; track_name: string; artists_name: string};
export type PlaybackCandidate = {video_id: string; title: string; channel_title: string; duration_seconds: number; source: 'CATALOG_MAPPING' | 'YOUTUBE_API' | 'MAPPING_REGISTRY'; match_status?: 'VERIFIED' | 'CANDIDATE'};
export type PlaybackResolution = {track_id: string; status: 'READY' | 'SEARCH_UNAVAILABLE' | 'NO_MATCH' | 'MAPPING_REQUIRED'; candidates: PlaybackCandidate[]; reason?: 'UNMAPPED' | 'PENDING' | 'BLOCKED'; message?: string};
export type PlaybackPhase = 'idle' | 'resolving' | 'loading' | 'playing' | 'paused' | 'blocked' | 'unavailable' | 'complete' | 'error';
export type PlaybackSnapshot = {index: number; phase: PlaybackPhase; message: string; candidate: PlaybackCandidate | null; skipped: {track_id: string; track_name: string; reason: string}[]; playedTrackIds: string[]};
export type PlaybackAdapter = {load: (videoId: string) => void; play: () => void; pause: () => void};
export type PlaybackResolver = (trackId: string, excludedVideoIds: string[], signal: AbortSignal) => Promise<PlaybackResolution>;

// The controller only advances on a real ENDED event, explicit navigation, or a
// recorded unavailable recording. A blocked autoplay never silently skips a song.
export class YoutubePlaybackController {
  private state: PlaybackSnapshot = {index: 0, phase: 'idle', message: '', candidate: null, skipped: [], playedTrackIds: []};
  private request: AbortController | null = null;
  private sequence = 0;
  private stopped = false;
  private blockReason: string | null = null;
  private candidates: PlaybackCandidate[] = [];
  private attempted: string[] = [];
  private requests = 0;
  private began = false;

  constructor(private tracks: PlaybackTrack[], private adapter: PlaybackAdapter, private resolve: PlaybackResolver, private publish: (state: PlaybackSnapshot) => void) {}

  snapshot() {return {...this.state, skipped: [...this.state.skipped], playedTrackIds: [...this.state.playedTrackIds]};}

  private update(patch: Partial<PlaybackSnapshot>) {
    if (this.stopped) return;
    this.state = {...this.state, ...patch};
    this.publish(this.snapshot());
  }

  private invalidate() {
    this.sequence += 1;
    this.request?.abort();
    this.request = null;
    this.began = false;
  }

  async start(index = 0) {
    if (this.stopped || this.blockReason) return;
    this.invalidate();
    if (index >= this.tracks.length) {this.finish(); return;}
    this.adapter.pause();
    this.candidates = []; this.attempted = []; this.requests = 0;
    this.update({index: Math.max(0, index), candidate: null, phase: 'resolving', message: '이 곡의 재생 가능한 영상을 찾고 있어요.'});
    await this.findCandidates();
  }

  private async findCandidates() {
    const track = this.tracks[this.state.index];
    if (!track || this.stopped || this.blockReason) return;
    const sequence = this.sequence;
    const controller = new AbortController(); this.request = controller; this.requests += 1;
    this.update({phase: 'resolving', message: '이 곡의 재생 가능한 영상을 찾고 있어요.'});
    try {
      const result = await this.resolve(track.track_id, [...this.attempted], controller.signal);
      if (controller.signal.aborted || sequence !== this.sequence || this.stopped || this.blockReason) return;
      if (result.track_id !== track.track_id) throw new Error('곡의 영상 응답이 일치하지 않아요. 다시 확인해 주세요.');
      if (result.status === 'MAPPING_REQUIRED') {
        await this.skipUnavailable(result.message || (result.reason === 'BLOCKED' ? '등록한 영상이 차단되어 다른 영상 연결이 필요해요.' : result.reason === 'PENDING' ? '등록한 영상의 원곡·삽입 재생 검수를 기다리고 있어요.' : '이 곡의 영상이 아직 연결되지 않았어요.'));
        return;
      }
      if (result.status === 'SEARCH_UNAVAILABLE') {
        if (this.attempted.length) {
          await this.skipUnavailable('확인된 영상은 삽입 재생을 허용하지 않고, 대체 영상 검색도 현재 연결할 수 없어요.');
          return;
        }
        this.update({phase: 'error', candidate: null, message: result.message || '영상 검색 연결을 확인할 수 없어요. 연결을 다시 확인해 주세요.'});
        return;
      }
      this.candidates = result.candidates.filter((candidate, index, all) => /^[A-Za-z0-9_-]{11}$/.test(candidate.video_id) && !this.attempted.includes(candidate.video_id) && all.findIndex(item => item.video_id === candidate.video_id) === index);
      if (result.status !== 'READY' || !this.candidates.length) {await this.skipUnavailable(result.message || '원곡과 일치하는 재생 가능한 영상을 찾지 못했어요.'); return;}
      this.loadNextCandidate();
    } catch (error) {
      if (!controller.signal.aborted && sequence === this.sequence) this.update({phase: 'error', candidate: null, message: error instanceof Error ? error.message : '영상 연결을 다시 확인해 주세요.'});
    }
  }

  private loadNextCandidate() {
    if (this.stopped || this.blockReason) return;
    const candidate = this.candidates.shift();
    if (!candidate || this.attempted.length >= 5) {void this.skipUnavailable('이 곡의 영상이 삭제되었거나 삽입 재생을 허용하지 않아요.'); return;}
    this.attempted.push(candidate.video_id); this.began = false;
    this.update({candidate, phase: 'loading', message: 'YouTube 영상을 불러오고 있어요.'});
    this.adapter.load(candidate.video_id);
  }

  private async skipUnavailable(reason: string) {
    const track = this.tracks[this.state.index];
    const skipped = this.state.skipped.filter(item => item.track_id !== track.track_id);
    this.update({skipped: [...skipped, {track_id: track.track_id, track_name: track.track_name, reason}]});
    await this.start(this.state.index + 1);
  }

  private finish() {
    this.adapter.pause();
    const count = this.state.playedTrackIds.length;
    this.update({candidate: null, phase: count ? 'complete' : 'unavailable', message: count ? `선곡표의 마지막 곡까지 진행했어요. 재생하지 못한 곡 ${this.state.skipped.length}곡을 확인해 주세요.` : '이 선곡표에서 재생 가능한 영상을 찾지 못했어요. 아래 누락 내역과 연결 설정을 확인해 주세요.'});
  }

  onPlayerState(value: number) {
    if (this.stopped) return;
    if (this.blockReason) {this.adapter.pause(); return;}
    if (!this.state.candidate) return;
    if (value === 1) {
      this.began = true;
      const trackId = this.tracks[this.state.index].track_id;
      this.update({phase: 'playing', message: 'YouTube에서 재생 중이에요.', playedTrackIds: [...new Set([...this.state.playedTrackIds, trackId])]});
    } else if (value === 0 && this.began) {
      this.began = false;
      void this.start(this.state.index + 1);
    } else if (value === 2 && this.state.phase === 'playing') {
      this.update({phase: 'paused', message: '일시 정지했어요.'});
    }
  }

  onPlayerError(code: number) {
    if (this.stopped || this.blockReason || !this.state.candidate) return;
    this.began = false;
    if ([2, 100, 101, 150].includes(code)) {
      if (this.candidates.length && this.attempted.length < 5) this.loadNextCandidate();
      else if (this.requests < 2 && this.attempted.length < 5) void this.findCandidates();
      else void this.skipUnavailable(`YouTube 삽입 재생 불가(오류 ${code})로 이 곡을 건너뛰었어요.`);
    } else {
      this.adapter.pause();
      this.update({phase: 'error', message: code === 153 ? 'YouTube가 이 페이지의 출처를 확인하지 못했어요(153). 대시보드를 새로고침해 주세요.' : `YouTube 플레이어 연결을 확인해 주세요(오류 ${code}). 이 곡은 자동으로 건너뛰지 않았어요.`});
    }
  }

  onAutoplayBlocked() {
    if (!this.blockReason && this.state.candidate && !this.stopped) this.update({phase: 'blocked', message: '브라우저가 자동 재생을 보류했어요. [재생]을 한 번 눌러 주세요.'});
  }

  onLoadingDelayed() {
    if (!this.blockReason && !this.stopped && this.state.phase === 'loading') this.update({message: '재생 준비가 길어지고 있어요. 필요하면 [재생]을 눌러 주세요.'});
  }

  setBlocked(reason: string | null) {
    if (reason === this.blockReason || this.stopped) return;
    this.blockReason = reason;
    if (reason) {
      const pending = this.state.phase === 'resolving';
      this.invalidate(); this.adapter.pause();
      this.update({phase: 'blocked', message: reason, ...(pending ? {candidate: null} : {})});
    } else this.update({phase: 'paused', message: '변경 상태를 확인했어요. [재생]을 누르면 이어서 재생해요.'});
  }

  play() {
    if (this.stopped || this.blockReason) return;
    if (!this.state.candidate || ['complete', 'unavailable'].includes(this.state.phase)) {void this.start(this.state.phase === 'complete' || this.state.phase === 'unavailable' ? 0 : this.state.index); return;}
    this.update({phase: 'loading', message: '재생을 시작하고 있어요.'}); this.adapter.play();
  }
  pause() {if (!this.stopped) {this.adapter.pause(); this.update({phase: 'paused', message: '일시 정지했어요.'});}}
  previous() {if (!this.blockReason) void this.start(Math.max(0, this.state.index - 1));}
  next() {if (!this.blockReason) void this.start(this.state.index + 1);}
  retry() {if (!this.blockReason) void this.start(this.state.index);}
  destroy() {this.invalidate(); this.adapter.pause(); this.stopped = true;}
}
