# YouTube 재생 변경 라우팅

- 작성자/담당: Codex YouTube 로컬 재생 구현 / C·B 연결
- 작성일: 2026-10-16
- 수정일: 2026-10-16
- 범위: 외부 연결 X-01/X-02와 구분한 이번 로컬 시험, 영상 매핑·HTTP·공식 플레이어·큐·시험 로그
- 작업 브랜치/기준 커밋: `feature/ad-logic`, `f22f974acb54e8b605f7cb7704f38a55609ffd7f` 이후 미커밋 작업
- 실제 계정 변경·OAuth·공유 DB·광고 환경·커밋/푸시/배포는 이 구현에 포함하지 않습니다.

## 1. 기준에서 코드까지

[AGENTS](../../AGENTS.md)의 2026-10-16 수령 원문 보존·별도 라우팅과 [재생 가이드](music/YouTube_로컬_재생_기획과_구현_가이드.md)의 단일 영상 큐를 적용했습니다. 기획 담당이 단계1에서 대조한 최신 [ON/OFF 후보 가이드](../product/카페_음악_추천_서비스_3차_컬럼_기반_추천_로직_가이드.md)·[공통 계약](../product/3차_공통_개발_계약과_검증_기준.md)을 정본으로 연결합니다. 시즌 판정·목록 생성은 별도 `music_playback` 담당의 산출물을 입력받으며 이 플레이어가 점수나 판정을 다시 만들지 않습니다.

현재 코드의 `backend/manage.py`·`backend/cafe/`는 Django입니다. 최신 문서의 목표 FastAPI로 이미 이식한 것으로 표시하지 않습니다. 이번 [prototype/youtube-player](../../prototype/youtube-player/)는 Python 표준 라이브러리로 격리했으며 기존 Django/FastAPI·인증·DB를 초기 실행 의존성으로 두지 않습니다.

입력은 [general/examples](../../analysis/weather_music_20261016/general/examples/)의 다섯 일반곡 선곡표입니다. 기존 CSV 열을 `source_fields`에 그대로 보존합니다. 원문18개 전체가 확보되었다고 만들거나 누락 값을 생성하지 않으며 `source_readiness=ANALYSIS_ONLY_NOT_READY`를 고정합니다. `GENERAL`은 메타데이터 사전 검사 통과로, 청취·운영 READY와 다릅니다.

## 2. 파일·함수·실제 흐름

