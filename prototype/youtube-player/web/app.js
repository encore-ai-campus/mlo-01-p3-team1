import {QueueController, PreviewSession} from './queue.mjs';

const $ = id => document.getElementById(id);
let sessionId = globalThis.crypto?.randomUUID?.() ?? `demo-${Date.now()}`;
try { sessionId = sessionStorage.getItem('youtube-demo-session') ?? sessionId; sessionStorage.setItem('youtube-demo-session', sessionId); } catch { /* memory-only logging remains available */ }
let config, playlist, selected, player, playerAttempt = 0, apiPromise, savedResume, preview;
let logs = [];
const logKey = `youtube-demo-log:${sessionId}`;
const restoreKey = 'youtube-demo-restore-v1';
try { const savedLogs = JSON.parse(sessionStorage.getItem(logKey) ?? '[]'); if (Array.isArray(savedLogs)) logs = savedLogs; } catch { /* preserve new memory log */ }

function message(text, id = 'notice') { $(id).textContent = text; }

async function request(path, options = {}) {
  const response = await fetch(path, {...options, headers: {...(options.headers ?? {}), ...(config ? {'X-Local-Nonce': config.nonce} : {})}});
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error ?? '요청에 실패했습니다.');
  return payload;
}

function persistLog(record) {
  logs.push({...record, demo_session_id: sessionId});
  try {
    sessionStorage.setItem(logKey, JSON.stringify(logs));
    saveResume();
    $('log-status').textContent = `${logs.length}개 이벤트를 브라우저에 보관 중입니다. 시험 종료 전 파일로 내보내 주세요.`;
  } catch {
    $('log-status').textContent = `브라우저 저장에 실패했습니다. ${logs.length}개 메모리 이벤트를 지금 내보내 주세요.`;
  }
  renderPlayback();
}

function saveResume() {
  if (preview) return;
  const state = controller.exportState();
  const seconds = typeof player?.getCurrentTime === 'function' && currentId(player) === state.youtube_video_id ? player.getCurrentTime() : 0;
  localStorage.setItem(restoreKey, JSON.stringify({...state, weather: playlist?.weather, position_seconds: Number.isFinite(seconds) && seconds > 0 ? seconds : 0}));
}

function loadAPI() {
  if (globalThis.YT?.Player) return Promise.resolve();
  if (apiPromise) return apiPromise;
  apiPromise = new Promise((resolve, reject) => {
    globalThis.onYouTubeIframeAPIReady = resolve;
    const script = document.createElement('script');
    script.src = 'https://www.youtube.com/iframe_api';
    script.onerror = () => { apiPromise = null; reject(new Error('YouTube 플레이어를 읽지 못했습니다. 네트워크를 확인해 주세요.')); };
    document.head.append(script);
  });
  return apiPromise;
}

function currentId(target) {
  try { return new URL(target.getVideoUrl()).searchParams.get('v'); } catch { return null; }
}

function playerVisible() {
  const box = $('player-shell').getBoundingClientRect();
  if (document.hidden || box.width <= 0 || box.height <= 0) return false;
  const width = Math.max(0, Math.min(box.right, innerWidth) - Math.max(0, box.left));
  const height = Math.max(0, Math.min(box.bottom, innerHeight) - Math.max(0, box.top));
  return width * height > box.width * box.height / 2;
}

