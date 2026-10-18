# C 구현과 연결 인계

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- 범위: 3차 C 담당. 로컬 고정 검증, 실제 서비스 연결 전 단계입니다.

코드 초안의 분야별 진입점·읽는 순서·변경/검증 기준은 [C 정리 기준과 작업 라우팅](../development/C_코드초안_정리기준과_작업라우팅.md)을 먼저 확인합니다. 이 문서는 실행 명령과 실제 연결 방법을 담당합니다.

## 1. 적용 기준과 브랜치

사용자 지시로 `develop@712820c`에서 만든 `feature/recommendation-music`에서 작업했습니다. 이 출발점에는 최신 문서 커밋 `ec0c7e3`가 조상으로 들어 있지 않습니다. 사용자가 확정한 음악18개＋검수보조1개·RDB4개·W 내부50:45:5·전체75:25·장르/speed 필수·176~184분·자동단축 미사용을 코드에 적용했습니다.

[음악 통합 계약](../product/3차_음악_정책_통합_계약.md)과 [음악 인계](../handoff/music/README.md), 연결된 컬럼/매핑/테이블/선곡 문서는 기존 수령본을 `ec0c7e3`에서 복원했습니다. 원본 문서의 작성/수정일과 본문을 보존했습니다. 브랜치 병합·커밋·푸시는 수행하지 않았습니다. 기존 네 제품 문서와 공통 계약의 옛 본문은 이 브랜치에서 전부 재작성하지 않았으므로 음악/스택/시간의 충돌에는 최신 사용자 결정과 음악 통합 계약을 우선합니다.

계약 버전 보류도 유지합니다. 공통 문서/fixture 최상위 `.2`와 이벤트 envelope `.1` 중 어느 것을 정답으로 정하거나 기존 JSON을 수정하지 않았습니다. C 로컬 PendingEvent는 정식 발행 envelope가 아닌 연결 대기 기록입니다. 실제 `X-Contract-Version`/Kafka envelope·공통 outbox 연결은 B와 버전 결정을 확인한 후 적용합니다.

## 2. 실행 환경

실제로 검증한 환경은 Windows·Python3.12, Django6.1.2·DRF3.18.3·OR-Tools9.15.6755, React19.3.0·TypeScript5.9.3·Vite7.3.7입니다. 전체 Python 잠금은 `backend/requirements.lock`, 프론트엔드 잠금은 `frontend/pnpm-lock.yaml`입니다. 이 로컬 설치를 팀/운영 호환 버전 확정으로 취급하지 않습니다.

프로젝트 루트의 PowerShell에서 최초 설치합니다.

```powershell
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r backend/requirements.lock
$env:C_LOCAL_DEMO='1'
./.venv/Scripts/python.exe -m backend.manage migrate --noinput
./.venv/Scripts/python.exe -m backend.manage seed_c_demo
```

`seed_c_demo`는 합성곡64개만 `is_test=true`로 생성합니다. Spotify 실제 곡/청취 검수/실제 날씨를 가장하지 않습니다. 동일 버전은 덮어쓰지 않습니다. SQLite는 단일 작업자의 로컬 검증에만 사용합니다.

터미널 세 개에서 실행합니다.

```powershell
# 터미널1 · API
$env:C_LOCAL_DEMO='1'
./.venv/Scripts/python.exe -m backend.manage runserver 127.0.0.1:8001
```

```powershell
# 터미널2 · 추천 작업자
$env:C_LOCAL_DEMO='1'
./.venv/Scripts/python.exe -m backend.manage run_recommendations
```

```powershell
# 터미널3 · 공개 화면
cd frontend
pnpm install --frozen-lockfile
$env:VITE_C_DEMO='1'
pnpm dev
```