| 파일 | 함수·클래스 | 실제 동작과 변경 이유 |
|---|---|---|
| [server.py](../../prototype/youtube-player/server.py) | `utc_now()`, `digest(value)`, `InputError`, `ConflictError` | UTC 시각·불변 버전 계산·입력과 충돌 오류를 분리합니다. |
| 같은 파일 | `PlaylistStore.__init__(data_dir,mapping_file)`, `source(weather)`, `mappings()`, `known_tracks()` | 일반 CSV의 순번·중복·양의 길이를 확인하고 로컬 영상 sidecar를 읽습니다. CSV는 쓰지 않습니다. |
| 같은 파일 | `PlaylistStore.validate_mapping(record,source)`, `import_mappings(payload)` | 원곡 대조·VERIFIED 근거·현재 매핑 버전 검증 후 일괄 원자 교체합니다. 잘못된 일부 항목이 있으면 전체 입력을 저장하지 않습니다. |
| 같은 파일 | `PlaylistStore.playlist(weather)`, `listing()` | 원문 보존·시즌 상태·영상 상태를 결합하고 CSV해시+매핑해시로 큐 버전을 고정합니다. 실제 운영 결과 ID를 만들지 않습니다. |
| 같은 파일 | `iso_duration(value)`, `SearchProvider.__init__(api_key)`, `request(endpoint,parameters)`, `search(source)` | 선택적 공식 검색과 영상 메타데이터 확인. 서버 키만 사용하며 검색 결과는 CANDIDATE입니다. |
| 같은 파일 | `LocalServer.__init__(port,store,search)` | `127.0.0.1`에만 바인딩하고 실행별 nonce를 메모리에 생성합니다. |
| 같은 파일 | `Handler.local_origin()`, `protected(read=False)` | 허용 Host·출처·nonce로 로컬 쓰기/검색을 보호합니다. POST는 Origin 필수, GET 검색은 Origin 없는 브라우저 same-origin 요청을 별도 검증합니다. |
| 같은 파일 | `Handler.headers_for(...)`, `send_json(...)`, `do_GET()`, `do_POST()`, `log_message(...)` | 허용한 정적 파일만 제공하고 CSP·Referer를 설정합니다. 요청 URL/헤더·비밀값을 로그에 출력하지 않습니다. |
| 같은 파일 | `main()` | `--data-dir`, `--mapping-file`, `--port` 인자를 처리하고 서버를 종료합니다. |
| [queue.mjs](../../prototype/youtube-player/web/queue.mjs) | `QueueController.prepare/load/start/retry/pause/stop/hold/advanceOnce/onState/onBlocked/waitForUser/exportState` | GENERAL+VERIFIED+양의 플랫폼 길이의 고정 큐. 종료·다음·항목 오류를 단일 전환 경로로 처리합니다. |
| 같은 파일 | `PreviewSession.constructor/observe` | 미확정 단일 영상 검수. GENERAL+실제 형식 ID가 필요하며 종료 시 자동 다음·자동 VERIFIED가 없습니다. 일반 큐 gate를 완화하지 않습니다. |
| [app.js](../../prototype/youtube-player/web/app.js) | `loadAPI`, `adapter.load/play/pause/stop`, `playerVisible`, `currentId`, `preparePreview` | 공식 삽입 플레이어 생성·ID/상태 확인·매 시도 객체 분리·검수용 단일 시험을 연결합니다. 이전 객체를 먼저 destroy하므로 동시 플레이어는 하나입니다. |
| 같은 파일 | `request/refresh/renderPlaylist/selectTrack/prepare/saveMappings/videoIdFromInput` | 날씨·목록, 수동 검색/후보·검수·JSON 가져오기를 연결합니다. 미확인 항목을 조용히 건너뛰지 않습니다. |
| 같은 파일 | `persistLog/saveResume/download/renderPlayback` 및 버튼 이벤트 | 실행별 브라우저 로그와 버전/곡/영상 대조 복원, JSONL 다운로드를 구현합니다. 실제 파일 저장은 사용자가 확인합니다. |
| [index.html](../../prototype/youtube-player/web/index.html)·[styles.css](../../prototype/youtube-player/web/styles.css) | 로컬 화면·반응형 표시 | 영상 검수, 앞5곡/전체/1곡 큐, 검수용 미확정 preview, 수동 확인과 로그 내보내기를 제공합니다. |

이전에는 실행 코드가 없었습니다. 현재는 키 없는 수동 검수·등록부터 실제 플레이어 호출까지 사용할 수 있는 로컬 도구가 있습니다. 통계·추천·승인·곡 제외·Gemini·광고 이벤트를 재생 조작으로 발생시키지 않습니다.

## 3. API·저장·인증 경계

| 경로 | 입력·응답·순서 |
|---|---|
| `GET /api/config` | 실행 nonce·키 사용 가능 여부·분석 전용 상태. 키·이메일·쿠키를 반환하지 않습니다. |
| `GET /api/playlists` | 다섯 날씨의 곡 수·확정 수·원본 길이. 데이터 미생성은 이유를 표시합니다. |
| `GET /api/playlists/{weather}` | `schema_version`, `queue_version`, `mapping_version`, `source_readiness`, `source_csv_sha256`, 시즌 버전, `tracks`를 반환합니다. 각 곡에 원본값·`source_fields`·시즌 상태·`mapping`·`playable`이 포함됩니다. |
| `POST /api/mappings/import` | `{expected_mapping_version,mappings:[...]}`. 기존 버전과 다르면409, 잘못된 입력422, 외부 출처·nonce 누락403입니다. 기존 가이드의 읽기 전용 서버 제안에서 이번 사용자 구현 요청으로 추가한 로컬 매핑 쓰기 경로입니다. |
| `GET /api/youtube/search?track_id=...` | 현재 GENERAL 곡만 허용합니다. 키가 없으면 수동 검색 안내. 키가 있을 때 실제 공식 요청이 발생합니다. 후보를 자동 확정하지 않습니다. |

