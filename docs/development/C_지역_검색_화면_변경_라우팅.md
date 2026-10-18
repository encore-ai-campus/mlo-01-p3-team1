# C 지역 검색 화면 변경 라우팅

- 작성자/담당: Codex / C 공개 프론트엔드. A의 지역·날씨 조회 계약을 재사용합니다.
- 작성일/수정일: 2026-10-16
- 작업 범위: W-06/U-01 지역 검색·직접 선택·최초 진입 화면. 사용자 요청: “지역 검색기능도 추가하고 프론트도 저렇게 수정”.
- 브랜치/기준 커밋: `feature/integration@34711757b1b1c70e4716f8117a65a69251dc733a` + 작업 시작 시의 미커밋 변경. 기존 작업 내용을 보존했습니다.
- 상태: 코드·고정 응답 UI 시험·격리 로컬 백엔드 통합·현재 실행 앱의 실제 날씨 표시 확인. 운영 PostgreSQL/ES/Kafka 연결 전체 검증 완료를 뜻하지 않습니다.

## 1. 기준과 우선순위

다음 자료는 읽기만 했으며 수령 원문·시안·기존 라우팅 문서를 수정하지 않았습니다. 기준 커밋 이후 미커밋 문서를 포함하므로 커밋만으로 현재 내용을 재현할 수는 없습니다.

| 참조 | 확인한 기준/현재 구현과의 관계 |
|---|---|
| `docs/product/카페_음악_서비스_기능_및_사용자_흐름_정리.md` | 공개 지역·날씨 선택, 익명 지역 복원, 기존 선곡/평가 흐름 보존 |
| `docs/product/카페_음악_서비스_구현_설계도.md` | 지역 ID 기반 조회·시간/실패 상태·결과와 입력 변경 구분 |
| `docs/product/카페_음악_추천_서비스_3차_컬럼_기반_추천_로직_가이드.md` | ON/OFF와 기존 추천 규칙 유지. 검색이 추천이나 Gemini를 호출하지 않음 |
| `docs/product/카페_음악_추천_서비스_3차_구현_태스크.md` | W-06/U-01 공개 지역/날씨 화면. 기존 ‘지역 필수’ 표현은 최신 OFF 지역 생략 결정 및 현행 코드와 구분 |
| `docs/product/3차_공통_개발_계약과_검증_기준.md` | `phase3-20261016.1`, 모드별 입력과 외부 오류 분리 |
| `docs/handoff/weather/received/20261014/01_날씨_수집과_지역매핑.md` | 행정 지역/격자 매핑. 실제 지역 목록/ID의 소유는 날씨 담당 |
| `docs/development/실제_날씨_표시_변경_라우팅.md` | 현재 PC의 기상청 캐시 연결과 정식 운영 파이프라인의 차이 |
| `docs/assets/mockups/05-main-v8-compact-feedback-no-language.png` | 기존 3열/광고/안내/평가 배치 유지. 이번 대화에서 승인한 첫 진입 시안의 인라인 검색·미설정·예보 빈 상태를 적용 |

사용자 최신 결정에 따라 최초 진입부터 검색창과 [지역을 직접 선택하기]를 표시합니다. 기존 문서의 단계별 드롭다운 설명을 없애거나 원문을 고치는 대신, 이 문서에서 변경 경로를 명시합니다. 행정동 이름 검색이며 도로명·지번 주소 검색이나 자동 위치 추적은 추가하지 않았습니다.

## 2. 변경 전후와 파일/함수

