# YouTube 자동 검색 변경 라우팅

- 작성일: 2026-10-16
- 수정일: 2026-10-16
- 작성/담당: YouTube 자동 검색 백엔드 작업자(C 협업)
- 범위: 기존 공개 대시보드 중앙 iframe의 영상 후보 조회 서비스. U-01/U-03·R-02 연결 보완이며 기존 태스크 직접 선행 관계는 변경하지 않습니다.
- 브랜치/기준 커밋: `feature/ad-logic` / `f22f974`
- 최신 사용자 결정: 기존 중앙 곡 앨범 이미지 영역에서 자동 iframe 재생·연속 재생하고 LLM을 필수로 요구하지 않습니다. 외부 YouTube 이동을 주진입으로 삼은 앞 구현보다 이 결정이 우선합니다.

## 기준과 수령 원문 경계

[서비스 흐름](../product/카페_음악_서비스_기능_및_사용자_흐름_정리.md), [설계도](../product/카페_음악_서비스_구현_설계도.md), [ON/OFF 추천 가이드](../product/카페_음악_추천_서비스_3차_컬럼_기반_추천_로직_가이드.md), [구현 태스크](../product/카페_음악_추천_서비스_3차_구현_태스크.md), [공통 개발 계약](../product/3차_공통_개발_계약과_검증_기준.md)을 추천/소유/당시 곡/시간의 기준으로 연결합니다. 수령 음악 자료인 [음악 분류 컬럼 정의](../handoff/music/음악_분류_컬럼_정의.md)와 `docs/handoff/music/` 원문은 기준 커밋의 수령 자료이며 수정하지 않습니다. 목표 FastAPI와 현재 Django 로컬 실행의 차이는 [음악·재생 정본 라우팅](./음악_재생_정본_변경_라우팅.md)에 유지합니다.

일반 추천은 전체 GENERAL 적격 풀에서 먼저 구성합니다. 영상이 없다는 이유로 음악 후보 풀을 기존47곡에 제한하거나 음악을 다른 곡으로 교체하지 않습니다. 영상 검색은 이미 생성된 원곡에 연결할 영상 후보를 읽는 보조 작업이며 곡 점수·순서·제외·피드백·승인·카탈로그·결과 스냅샷을 변경하지 않습니다. 기본 추천과 영상 조회는 Gemini/LLM을 호출하지 않습니다. 명시 Gemini 재설정 계약은 별도입니다.

## 호출과 반환

루트 통합 담당의 `POST /api/playlists/{playlist_id}/youtube-playback`은 기존 `Endpoint`의 소유/CSRF 경계에서 선곡표를 조회하고, `validate_playback_request(body)`로 `{track_id, excluded_video_ids?:[]}`를 검사합니다. 이 서비스에 전달할 곡은 해당 선곡표의 불변 `snapshot.items`에서 찾습니다. 클라이언트가 임의 검색어·URL·API 키·곡 메타데이터를 주입할 수 없습니다. 키 누락/정상 조회의 상태 DTO는 HTTP 200 본문이며 소유/입력 오류는 기존 공통 오류를 따릅니다.

`backend/recommendation/youtube_playback.py`의 `resolve_playback_candidates(track, excluded_video_ids=(), owner_id='')`가 반환하는 필드는 다음과 같습니다.

| 필드 | 정의 |
|---|---|
| `track_id` | 요청한 원본 선곡표 곡 ID |
| `status` | `READY`(후보 있음), `SEARCH_UNAVAILABLE`(검색 연결/한도/기술 사유), `NO_MATCH`(조회한 제한 후보에서 규칙 통과 없음) |
| `candidates` | 최대5개. `video_id/title/channel_title/duration_seconds/source/match_status` |
| `source` | `CATALOG_MAPPING` 또는 `YOUTUBE_API` |
| `match_status` | 기존 메타데이터 확인값 `VERIFIED` 보존, 새 자동 API 매칭은 `CANDIDATE` |
| `reason/message` | 검색 미가용의 고정 이유와 한국어 안내. upstream 본문/자격증명 미노출 |