VERIFIED 등록에는 11자 영상 ID, 양의 `platform_duration_seconds`, `youtube_title`, `youtube_channel`, `verification_note`, `verified_by`, 시간대가 있는 `checked_at`이 필요합니다. `match_method`를 함께 보존하고 원곡명·아티스트·앨범·길이는 서버가 원본으로 고정합니다. 영상과 원곡의 실제 일치·한국 재생·삽입 가능은 사람의 검수 근거이며 형식 검사를 실제 청취 검증으로 표시하지 않습니다.

기본 sidecar는 `prototype/youtube-player/data/mapping.json`이며 Git 제외입니다. 사용자 JSON의 `mappings` 배열을 불러오면 현재 서버 버전을 붙여 제출합니다. 서버는 기존 매핑과 병합하고 임시 파일을 원자 교체합니다. 새 매핑은 새 큐 버전을 만들며 이미 실행 중인 큐는 복사본을 보존합니다. 원본 CSV와 시즌 판정 자료는 수정하지 않습니다.

POST는 로컬 Host·동일 Origin·`X-Local-Nonce`·JSON·1MiB 이하를 검사합니다. GET 검색은 같은 Origin 또는 Origin 없는 `Sec-Fetch-Site:same-origin`과 nonce를 검사합니다. 정적 경로는 화면 파일의 허용 목록으로 제한하며 저장소·data·logs·.env를 노출하지 않습니다. nonce는 서버 재시작마다 바뀌고 디스크·공유 계정에 보관하지 않습니다.

## 4. 플레이어·실패·검수 흐름

첫 일반 큐는 cue한 후 사용자가 시작합니다. 다음 곡은 앱 한 곳에서 `loadVideoById`로 이동하고 `loadPlaylist` 자동 이동을 혼합하지 않습니다. 매 재생 시도마다 이전 플레이어를 destroy하고 새 공식 객체를 하나만 생성합니다. 콜백의 실제 `event.target`과 객체 생성 때의 시도 ID를 대조하여 오래된 객체의 종료/오류를 무시합니다. `getVideoUrl`·현재 플레이어 상태도 교차 확인합니다. 교체 공백은 있을 수 있습니다.

자동 재생은 페이지·탭과 플레이어의 표시 상태를 확인합니다. 화면 밖이면 cue만 하고 사용자의 시작을 기다립니다. 탭을 숨기면 일시정지하며 숨긴 오디오 플레이어를 제공하지 않습니다. 첫 클릭과 전환 후 차단은 같은 순번에서 수동 재개합니다. 영상/음성을 다운로드하거나 광고를 우회하지 않습니다.

오류2/100/101/150은 해당 시도를 한 번만 실패 처리한 후 다음 항목을 시도합니다. 오류153은 전체 보류, 오류5·미확정 장애는 보류·명시 재시도입니다. 정지는 먼저 STOPPED를 설정하여 API의 종료 이벤트로 이동하지 않게 합니다. 마지막/모든 항목 실패는 유한 종료하며 자동 반복하지 않습니다.

검수자는 GENERAL 곡을 선택하고 실제 URL/ID를 입력한 뒤 [입력 영상 사전 시험]을 준비하고 [사전 시험 재생]을 누를 수 있습니다. 이 경로는 UNVERIFIED_PREVIEW로 표시하며 일반 큐에 들어가지 않습니다. 양의 플레이어 길이만 관측값으로 표시·입력 보조하며 제목·원곡·버전·국내 삽입 재생의 확인과 확정 저장은 별도 사람 작업입니다. 종료 후 자동 다음과 자동 확정은 없습니다.