| 변경 파일 | 변경 내용 |
|---|---|
| `frontend/src/features/region-weather/RegionPicker.tsx` / `RegionPicker`, `apply`, `direct` | 상시 3개 드롭다운 → 인라인 검색 + 검색 결과 + 직접 선택 dialog. 검색 결과는 선택 즉시 적용. 직접 선택은 draft를 유지하고 최종 설정 시에만 적용 |
| `frontend/src/features/region-weather/regionSearch.ts` / `findRegions` | NFKC/공백 정리, 검색어 토큰 AND 포함 검색, 정확한 동 이름→접두어→기타 순위, 이름/ID 안정 정렬. 원본 목록을 변경하지 않음 |
| `frontend/src/features/region-weather/region-picker.css` | 검색/목록/직접 선택 스타일, 데스크톱 검색창 아래 결과·중앙 선택 dialog, 700px 이하 직접 선택 하단 시트. 모바일 날씨 영역 줄바꿈 보정 |
| `frontend/src/features/region-weather/WeatherPanel.tsx` / `WeatherPanel` | 사용되지 않던 onSearch 대신 지역 목록 상태/재시도 전달. 미설정 제목/설명 및 현재·1~3시간 후 대시 표시. 실제 관측/예보·만료/오류·펭귄 안내 유지 |
| `frontend/src/features/recommendation/PublicPage.tsx` / 지역 목록 effect | auth/options와 지역 목록 조회 오류 분리. 목록만 재시도하며 기존 선택과 결과를 보존. OFF 선곡을 지역 목록 실패로 차단하지 않음 |
| `frontend/tests/regionSearch.test.ts` | 복수 지역어·동명이동·정확 이름 우선·빈 입력/미일치·목록 불변성 |
| `frontend/scripts/region-search-smoke.cjs` | 고정 HTTP 응답으로 초기/검색/선택/취소/복원/오류 재시도/기존 결과 보존/모바일 시험. 광고도 고정 예시이며 실제 광고 원장을 쓰지 않음 |
| `frontend/scripts/{smoke,feedback-smoke,integration-smoke,weather-live-smoke}.cjs` | 기존 드롭다운 조작 앞에 직접 선택 열기, 마지막에 적용 추가. integration은 하위 선택 초기화 후 취소도 확인 |
| `tests/run_browser_integration.py` | 선택 환경변수 BROWSER_USE_BUILD=1이면 개발 서버 대신 사전 빌드의 Vite preview를 사용. 기존 기본 경로 유지. 임시 DB/서버 격리 방식 유지 |

`frontend/src/style.css`의 기존 작업 내용은 이번 작업에서 수정하지 않았습니다. 기존 전역 스타일과 함께 동작하도록 기능 CSS의 범위를 제한했습니다. 대표 앨범·좋아요/싫어요·별점·승인·제외·음악 필터·광고 규칙은 변경하지 않았습니다.

## 3. 입력 → 조회 → 적용 → 저장 흐름

1. 정상 서비스 모드에서 익명 인증 초기화 뒤 `GET /api/regions/tree`의 `items[]`를 받습니다. 각 항목의 `region_id`, `name`, `province`, `district`, `locality`를 사용합니다. 추가 검색 API/DB/큐/마이그레이션은 없습니다. 기존 서버 `/api/regions?q=`는 변경하거나 호출하지 않습니다.
2. 브라우저에서 받은 목록을 검색합니다. 예: `서울 성수`, `성동구`, `성수1가`. 상위 행정구역을 함께 보여 동명 지역을 구분하고 최대 30개만 표시하며 더 좁히라는 안내를 제공합니다. 임의 문자열은 ID로 저장하지 않습니다.
3. 방향키로 결과 이동, Enter로 명시 선택, Esc/밖 클릭/포커스 이탈로 닫습니다. 입력 중 IME Enter는 지역 선택으로 해석하지 않습니다. 검색 결과는 combobox/listbox 의미를 제공합니다.
4. 직접 선택은 native modal dialog의 포커스 제한/Esc를 사용합니다. 상위 선택 변경 시 하위 draft만 초기화합니다. 닫기/Esc/배경 클릭은 현재 지역·날씨에 영향을 주지 않습니다. 재개방 시 적용 지역으로 draft를 복구합니다.
5. 적용 시 `onRegion(id)` → `choices.region_id` → 기존 effect의 `GET /api/weather?region_id=...` → 날씨 패널 갱신입니다. 이전 조회는 AbortController로 중단합니다. 기존 30초 기본 폴링·날씨 유효성 계약을 유지합니다.
6. 정상 서비스는 기존 `localStorage['cafe-region']` 저장·유효 ID 복원을 재사용합니다. 저장 실패 시 선택은 현재 탭에서 유지합니다. 기존 C_DEMO 모드의 context 공급·지역 저장 제외는 그대로입니다.
7. 기존 선곡표는 그대로 두고 조건 변경 상태로 표시합니다. 사용자가 [선곡표 받기]를 눌러야 새 기본 추천을 요청합니다. 명시 OFF 선택을 지역 적용으로 ON으로 덮어쓰지 않습니다. 무지역 초기 OFF/지역 선택 후 기본 ON은 기존 모드 동작입니다.
8. 지역 목록 조회 실패는 패널 안에서 재시도합니다. region_id 없는 OFF 추천은 계속 허용합니다. ON은 기존 날씨 준비/유효성 조건을 유지합니다. 생성/저장/승인 중 지역 입력·적용을 차단합니다. API 소유/권한·익명 쿠키·outbox/피드백 계약은 기존 서버 책임을 유지합니다.