현재 Vite의 로컬 프록시는 `127.0.0.1:8001`, 화면은 `http://127.0.0.1:5173`입니다. pnpm이 PATH에 없으면 Codex 제공 Node 런타임의 `node_modules/pnpm/bin/pnpm.cjs`를 Node로 실행할 수 있습니다. 배포 명령은 포함하지 않습니다. 종료는 각 터미널에서 Ctrl+C입니다.

## 3. CSV 변환과 음악 RDB

저장소에 포함한 원본 CSV를 변경하지 않고 상대 경로로 입력합니다. 수령 당시 다운로드 파일과 해시가 일치합니다.

```powershell
./.venv/Scripts/python.exe -m pipeline.music.normalize docs/handoff/music/spotify_dataset.csv --schema spotify-raw20-v1 --output artifacts/music-staging.json
```

입력 형식은 `spotify-raw20-v1` 또는 `music-normalized19-v1`입니다. energy/acousticness 절삭·mode0/1·3박자 보정/HALF_UP·장르 합집합·검수False 보존·아티스트 ID 빈 위치를 처리합니다. 필수 메타데이터 충돌 곡은 정상 목록에서 통째로 격리하고 오류 행/원본/해시를 보고서에 남깁니다. 길이0은 저장 형식에는 허용하지만 추천에서 제외합니다.

로컬 DB 적재까지 확인할 때만 아래 명령을 명시적으로 사용합니다. 일반 변환 명령은 DB에 쓰지 않습니다.

```powershell
$env:C_LOCAL_DEMO='1'
./.venv/Scripts/python.exe -m backend.manage stage_music docs/handoff/music/spotify_dataset.csv --schema spotify-raw20-v1 --report artifacts/music-staging.json --load-local-demo
```

`music_album/music_track/music_tag/track_tag` 모델과 PK/FK/UNIQUE/범위 제약을 제공합니다. track_tag는 복합 PK입니다. 실제 음악 RDB 제품·분리 배치·DDL 적용은 INF/B 연결 전입니다. 원본 확인 장르 연결만 approved로 입력하고 청취 mood/악기를 생성하지 않습니다. 일반 적재는 검수 컬럼을 갱신하지 않습니다.

`backend.music.catalog.export_tracks`는 활성/approved 연결을 먼저 모아 곡당 한 행을 반환합니다. `publish(version, source_ref, source_sha256, is_test)`는 원본 불변 참조/해시를 받아 불변 카탈로그를 발행하며 같은 버전을 덮지 않습니다. 실제 원본 보관·manifest·분리 DB 발행/복구는 INF/B 검증 대상입니다. 실제 CSV 변환만으로 READY를 만들지 않습니다.

## 4. 추천·작업·상태