const adapter = {
  async load(item, attempt, autoplay, startSeconds = 0) {
    preview = null;
    $('preview-start').disabled = true;
    $('preview-stop').disabled = true;
    playerAttempt = attempt;
    if (player) { player.destroy(); player = null; }
    $('player-shell').replaceChildren();
    const holder = document.createElement('div');
    holder.id = `youtube-attempt-${attempt}`;
    $('player-shell').append(holder);
    const readyTimeout = setTimeout(() => {
      if (playerAttempt === attempt && controller.state === 'LOADING') controller.hold('PLAYER_READY_TIMEOUT');
    }, 30000);
    try {
      await loadAPI();
      if (attempt !== controller.attempt || controller.state !== 'LOADING') { clearTimeout(readyTimeout); return; }
      // A new visible instance per attempt makes target + captured attempt meaningful.
      const instance = new YT.Player(holder.id, {
        width: 640, height: 340,
        playerVars: {origin: location.origin, enablejsapi: 1, controls: 1, playsinline: 1, autoplay: 0},
        events: {
          onReady(event) {
            clearTimeout(readyTimeout);
            if (attempt !== playerAttempt || event.target !== player || controller.state !== 'LOADING') return;
            const iframe = event.target.getIframe();
            iframe.setAttribute('allow', 'autoplay; encrypted-media; fullscreen; picture-in-picture');
            iframe.setAttribute('referrerpolicy', 'strict-origin-when-cross-origin');
            const request = {videoId: item.mapping.youtube_video_id, startSeconds};
            if (autoplay && playerVisible()) event.target.loadVideoById(request);
            else {
              event.target.cueVideoById(request);
              if (autoplay) controller.waitForUser('PLAYER_NOT_VISIBLE', attempt);
            }
          },
          onStateChange(event) {
            if (attempt !== playerAttempt || event.target !== player) return;
            controller.onState(event.data, attempt, currentId(event.target), event.target.getPlayerState());
            if (event.data === YT.PlayerState.PLAYING) {
              const duration = event.target.getDuration();
              if (duration > 0 && Number.isFinite(duration)) controller.record('PLATFORM_DURATION_OBSERVED', {platform_duration_seconds: duration, duration_source: 'IFRAME_PLAYER'});
            }
          },
          onError(event) {
            clearTimeout(readyTimeout);
            if (attempt === playerAttempt && event.target === player) controller.onError(event.data, attempt);
          },
          onAutoplayBlocked(event) {
            clearTimeout(readyTimeout);
            if (attempt === playerAttempt && event.target === player) controller.onBlocked(attempt);
          },
        },
      });
      player = instance;
    } catch (error) {
      clearTimeout(readyTimeout);
      if (attempt === controller.attempt) { controller.hold('PLAYER_LOAD_FAILED'); message(error.message); }
    }
  },
  play() {
    if (typeof player?.playVideo !== 'function') { controller.hold('PLAYER_NOT_READY'); return; }
    $('player-shell').scrollIntoView({block: 'center'});
    player.playVideo();
  },
  pause() { if (typeof player?.pauseVideo === 'function') player.pauseVideo(); },
  stop() {
    if (typeof player?.stopVideo !== 'function') return;
    const id = controller.items[controller.index]?.mapping.youtube_video_id;
    player.stopVideo();
    if (id) player.cueVideoById(id);
  },
};

const controller = new QueueController(adapter, persistLog);

function renderPlayback() {
  const state = controller.snapshot();
  $('player-status').textContent = `${state.state} · ${state.count ? `${state.index + 1}/${state.count}` : '준비 전'} · 실패 ${state.failureCount}`;
  $('current').textContent = state.current ? `${state.current.source_position}. ${state.current.track_name} / ${state.current.artists}${state.next ? ` → 다음: ${state.next.track_name}` : ''}` : '아직 준비한 재생 큐가 없습니다.';
  $('start').disabled = !['CUED', 'PAUSED', 'WAITING_FOR_USER', 'STOPPED'].includes(state.state);
  $('pause').disabled = !['PLAYING', 'BUFFERING'].includes(state.state);
  const canMove = state.count && !state.pending && !['STOPPED', 'ERROR_HOLD', 'FINISHED', 'IDLE'].includes(state.state);
  $('next').disabled = !canMove;
  $('previous').disabled = !canMove;
  $('stop').disabled = !state.count || state.state === 'STOPPED';
  $('retry').disabled = state.state !== 'ERROR_HOLD';
  if (preview) {
    for (const id of ['start', 'pause', 'previous', 'next', 'stop', 'retry']) $(id).disabled = true;
    $('player-status').textContent = 'UNVERIFIED_PREVIEW · 검수 전용 단일 영상 · 자동 다음 없음';
    $('current').textContent = `검수 중: ${preview.trackName} / ${preview.artists}`;
  }
  if (state.state === 'WAITING_FOR_USER') message('자동 재생이 차단되었습니다. 같은 곡에서 [재생 시작 / 재개]를 눌러 주세요.');
  if (state.state === 'ERROR_HOLD') message('재생이 보류되었습니다. 오류153은 HTTP 출처·Referer를 확인하고, 확인 후 [오류 후 다시 준비]를 눌러 주세요.');
}