송수신 경계: A는 실제 목록과 유효한 날씨 조회, C는 지역 선택/검색과 추천 입력, B는 기존 익명 소유/피드백입니다. 현재 반환 필드로 동작하여 추가 어댑터는 필요하지 않습니다.

## 4. 실제 검증과 한계

2026-10-16 실행 결과:

- `node node_modules/typescript/bin/tsc -b`: 통과.
- frontend에서 `node node_modules/vite/bin/vite.js build --configLoader runner`: 통과.
- frontend에서 `node node_modules/vitest/vitest.mjs run --configLoader runner`: 3파일/4테스트 통과(지역 검색 2 + 기존 API/프록시 2).
- `NODE_PATH`를 번들 Node 패키지 경로로 설정하고 `node frontend/scripts/region-search-smoke.cjs`: 통과. 실제 빌드 + Edge, 고정 HTTP 응답만 사용. 검색/키보드/미일치/취소/확정/명시 OFF 유지/선곡표 보존/추천 자동 호출 없음/지역 복원/390px 모바일/목록 실패 후 OFF 활성·재시도 확인.
- `BROWSER_USE_BUILD=1`과 번들 Node 패키지 NODE_PATH를 설정하고 `.venv/Scripts/python.exe tests/run_browser_integration.py`: 통과. 격리 SQLite·실제 공통 API·추천 작업자·실제 3,564개 지역 트리 응답을 사용. OFF 무지역 선곡·좋아요 해제·별점 취소·곡 제외/취소·직접 선택/상위 초기화·관리 로그인/이력/로그아웃 통과. 합성 날씨/음악이며 Gemini 비활성화. 함께 실행된 광고 배치 시험은 고정 HTTP 자료 기반 통과.
- 실행 중인 `http://127.0.0.1:19073`에 `node frontend/scripts/weather-live-smoke.cjs`: 통과. 직접 선택한 목포 `region:1211075700`에서 `is_test=false`, `source=KMA_API_HUB`, 흐림·22.8°C와 관측/예보16:30 표시. 기존 캐시 조회 시험이며 외부 수집기·정식 저장소를 신규 생성하거나 재설정하지 않음.
- `git diff --check -- frontend tests/run_browser_integration.py`: 통과.
- 화면 직접 확인: `artifacts/region-search/initial-desktop.png`, `search-desktop.png`, `direct-mobile.png`, `initial-mobile.png`. 실제 앱 렌더이며 고정 응답 시험 자료를 사용합니다. 최초 모바일 가로 넘침을 수정하고 재시험했습니다.

실패/조정: 기본 Vite config 번들링과 개발 의존성 스캔이 제한된 Windows 환경의 상위 디렉터리 접근으로 실패했습니다. 제품 설정을 바꾸지 않고 runner + 빌드 preview로 검증했습니다. 번들 Python에는 Django가 없고 프로젝트 venv의 기반 Python 실행에는 제한이 있어 기존 프로젝트 venv 시험을 승인된 실행 환경에서 수행했습니다. 설치/패키지 버전/잠금 파일을 바꾸지 않았습니다.

## 5. 인계와 남은 연결

- A/INF: 운영 PostgreSQL 지역 목록의 실제 연결·매핑 갱신·ES 유효 예보·Kafka/Spark 전체 운영 연결/복구는 기존 인계 사항입니다. 현재 로컬 날씨 표시 통과와 구분합니다.
- C: 지역 트리 형식 변경 시 이 컴포넌트의 계층 필드와 검색 결과를 함께 검증합니다. 검색 전송 API·상태 저장 규약은 새로 추가하지 않았습니다.
- PL: 도로명/지번 주소 검색과 자동 위치 확인은 이번 승인 범위가 아니며 추가 정책이 확정되지 않았습니다. 이 문서가 해당 기능을 확정하지 않습니다.
- 기존 smoke/feedback 전체 스크립트는 조작 호환 수정만 했고 이번에 각각 별도 실행하지 않았습니다. 공통 흐름은 격리 통합 시험에서 검증했습니다. 운영 RDB 부하/장애 복구·실제 Gemini 응답/과금·정식 광고 원장은 미검증입니다.
- 커밋·푸시·배포·외부 서비스 변경은 수행하지 않았습니다. 수령 원문·기존 이미지와 타인의 라우팅 문서는 보존했습니다.