`READY`는 iframe에서 재생할 후보가 준비되었다는 뜻입니다. 기존 `VERIFIED`는 앞 단계 메타데이터 확인 범위이며 삽입 성공을 보장하지 않습니다. API의 `status.embeddable=true`도 현재 브라우저에서의 성공을 보장하지 않으므로 실제 YouTube Player 오류 처리는 프런트엔드가 수행합니다. `NO_MATCH`는 YouTube 전체에 영상이 없다는 판정이 아니며 검색 상위5개·현재 검사 규칙의 결과입니다.

실패 영상은 유효11자 ID만 최대10개까지 `excluded_video_ids`로 받습니다. 해당 곡의 기존 검증 매핑을 먼저 반환하고, 그 영상이 실패 목록에 포함되면 API 후보 조회로 넘어갑니다. API 조회 결과는 모든 후보를 캐시한 뒤 요청의 실패 ID를 제거하므로 다른 후보로 시도할 때마다 검색 API를 다시 호출하지 않습니다. 모든 후보 소진 시 `NO_MATCH`입니다.

## 공식 API와 매칭

고정 `https://www.googleapis.com/youtube/v3/`에만 접속하며 리디렉션을 따르지 않습니다. 서버의 기존 곡명과 아티스트로 `search.list`를1회 호출하고 `type=video`, `videoEmbeddable=true`, `videoSyndicated=true`, `regionCode=KR`, `maxResults=5`, `order=relevance`를 적용합니다. 반환된 고유 ID만 `videos.list(part=snippet,contentDetails,status)`1회로 확인합니다.

공개/삽입 허용, 한국 지역 제한, 연령 제한, 현재/예정 생방송, 양의 ISO8601 길이를 검사합니다. 원본 길이 차이는 `min(60초,max(12초,원본의12%))` 이내이고, 정규화한 곡명 토큰80%와 주 아티스트 토큰75% 이상이 확인되어야 후보가 됩니다. 원본 곡명·앨범에 없는 live/remix/cover/karaoke 등 명시 버전은 거절합니다. 곡명·아티스트·길이 근접 점수와 영상 ID로 정렬합니다. 이 규칙은 초기 메타데이터 추정이며 청취/파형 동일성 검증이나 자동 VERIFIED 승격이 아닙니다. 한글/로마자 다른 표기·제목이 다른 클래식 악장·출처가 부족한 영상은 놓칠 수 있습니다.