function selectTrack(track) {
  selected = track;
  $('selected').textContent = `${track.source_position}. ${track.track_name} / ${track.artists} · ${track.album_name}`;
  const query = `${track.track_name} ${track.artists} ${track.album_name}`;
  $('manual-search').href = `https://www.youtube.com/results?search_query=${encodeURIComponent(query)}`;
  const mapping = track.mapping ?? {};
  $('video-id').value = mapping.youtube_video_id ?? '';
  $('video-title').value = mapping.youtube_title ?? '';
  $('video-channel').value = mapping.youtube_channel ?? '';
  $('video-duration').value = mapping.platform_duration_seconds ?? '';
  $('reviewer').value = mapping.verified_by ?? '';
  $('verification-note').value = mapping.verification_note ?? '';
  $('confirmed').checked = false;
  $('api-search').disabled = !config?.search_enabled || track.occasion_status !== 'GENERAL';
  $('candidates').replaceChildren();
  $('mapping-form').querySelector('button[type=submit]').disabled = track.occasion_status !== 'GENERAL';
  document.querySelectorAll('#tracks tr').forEach(row => row.classList.toggle('selected', row.dataset.trackId === track.track_id));
}

function renderPlaylist() {
  $('summary').textContent = `${playlist.track_count}곡 · 영상 확정 ${playlist.playable_count}곡 · 보류 ${playlist.track_count - playlist.playable_count}곡 · 원본 ${(playlist.source_total_ms / 60000).toFixed(2)}분 · YouTube ${playlist.platform_total_seconds === null ? '미확정' : (playlist.platform_total_seconds / 60).toFixed(2) + '분'}`;
  $('versions').textContent = `분석 자료: ${playlist.source_readiness} | 큐 ${playlist.queue_version.slice(0, 12)} | CSV ${playlist.source_csv_sha256.slice(0, 12)} | 시즌 ${playlist.occasion_policy_versions.join(', ')}`;
  const tbody = $('tracks');
  tbody.replaceChildren();
  for (const track of playlist.tracks) {
    const row = document.createElement('tr');
    row.dataset.trackId = track.track_id;
    const values = [track.source_position, `${track.track_name} / ${track.artists}`, track.occasion_status, track.mapping?.match_status ?? 'UNRESOLVED'];
    for (const value of values) { const td = document.createElement('td'); td.textContent = value; row.append(td); }
    const cell = document.createElement('td'), button = document.createElement('button');
    button.textContent = '매핑 검수'; button.addEventListener('click', () => selectTrack(track));
    cell.append(button); row.append(cell); tbody.append(row);
  }
  const priorId = selected?.track_id;
  selectTrack(playlist.tracks.find(t => t.track_id === priorId) ?? playlist.tracks[0]);
  $('restore').disabled = !savedResume || savedResume.queue_version !== playlist.queue_version || savedResume.state === 'FINISHED';
}

async function refresh() {
  try {
    const result = await request(`/api/playlists/${$('weather').value}`);
    playlist = result;
    renderPlaylist();
    message('원본 순서를 보존했습니다. GENERAL 곡의 실제 영상을 확인하고 매핑을 확정해 주세요.');
  } catch (error) { message(error.message); }
}

function prepare(mode) {
  try {
    if (!playlist) throw new Error('선곡표를 먼저 불러와 주세요.');
    const items = mode === 'one' ? [selected] : mode === 'five' ? playlist.tracks.slice(0, 5) : playlist.tracks;
    if (mode === 'five' && items.length < 5) throw new Error('앞 5곡 시험에 필요한 곡이 부족합니다.');
    if (items.some(item => !item?.playable)) throw new Error('선택 범위의 모든 곡이 GENERAL과 영상 매핑 확정을 통과해야 합니다. 미확인 곡을 조용히 건너뛰지 않습니다.');
    if (mode === 'all' && (playlist.source_total_ms < 176 * 60000 || playlist.source_total_ms > 184 * 60000)) throw new Error('전체 시험은 원본 합176~184분인 일반곡 선곡표가 필요합니다.');
    controller.prepare(playlist, items);
    message(`${items.length}곡 시험 큐를 고정했습니다. CUED가 표시되면 [재생 시작 / 재개]를 눌러 주세요.`);
  } catch (error) { message(error.message); }
}