## 5. 실행·검증 결과

저장소 루트에서 Python 표준 라이브러리로 실행합니다. 기본8002가 사용 중이면 사용 가능한 포트를 지정합니다.

```powershell
python prototype/youtube-player/server.py --data-dir analysis/weather_music_20261016/general --port 8002
```

같은 Chrome 프로필에서 `http://127.0.0.1:8002/`를 엽니다. 선택한 일반곡의 실제 영상·길이·메타데이터를 검수해 등록합니다. 1곡 시험→앞5곡 부분 시험→필터 후 전체 목록 시험 순으로 진행합니다. 데이터/매핑 경로만 CLI로 지정할 수 있으며 원본 전체를 웹에 제공하지 않습니다.

선택적인 `YOUTUBE_DATA_API_KEY`는 프로세스 환경에서만 읽습니다. `.env`를 생성·읽지 않습니다. 검색은 곡별15분 메모리 캐시와 프로세스 UTC날짜별100회 안전 상한을 사용합니다. 이 상한은 실제 Google 프로젝트 전체 쿼터·재시작 간 집계를 대체하지 않습니다. 현재 프로젝트 할당은 운영자가 별도 확인해야 합니다. OAuth 계정 재생목록 쓰기와 Premium 보장은 구현하지 않았습니다.

검증 명령과 실제 결과:

```powershell
python -m unittest discover -s prototype/youtube-player/tests -v
node --test prototype/youtube-player/tests/queue.test.mjs
Get-Content -LiteralPath prototype/youtube-player/web/app.js -Raw -Encoding UTF8 | node --input-type=module --check
```

- Python9건 PASS: 입력 원문 보존, GENERAL·VERIFIED·길이 gate, 버전 충돌·원자 병합, nonce/Origin/Host, 정적 경로 차단, Origin 없는 same-origin GET 검색, 모의 검색의 한국/삽입/길이 필터·캐시. 실제 외부 API를 호출하지 않았습니다.
- Node14건 PASS: 중복 종료·종료/다음 경합·오래된 시도, 종료 전 PLAYING, 자동 재생 차단, 일시정지/버퍼링,153/5 보류, 유한 실패, 정지, 마지막 종료, 불변 큐, 수동 복원, 미확정 preview와 일반 큐 분리·양의 길이 관측·자동 확정 없음.
- app.js 모듈 구문 PASS.
- 실제 general5날씨를 동일 프로세스 HTTP 서버로 조회:47/45/46/43/68곡 모두200, 각각10,800,000ms, 전부GENERAL, 미매핑 playable0, 분석 전용 상태 유지.
- 최초 Python 시험은 Windows 샌드박스 기본 Temp ACL 때문에 setup이 실패했습니다. 저장소 내 시험 전용 임시 폴더로 변경하고 재검증했습니다. 시험 cleanup 대상은 해당 임시 루트 내부임을 확인합니다.
- 브라우저 화면·실제 영상·계정·소리·5곡 자연 연속 및 전체 장시간 시험은 root가 별도 기록합니다. 위 자동 검증을 실제 YouTube 재생 성공으로 표시하지 않습니다.

## 6. 남은 연결

C·PL은 실제 영상 매핑과 원곡 일치 검수·삽입 시험·전체 실행 로그를 남겨야 합니다. 일반곡 CSV의 자동 GENERAL과 음악 운영 READY는 분리합니다. INF는 실제 Chrome 프로필·출처·네트워크·출력 장치와 프로세스 기동을 확인합니다. B·C는 후속 FastAPI 이식과 실제 결과/소유/DB 연결을 별도 계약으로 구현하며 기존 Django·광고 환경을 이 도구의 완료로 승격하지 않습니다.

수령 원문과 기존 다른 작업의 라우팅 파일은 변경하지 않았습니다. 이 문서는 위 Python/브라우저 모듈과 로컬 시험 범위만 관리합니다.