공식 확인 근거(2026-10-16): [search.list](https://developers.google.com/youtube/data/reference/rest/v3/search/list), [videos resource](https://developers.google.com/youtube/data/reference/rest/v3/videos), [할당량 설명](https://developers.google.com/youtube/data/determine_quota_cost). 현재 search 문서는 검색용 할당량 묶음을 설명하므로 과거의 검색100단위를 현재 프로젝트의 과금/할당량으로 단정하지 않습니다. 실제 Google Cloud 프로젝트의 할당량과 API 키 제한은 담당자가 확인해야 합니다.

## 설정·캐시·제한

| 서버 설정 | 코드 보호 기본값/용도 |
|---|---|
| `YOUTUBE_DATA_API_KEY` | 서버 전용. 누락 시 기존 매핑은 사용하고 미매핑은 `API_KEY_MISSING` |
| `YOUTUBE_SEARCH_TIMEOUT_SECONDS` | 요청당8초, 코드 허용1~15초 |
| `YOUTUBE_SEARCH_PER_OWNER_MINUTE` | 같은 소유 문맥의 미캐시 검색6회/분 |
| `YOUTUBE_SEARCH_DAILY_LIMIT` | 앱의 미캐시 검색80회/UTC일 |
| `YOUTUBE_SEARCH_CACHE_SECONDS` | 후보 있음6시간, 코드 최대24시간 |

설정 읽기는 루트 `backend/cafe/settings.py`에 연결합니다. 보호 기본값은 실제 프로젝트의 승인 예산·할당량이나 운영 보장치가 아닙니다. Django의 기존 기본 `LocMemCache`는 프로세스별·비영속 캐시이며 프로세스 재시작/퇴거로 사라집니다. 운영에서 여러 프로세스의 공통 한도를 보장하려면 원자 `add/incr`를 지원하는 공유 캐시와 배포 설정을 INF가 연결해야 합니다. 이번 구현에 Redis·모델·migration·공유DB 설치는 추가하지 않습니다.

후보 캐시 키 `ytp:candidates:<SHA256>`는 원본 곡 ID/곡명/아티스트/앨범/길이·`POLICY_VERSION`·API 키의 해시 지문으로 구성합니다. 원문 키/소유 ID는 저장하지 않습니다. 같은 곡은 소유 문맥이 달라도 읽기 후보 캐시를 재사용합니다. 후보 없음은10분, upstream 기술 오류는60초 캐시합니다. `ytp:inflight:<SHA256>`는45초 단일 요청 잠금이며 겹친 조회는 `API_BUSY`입니다. 분 한도 키는 소유 ID의 해시와 UTC 분, 일 한도는 UTC 날짜입니다. 캐시/기존 매핑 조회는 검색 한도를 사용하지 않습니다.

`API_KEY_MISSING`, `API_QUOTA_EXCEEDED`, `API_AUTH_FAILED`, `API_NETWORK_ERROR`, `API_INVALID_RESPONSE`, `API_RATE_LIMITED`, `API_DAILY_LIMIT`, `API_BUSY`를 고정 안내로 반환합니다. 클라이언트에 Google 오류본문·요청 URL·키를 반사하지 않습니다. 자동 재시도나 대체 검색 서비스/비공식 스크래핑은 없습니다.

## 변경 파일과 검증·남은 연결

| 파일 | 변경 전 → 후 |
|---|---|
| `backend/recommendation/youtube_playback.py` | 없음 → 원곡 기반의 읽기 후보 해석/공식 검색/캐시/한도/고정 오류 |
| `backend/recommendation/tests/test_youtube_playback.py` | 없음 → DB/외부 네트워크 없는18건 의미 검증 |
| `docs/music-playback-routing/files/backend/recommendation/youtube_playback.py.md` | 없음 → 검사기 AST 짝 문서 |
| `docs/music-playback-routing/files/backend/recommendation/tests/test_youtube_playback.py.md` | 없음 → 테스트 AST 짝 문서 |

실행한 명령은 `C_LOCAL_DEMO=1`에서 `.\.venv\Scripts\python.exe -X utf8 -m backend.manage test backend.recommendation.tests.test_youtube_playback --verbosity 2`이며18건 전부 통과했습니다. 엄격 입력·원본 불변·키 없음·API 검색 필터·버전/길이/지역/삽입 제한·캐시·중복 호출·분/일 한도·오류 비밀 비노출을 확인했습니다. 네트워크 응답은 mock이며 실제 API 과금·검색·전곡 동영상 일치/삽입 재생 성공을 뜻하지 않습니다.

API endpoint/settings/소유·CSRF 통합과 프런트엔드의 자동 연결·오류/다음 곡 처리는 루트·프런트엔드 담당이 연결합니다. 서버에 실제 API 키가 없는 현재 환경에서는 새 미매핑 곡의 자동 검색을 완료했다고 보고하지 않습니다. API 키 연결 후 상위5개 매칭 적중률·한국 브라우저의 실제 삽입·인증/할당량·캐시 재시작/동시 요청을 추가 검증해야 합니다. 변경 라우팅 검사기의 UTF8 실행 보고서는 `analysis/youtube-resolver-routing-audit.json`이며 전체 색인 보완과 최종 통합 판정은 루트가 취합합니다.