function videoIdFromInput(value) {
  const input = value.trim();
  if (/^[A-Za-z0-9_-]{11}$/.test(input)) return input;
  try {
    const url = new URL(input);
    if (!['youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtu.be'].includes(url.hostname)) return '';
    const id = url.hostname === 'youtu.be' ? url.pathname.slice(1) : url.searchParams.get('v');
    return /^[A-Za-z0-9_-]{11}$/.test(id ?? '') ? id : '';
  } catch { return ''; }
}

async function preparePreview() {
  const videoId = videoIdFromInput($('video-id').value);
  if (selected?.occasion_status !== 'GENERAL' || !videoId) {
    message('GENERAL 곡을 선택하고 실제 영상 URL 또는 ID를 입력해 주세요.', 'preview-status');
    return;
  }
  controller.stop();
  playerAttempt = `preview-${Date.now()}`;
  const token = playerAttempt;
  if (player) { player.destroy(); player = null; }
  preview = new PreviewSession(selected, videoId, token);
  $('confirmed').checked = false;
  $('preview-start').disabled = true;
  $('preview-stop').disabled = false;
  renderPlayback();
  message('미확정 영상 검수용 플레이어를 준비합니다. 일반 큐와 분리된 단일 시험입니다.', 'preview-status');
  $('player-shell').replaceChildren();
  const holder = document.createElement('div'); holder.id = `preview-${Date.now()}`;
  $('player-shell').append(holder);
  try {
    await loadAPI();
    if (playerAttempt !== token) return;
    const instance = new YT.Player(holder.id, {
      width: 640, height: 340,
      playerVars: {origin: location.origin, enablejsapi: 1, controls: 1, autoplay: 0, playsinline: 1},
      events: {
        onReady(event) {
          if (playerAttempt !== token || event.target !== player) return;
          event.target.getIframe().setAttribute('allow', 'autoplay; encrypted-media; fullscreen; picture-in-picture');
          event.target.getIframe().setAttribute('referrerpolicy', 'strict-origin-when-cross-origin');
          event.target.cueVideoById(videoId);
        },
        onStateChange(event) {
          if (playerAttempt !== token || event.target !== player) return;
          try { preview.observe(event.data, currentId(event.target), event.target.getDuration()); }
          catch { event.target.pauseVideo(); message('기대 영상과 달라 사전 시험을 중단했습니다.', 'preview-status'); return; }
          if (event.data === 5 || event.data === 2) $('preview-start').disabled = false;
          if (event.data === 1) {
            if (currentId(event.target) !== videoId) { event.target.pauseVideo(); message('기대 영상과 달라 사전 시험을 중단했습니다.', 'preview-status'); return; }
            const duration = preview.duration;
            if (duration) {
              preview.duration = duration;
              if (selected?.track_id === preview.trackId && videoIdFromInput($('video-id').value) === videoId) $('video-duration').value = duration;
            }
            message(`검수용 미확정 영상 재생 중 · 관측 길이 ${duration ?? '확인 중'}초. 원곡·버전을 직접 대조한 뒤 별도로 확정 저장해 주세요.`, 'preview-status');
          }
          if (event.data === 0) {
            $('preview-start').disabled = false;
            message('검수용 단일 영상 시험이 끝났습니다. 자동 다음 곡과 자동 확정은 없습니다.', 'preview-status');
          }
          persistLog({recorded_at: new Date().toISOString(), event: 'MAPPING_PREVIEW_STATE', preview_id: token, track_id: preview.trackId, youtube_video_id: videoId, player_state: event.data, platform_duration_seconds: preview.duration ?? null, mapping_status: 'UNVERIFIED_PREVIEW'});
        },
        onError(event) {
          if (playerAttempt !== token || event.target !== player) return;
          $('preview-start').disabled = true;
          message(`검수용 영상 오류 ${event.data}. ${event.data === 153 ? 'HTTP 출처와 Referer를 확인해 주세요.' : '이 영상의 상태와 삽입 허용 여부를 확인해 주세요.'} 확정 상태는 바꾸지 않습니다.`, 'preview-status');
          persistLog({recorded_at: new Date().toISOString(), event: 'MAPPING_PREVIEW_ERROR', preview_id: token, track_id: preview.trackId, youtube_video_id: videoId, error_code: event.data, mapping_status: 'UNVERIFIED_PREVIEW'});
        },
        onAutoplayBlocked(event) {
          if (playerAttempt !== token || event.target !== player) return;
          $('preview-start').disabled = false;
          message('검수용 재생이 차단되었습니다. [사전 시험 재생] 또는 플레이어의 시작 버튼을 눌러 주세요.', 'preview-status');
        },
      },
    });
    player = instance;
  } catch (error) { message(error.message, 'preview-status'); }
}

