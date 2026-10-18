/** Review-only single-video session. It cannot create a verified mapping or queue. */
export class PreviewSession {
  constructor(track, videoId, token) {
    if (track?.occasion_status !== 'GENERAL' || !/^[A-Za-z0-9_-]{11}$/.test(videoId)) throw new Error('GENERAL 곡과 실제 영상 ID만 사전 시험할 수 있습니다.');
    this.token = token;
    this.trackId = track.track_id;
    this.trackName = track.track_name;
    this.artists = track.artists;
    this.videoId = videoId;
    this.duration = null;
    this.mapping_status = 'UNVERIFIED_PREVIEW';
    this.state = 'LOADING';
  }

  observe(code, loadedId, duration) {
    if (code === 1 && loadedId !== this.videoId) throw new Error('기대 영상과 다른 사전 시험입니다.');
    if (code === 1 && Number.isFinite(duration) && duration > 0) this.duration = duration;
    this.state = ({0: 'FINISHED', 1: 'PLAYING', 2: 'PAUSED', 3: 'BUFFERING', 5: 'CUED'})[code] ?? this.state;
    return this.state;
  }
}

/** App-owned queue. Every attempt has its own visible player instance. */
export class QueueController {
  constructor(adapter, emit = () => {}) {
    this.adapter = adapter;
    this.emit = emit;
    this.items = [];
    this.index = 0;
    this.attempt = 0;
    this.state = 'IDLE';
    this.pending = false;
    this.consumed = false;
    this.played = false;
    this.version = null;
    this.failureCount = 0;
  }

  record(event, detail = {}) {
    this.emit({recorded_at: new Date().toISOString(), event, queue_version: this.version,
      attempt_id: this.attempt, source_position: this.items[this.index]?.source_position,
      track_id: this.items[this.index]?.track_id,
      youtube_video_id: this.items[this.index]?.mapping?.youtube_video_id,
      occasion_policy_version: this.items[this.index]?.source_fields?.occasion_policy_version,
      occasion_decision_version: this.items[this.index]?.source_fields?.occasion_decision_version,
      app_state: this.state, ...detail});
  }

  snapshot() {
    return {state: this.state, index: this.index, attempt: this.attempt, pending: this.pending,
      count: this.items.length, failureCount: this.failureCount, current: this.items[this.index],
      next: this.items[this.index + 1], version: this.version};
  }

  prepare(queue, items, {index = 0, startSeconds = 0} = {}) {
    if (!items.length || items.some(item => item.occasion_status !== 'GENERAL' ||
      !item.playable || item.mapping?.match_status !== 'VERIFIED' ||
      !/^[A-Za-z0-9_-]{11}$/.test(item.mapping.youtube_video_id) ||
      !Number.isFinite(item.mapping.platform_duration_seconds) || item.mapping.platform_duration_seconds <= 0)) {
      throw new Error('GENERAL 및 영상 매핑 확정을 통과한 곡만 재생할 수 있습니다.');
    }
    if (!Number.isInteger(index) || index < 0 || index >= items.length || !Number.isFinite(startSeconds) || startSeconds < 0) throw new Error('복원할 위치가 올바르지 않습니다.');
    this.stop();
    this.items = structuredClone(items);
    this.version = queue.queue_version;
    this.failureCount = 0;
    this.load(index, false, startSeconds);
  }

  load(index, autoplay, startSeconds = 0) {
    this.index = index;
    this.attempt += 1;
    this.pending = true;
    this.consumed = false;
    this.played = false;
    this.state = 'LOADING';
    this.record('LOAD_REQUEST', {autoplay});
    try {
      this.adapter.load(this.items[index], this.attempt, autoplay, startSeconds);
    } catch (error) {
      this.hold('PLAYER_CREATE_FAILED');
    }
  }

  start() {
    if (!['CUED', 'PAUSED', 'WAITING_FOR_USER', 'STOPPED'].includes(this.state) || !this.items.length) return;
    this.state = 'LOADING';
    this.pending = true;
    this.record('USER_START');
    this.adapter.play();
  }