- C API: 기본 작업 등록/조회, 결과 조회, 계열 제외 GET/PUT, 명시 재설정 등록, 승인.
- 정확한 Fraction 점수, 시간 구간 우선→목표 거리→시간 가중 Q→ID 집합 사전순으로 OR-Tools를 실행합니다. 기본 재생 순서는 S 내림차순/ID 오름차순입니다.
- 예보 구간은 시간대 문자열 순서가 아닌 절대 시각으로 정렬하며 마이크로초 경계도 Fraction으로 보존합니다. 화면은 실황과 앞3시간의 시간대별 예보를 구분합니다.
- 전체 적격 후보가 설정 상한을 넘으면 SEARCH_INCOMPLETE입니다. 2026-10-19에는 선택 장르용 정확 탐색 단축·CP-SAT 대체 경로와 대형 카탈로그의 선택적 ON 후보 인덱스를 연결했습니다. 점수·필터·176~184분·확장·오류 의미는 유지합니다. 넓은 조건과 OFF는 기존 후보 순회를 사용하고, 로컬 AWS/P95·동시 요청 부하는 검증되지 않았습니다. 운영 탐색 설정은 반드시 별도 공급합니다. [상세 라우팅과 검증](../development/추천_선곡_성능개선_변경_라우팅.md).
- 최초 성공 때 family의 장르/speed 집합을 고정합니다. 조건 변경 재설정은409, 새 기본 요청은 빈 제외의 새 계열입니다. 혼합 최초 auto/fast는 POLICY_NOT_READY, slow는 명시 집합을 적용합니다.
- 작업은 PostgreSQL claim/lease30초·heartbeat10초·세대/토큰 검사·최대3회 복구 코드가 있습니다. SQLite에서 다중 작업자를 사용하지 않습니다. PostgreSQL 실제 다중 claim/복구는 아직 미검증입니다.
- 만료된 작업자는 성공뿐 아니라 오류 상태 갱신과 외부 호출 시작도 할 수 없습니다. 만료 뒤 오류/예외가 발생해도 복구할 RUNNING 상태를 보존하며 다음 유효 세대만 완료합니다.
- 외부 호출 후 작업자가 중단되면 자동 재호출하지 않고 PROVIDER_OUTCOME_UNKNOWN으로 남깁니다. SDK는1회 시도로 제한하며 입력 목록 해시·모델/프롬프트/스키마·토큰 진단을 기록합니다. 실제 Gemini 호출/과금은 수행하지 않았습니다.
- 제외·승인과 C 이벤트 기록/멱등 응답을 같은 transaction.atomic에서 저장합니다. 취소는 원래 제외 이벤트/곡 스냅샷을 연결합니다. 실패한 재설정은 부모 결과/초안/승인을 바꾸지 않습니다.
- 평가 UI는 결과 버전에 귀속하며 GET의 reaction/rating 필드와 PUT의 value 필드를 구분합니다. 같은 키 재시도·충돌 후 최신 revision 확인·이전 결과의 늦은 응답 격리를 제공합니다.
- 평가 조회 실패는 다시 확인할 수 있고 대상별 실패/멱등 키를 보존합니다. 다른 곡의 저장 성공이 실패한 별점 재시도를 지우지 않습니다. 별점은 라디오 역할·방향키/Home/End·미평가/취소를 제공합니다.

## 5. A/B/INF 연결 경계

실제 모드는 `C_LOCAL_DEMO`를 해제하고 실제 비밀값을 실행 환경에 공급합니다. `.env.example`은 이름 안내이며 자동 로딩되지 않습니다.

| 연결 | 필요한 공급/호환 규격 | 현재 상태 |
|---|---|---|
| A → C 날씨 | `WEATHER_PROVIDER`의 import 경로. `(region_id, aware_as_of)` → region_id/as_of/valid_until/segments. 각 구간 start_at/end_at/issued_at/received_at/pty/sky/status 및 원문 참조/단위/출처를 보존 | 모의6시간 bundle만 실제 실행. 현재 기본 화면의 기온/간략 전망은 A 전체 응답 어댑터 보완 필요 |
| B → C 익명 소유 | `OWNER_RESOLVER(request)` → 서버 검증한 불투명 owner ID. 공통 guest 쿠키/CSRF 발급은 B | 로컬만 Django 서버 세션의 검증용 owner 사용. 운영 세션 만료·보관 정책 미확정 |
| C → B 이벤트 | `EVENT_SINK(kind,payload)`가 C와 같은 DB 트랜잭션 안에서 상태/event/outbox를 연결. C가 만든 event_id·당시 context/곡·취소 연결을 보존 | 실제 Kafka 발행 없음. B adapter와 보류 envelope 버전 필요 |
| B → C 평가 | 기존 feedback GET·reaction/rating PUT, 엄격 타입·revision·멱등·실제 결과 소유 | C UI 작성, B 고정 응답 브라우저 검증. 실제 저장/집계 대기 |
| B → C 인증/관리 | auth/me/login/logout·음악 imports/reviews/readiness·관리 제외 이력 목록/상세 | C 화면 작성. 허용 메뉴·관리 DTO/페이지네이션 세부는 B와 최종 대조 후 연결. 광고 관리 화면은 B |
| B → C 광고 | ads 응답은 ad(null 또는 ad_id/title/image_url/link_url/delivery_id)·evaluated_at·valid_until. ad-events는 delivery_id/event_id/event_type/occurred_at | 상단 최초 응답 후 하단 조회·1초 재확인·실패/기한 숨김·같은 이벤트 본문 재전송. B 고정 응답 검증 통과, 실제 중단3초/측정/중복은 통합 대기 |
| INF → C | PostgreSQL/음악 RDB 실제 제품·DDL·접속·프로세스 배치·보관/백업·작업 설정 | 로컬SQLite 검증만 수행 |