async function saveMappings(mappings) {
  if (!playlist) throw new Error('목록을 먼저 불러와 주세요.');
  await request('/api/mappings/import', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({mappings, expected_mapping_version: playlist.mapping_version})});
  await refresh();
  message('영상 매핑을 저장했습니다. 실행 중인 큐는 유지되며 새로 준비하는 큐에 적용됩니다.', 'mapping-message');
}

function download(name, value, kind) {
  const url = URL.createObjectURL(new Blob([value], {type: kind}));
  const anchor = document.createElement('a'); anchor.href = url; anchor.download = name;
  document.body.append(anchor); anchor.click(); anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

$('mapping-form').addEventListener('submit', async event => {
  event.preventDefault();
  if (!selected || !$('confirmed').checked) return;
  const id = videoIdFromInput($('video-id').value);
  if (!id) { message('실제 YouTube 영상 URL 또는 11자 ID를 확인해 주세요.', 'mapping-message'); return; }
  const record = {track_id: selected.track_id, youtube_video_id: id, youtube_title: $('video-title').value.trim(), youtube_channel: $('video-channel').value.trim(), platform_duration_seconds: Number($('video-duration').value), verified_by: $('reviewer').value.trim(), verification_note: $('verification-note').value.trim(), checked_at: new Date().toISOString(), match_method: 'MANUAL_REVIEW', match_status: 'VERIFIED'};
  try { await saveMappings([record]); } catch (error) { message(error.message, 'mapping-message'); }
});
$('preview-prepare').addEventListener('click', preparePreview);
$('preview-start').addEventListener('click', () => {
  if (!preview || playerAttempt !== preview.token || typeof player?.playVideo !== 'function') return;
  $('player-shell').scrollIntoView({block: 'center'});
  player.playVideo();
});
$('preview-stop').addEventListener('click', () => {
  if (typeof player?.pauseVideo === 'function') player.pauseVideo();
  message('검수용 단일 영상 시험을 일시정지했습니다. 매핑은 미확정 상태를 유지합니다.', 'preview-status');
});

$('api-search').addEventListener('click', async () => {
  try {
    const result = await request(`/api/youtube/search?track_id=${encodeURIComponent(selected.track_id)}`);
    $('candidates').replaceChildren();
    for (const candidate of result.candidates) {
      const button = document.createElement('button');
      button.textContent = `${candidate.youtube_title} / ${candidate.youtube_channel} (${candidate.platform_duration_seconds}초) · 후보 선택`;
      button.addEventListener('click', () => {
        $('video-id').value = candidate.youtube_video_id;
        $('video-title').value = candidate.youtube_title;
        $('video-channel').value = candidate.youtube_channel;
        $('video-duration').value = candidate.platform_duration_seconds;
        $('confirmed').checked = false;
        message('검색 후보입니다. 실제 영상과 삽입 재생을 확인한 뒤 사람이 확정해 주세요.', 'mapping-message');
      });
      $('candidates').append(button);
    }
    if (!result.candidates.length) message('자동 확인 가능한 후보가 없습니다. 수동 검색해 주세요.', 'mapping-message');
  } catch (error) { message(error.message, 'mapping-message'); }
});

$('import-file').addEventListener('change', async event => {
  try {
    const file = event.target.files[0];
    if (!file || file.size > 1024 * 1024) throw new Error('1MiB 이하의 JSON 파일을 선택해 주세요.');
    const data = JSON.parse(await file.text());
    await saveMappings(Array.isArray(data) ? data : data.mappings);
  } catch (error) { message(error.message, 'mapping-message'); }
  event.target.value = '';
});
$('export-mappings').addEventListener('click', () => {
  try { download('youtube-mappings.json', JSON.stringify({mappings: playlist.tracks.filter(t => t.mapping).map(t => t.mapping)}, null, 2), 'application/json'); } catch { message('매핑 내보내기에 실패했습니다.', 'mapping-message'); }
});
$('export-log').addEventListener('click', () => {
  try {
    download(`${sessionId}.jsonl`, logs.map(r => JSON.stringify(r)).join('\n') + '\n', 'application/x-ndjson');
    $('log-status').textContent = '다운로드를 요청했습니다. 실제 파일 저장을 확인해 주세요. 메모리 로그는 유지합니다.';
  } catch { $('log-status').textContent = '내보내기에 실패했습니다. 메모리 로그를 유지합니다. 다시 시도해 주세요.'; }
});
$('reload').addEventListener('click', refresh);
$('weather').addEventListener('change', () => { controller.stop(); refresh(); });
$('prepare-five').addEventListener('click', () => prepare('five'));
$('prepare-all').addEventListener('click', () => prepare('all'));
$('prepare-one').addEventListener('click', () => prepare('one'));
$('restore').addEventListener('click', () => {
  try {
    if (savedResume?.queue_version !== playlist?.queue_version || !Array.isArray(savedResume.track_ids)) throw new Error('현재 큐 버전과 이전 기록이 다릅니다. 새로 준비해 주세요.');
    const items = savedResume.track_ids.map(id => playlist.tracks.find(t => t.track_id === id));
    if (items.some(item => !item?.playable) || items[savedResume.index]?.mapping.youtube_video_id !== savedResume.youtube_video_id) throw new Error('복원할 곡·영상이 현재 매핑과 다릅니다.');
    const max = items[savedResume.index].mapping.platform_duration_seconds;
    const seconds = Math.max(0, Math.min(Number(savedResume.position_seconds) || 0, max - 1));
    controller.prepare(playlist, items, {index: savedResume.index, startSeconds: seconds});
    message('이전 위치를 준비했습니다. 버전을 확인한 뒤 [재생 시작 / 재개]를 눌러 주세요.');
  } catch (error) { message(error.message); }
});
$('start').addEventListener('click', () => controller.start());
$('pause').addEventListener('click', () => controller.pause());
$('stop').addEventListener('click', () => controller.stop());
$('next').addEventListener('click', () => controller.advanceOnce('USER_NEXT'));
$('previous').addEventListener('click', () => controller.advanceOnce('USER_PREVIOUS', controller.attempt, -1));
$('retry').addEventListener('click', () => controller.retry());
document.addEventListener('visibilitychange', () => {
  if (!document.hidden) return;
  if (preview && typeof player?.pauseVideo === 'function') player.pauseVideo();
  else controller.pause();
});
window.addEventListener('beforeunload', () => { try { saveResume(); } catch { /* memory data is kept until page closes; export beforehand */ } });

try {
  config = await request('/api/config');
  try { savedResume = JSON.parse(localStorage.getItem(restoreKey) ?? 'null'); }
  catch { message('브라우저 저장소를 읽지 못했습니다. 복원 없이 새 시험을 시작합니다.'); }
  if (savedResume?.weather && [...$('weather').options].some(o => o.value === savedResume.weather)) $('weather').value = savedResume.weather;
  await refresh();
  if (savedResume?.queue_version) message('이전 시험 기록이 있습니다. 같은 버전이면 [이전 위치 복원]을 누른 뒤 시작해 주세요. 자동 재생하지 않습니다.');
} catch (error) { message(`초기화 실패: ${error.message}`); }