  retry() {
    if (this.state !== 'ERROR_HOLD' || !this.items.length) return;
    // Recreate and cue. A second explicit click initiates playback after readiness.
    this.load(this.index, false);
  }

  pause() {
    if (!['PLAYING', 'BUFFERING'].includes(this.state)) return;
    this.state = 'PAUSED';
    this.record('USER_PAUSE');
    this.adapter.pause();
  }

  stop() {
    if (!this.items.length) return;
    this.state = 'STOPPED';
    this.pending = false;
    this.record('USER_STOP');
    // Cue this existing video after stop so replay needs no asynchronous re-creation.
    this.adapter.stop();
  }

  hold(reason) {
    this.state = 'ERROR_HOLD';
    this.pending = false;
    this.record('HOLD', {reason});
    this.adapter.pause();
  }

  advanceOnce(reason, expectedAttempt = this.attempt, direction = 1) {
    if (expectedAttempt !== this.attempt || this.pending || this.consumed ||
      ['IDLE', 'STOPPED', 'ERROR_HOLD', 'FINISHED'].includes(this.state)) return false;
    if (reason === 'ENDED' && !this.played) return false;
    this.consumed = true;
    this.pending = true;
    this.record('ADVANCE', {reason, direction});
    const next = this.index + direction;
    if (next >= this.items.length) {
      this.state = 'FINISHED';
      this.pending = false;
      this.record('QUEUE_FINISHED');
    } else if (next < 0) {
      this.load(0, false);
    } else {
      this.load(next, true);
    }
    return true;
  }

  onState(code, attempt, loadedId, actualState = code) {
    if (attempt !== this.attempt) return; // Callback is bound to that player's creation.
    if (this.state === 'STOPPED' || this.state === 'FINISHED' || this.state === 'ERROR_HOLD') return;
    const expectedId = this.items[this.index]?.mapping.youtube_video_id;
    if ((code === 1 || code === 0) && (loadedId !== expectedId || actualState !== code)) {
      this.hold('PLAYER_ID_OR_STATE_MISMATCH');
      return;
    }
    this.record('PLAYER_STATE', {player_state: code});
    if (code === 5) {
      this.state = 'CUED';
      this.pending = false;
    } else if (code === 1) {
      this.state = 'PLAYING';
      this.pending = false;
      this.played = true;
    } else if (code === 2) {
      this.state = 'PAUSED';
      this.pending = false;
    } else if (code === 3) {
      this.state = 'BUFFERING';
    } else if (code === 0 && this.played) {
      this.pending = false;
      this.advanceOnce('ENDED', attempt);
    }
  }

  onBlocked(attempt) {
    if (attempt !== this.attempt || ['STOPPED', 'FINISHED', 'ERROR_HOLD'].includes(this.state)) return;
    this.state = 'WAITING_FOR_USER';
    this.pending = false;
    this.record('AUTOPLAY_BLOCKED');
  }

  waitForUser(reason, attempt = this.attempt) {
    if (attempt !== this.attempt || ['STOPPED', 'FINISHED', 'ERROR_HOLD'].includes(this.state)) return;
    this.state = 'WAITING_FOR_USER';
    this.pending = false;
    this.record('USER_ACTION_REQUIRED', {reason});
  }

  onError(code, attempt) {
    if (attempt !== this.attempt || ['STOPPED', 'FINISHED', 'ERROR_HOLD'].includes(this.state)) return;
    this.record('PLAYER_ERROR', {error_code: code});
    if ([2, 100, 101, 150].includes(code)) {
      this.failureCount += 1;
      this.pending = false;
      this.state = 'ITEM_FAILED';
      this.advanceOnce(`ERROR_${code}`, attempt);
    } else {
      this.hold(code === 153 ? 'CLIENT_IDENTITY_ERROR_153' : `PLAYER_ERROR_${code}`);
    }
  }

  exportState() {
    return {queue_version: this.version, index: this.index,
      track_ids: this.items.map(item => item.track_id), state: this.state,
      youtube_video_id: this.items[this.index]?.mapping?.youtube_video_id};
  }
}