운영 통합 전 `OWNER_RESOLVER`/`WEATHER_PROVIDER`/`EVENT_SINK`가 없으면 성공을 가장하지 않습니다. 로그인은 서버 ADMIN/landing_path를 따르며 권한 선택 버튼을 만들지 않았습니다. `/admin/ads`에는 B 화면 연결 대기 표시만 있습니다. 4차 계정/결제/외부 목록 생성은 추가하지 않았습니다.

## 6. 남은 검증과 보류

혼합 최초 speed·테마 세부 정렬·실제 mood/악기/검수·explicit 미확인 세부·음악 DB/불변 발행/보관·세션/결과 만료·성능/청취 목표·Gemini 실제 프로젝트/예산은 보류/인계 대기입니다. 전체3차 또는 M/R/U/AD/F/Q 태스크를 모두 완료로 표시하지 않습니다.

OpenAPI 생성·B 공통 envelope·실제 PostgreSQL 동시성/복구·대규모 후보 확장·광고 실제 측정·A 응답의 전체 날씨 패널 매핑·관리 API 실연결은 후속 통합 대상입니다. 현재 브랜치의 과거 공통 문서와 최신 채택 문서를 통합하는 작업도 별도로 남습니다.

## 7. 목업·공개 연결 보완

제공 메인05·로그인06·안내01 PNG를 직접 확인해 흰색/파란색, 3패널의 위치/비율, 로그인 폼, 펭귄 대상 강조에 반영했습니다. 새 Header/WeatherPanel/Icons는 `frontend/src/components/`에 있으며 별도의 소개 영역과 임의의 서비스명을 제거했습니다. 옵션은 시안의 예시4개로 제한하지 않고 서버의 활성27개를 스크롤로 제공하며, 곡 수/날씨/이미지는 실제 응답과 기본 이미지를 사용합니다. 음악 재생시간은 공개 메인에 표시하지 않고 서버에서 검증합니다.

광고 공개 DTO·최초 문맥 순서는 현재 브랜치에 없는 `ec0c7e3`의 ADS README/01 원문과 대조했습니다. 원문은 Git 이력으로 확인했으며 파일 전체 복원/브랜치 병합을 수행한 것은 아닙니다. 실제 B 공개 OpenAPI·이미지 조회URL·관리 DTO와의 마지막 대조는 연결 시 필요합니다. B 광고 관리 화면07은 C가 구현하지 않습니다.

광고 전송은 같은 event_id/occurred_at/본문으로 최대3회, 실패 후 1초×시도수 지연을 사용하는 개발용 기본값입니다. 5분 지연 허용·3초 표시 기한·delivery 수명과 구분하며, 운영 재전송 설정은 B/INF 인계 전입니다. 정상 ad:null은 광고 없음, 실패는 연결 대기로 구분합니다. 클릭 이동은 전송 응답을 기다리지 않습니다.

브라우저 검증은 `frontend/scripts/smoke.cjs`(실제 C API/worker), `feedback-smoke.cjs`와 `ad-smoke.cjs`(각 B 계약 고정 응답)로 나눴습니다. 마지막 두 스크립트의 성공은 B DB/집계/운영 검증이 아닙니다. 상세 결과와 캡처는 [로컬 검증 기록](../acceptance/C_로컬_검증_20261015.md)에 있습니다.
