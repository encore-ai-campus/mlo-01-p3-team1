# C 코드 초안 정리 기준과 작업 라우팅

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- 적용 범위: 3차 C 담당 코드 초안과 관련 문서·검증·인계입니다.
- 현재 브랜치: `feature/recommendation-music` (`develop@712820c` 출발)
- 상태: 코드 초안 작성 및 로컬 검증. 실제 A/B/INF 연결과 전체3차 완료는 별도입니다.

## 1. 이 문서를 사용하는 순서

1. 요청이 읽기 전용인지 수정 지시인지 먼저 구분합니다. 확인·검토 요청만으로 코드나 문서를 변경하지 않습니다.
2. 아래 2절에서 적용 기준과 보류 사항을 확인합니다.
3. 3절의 분야별 표에서 읽을 문서 → 코드 진입점 → 관련 검증을 선택합니다. 여러 분야에 걸치면 해당 행을 모두 확인합니다.
4. 현재 변경 파일·다른 담당자의 미완성 변경을 확인하고 4절의 책임 경계에 맞춰 변경 범위를 정합니다.
5. 5절의 정리 기준으로 코드를 작성하고, 6절의 증거 수준과 변경 영향에 맞춰 검증합니다.
6. 실행 방법은 [실행·연결 인계](../runbook/C_구현과_연결_인계.md), 수행 결과는 [검증 기록](../acceptance/C_로컬_검증_20261015.md)에 연결합니다.

라우팅 표는 파일을 찾아가는 안내입니다. 검색 결과나 제목만 보고 관련 계약을 읽었다고 판단하지 않으며, 해당 동작의 전체 계약과 연결 구간을 확인합니다. 이 문서는 제품 정책·태스크 ID·직접 선행 작업·P0/P1·작업 권한을 변경하지 않습니다.

## 2. 적용 기준과 충돌 처리

적용 순서는 최신 사용자 결정 → 채택된 [음악 통합 계약](../product/3차_음악_정책_통합_계약.md)과 수령 원문 → 충돌하지 않는 제품/공통 계약 → 시안·예시·보관 이력입니다.

이 브랜치의 과거 제품/공통 문서에는 16개·수동 전용·FastAPI·자동135분 단축 등의 본문이 남아 있습니다. 이 값들을 코드로 복원하지 않습니다. 현재 C 초안은 음악18개＋검수보조1개, RDB4개, Django/DRF, W 내부50:45:5·전체75:25, 장르/speed 필수, 176~184분·자동단축 미사용을 적용합니다. 공유 문서 전체의 정합화는 아직 완료되지 않았습니다.

분야별 계약을 바꾸는 요청이면 다음 네 제품 문서를 모두 확인한 뒤 관련 음악/날씨/저장/평가/광고 인계까지 대조합니다.

- [서비스 기능과 사용자 흐름](../product/카페_음악_서비스_기능_및_사용자_흐름_정리.md)
- [구현 설계도](../product/카페_음악_서비스_구현_설계도.md)
- [추천 로직 가이드](../product/카페_음악_추천_서비스_3차_컬럼_기반_추천_로직_가이드.md)
- [구현 태스크](../product/카페_음악_추천_서비스_3차_구현_태스크.md)

확정·초안·자료 대기·실제 검증 완료를 구분합니다. 새 자료가 기존 문서와 충돌하면 위치와 코드 영향을 기록하고, 명확한 최신 사용자 결정이 없는 항목을 임의 선택하지 않습니다.

현재 보류/인계 경계는 다음과 같습니다.

| 항목 | 현재 처리 | 다음에 필요한 확인 |
|---|---|---|
| 최초 혼합 예보의 auto/fast | `POLICY_NOT_READY`; slow의 명시 집합은 별도 적용 | PL/C/A의 최초 기준 날씨 결정 |
| 테마 세부 정렬 | 승인 mood의 기존100/0 가점만 적용 | 부분 일치·추가 판단·최종 정렬 관계 |
| 실제 검수·적격 규모 | 없는 mood/악기/검수값을 생성하지 않음 | 실제 자료·근거·READY 발행과 필터 결과 |
| 공통 계약/이벤트 버전 | 기존 JSON 값을 유지. C PendingEvent는 정식 발행 envelope가 아님 | 문서/fixture `.2`와 이벤트 envelope `.1` 관계 및 B 통합 |
| 실제 환경·보관·호출 예산 | 고정 검증과 운영 연결을 구분 | INF/B/A 연결, 만료/보관 정책, Gemini 접근·예산 |

## 3. 분야별 작업 라우팅

| 작업 분야·태스크 연결 | 읽는 순서 | 현재 코드 진입점 | 함께 확인할 검증·영향 |
|---|---|---|---|
| CSV 입력·정제 — M-01~M-05, M-06 협력 | 음악 통합 계약2/3절 → [음악 인계](../handoff/music/README.md)의 컬럼·변환 → 테이블 | [normalize.py](../../pipeline/music/normalize.py), [stage_music.py](../../backend/music/management/commands/stage_music.py) | 원본20개/결과19개·헤더·NULL/0·HALF_UP·검수False 보존·장르 합집합·충돌 격리·원본 데이터 불변. 아래 변환 테스트를 실행 |
| 음악 저장·조회·발행 — A-05/A-06·Q-01 | 음악 인계의 테마/장르 → [테이블 구조](../handoff/music/테이블_구조_설계.md) → 통합 계약6절 | [음악 모델](../../backend/music/models.py), [catalog.py](../../backend/music/catalog.py), `backend/music/migrations/` | PK/FK/복합키·활성approved·곡당 한 행·검수 우선·카탈로그 해시/버전·발행 실패 시 기존 버전 보존 |
| 날씨 점수·취향·필수 필터 — R-02/R-03 | 통합 계약4/5절 → [선곡 규칙](../handoff/music/플레이리스트_생성_규칙.md) → 날씨 정규화/분류 | [policy.py](../../backend/recommendation/policy.py), [weather.py](../../backend/recommendation/weather.py) | 원래 PTY/SKY·180분 겹침·NULL/0·0~100·활성 분모·장르/speed·검수False 우선·초과 구간 유효성 |
| 시간 조합·Gemini — R-02/R-04 | 통합 계약6절 → 선곡 규칙 → [Gemini 설계](../product/카페_음악_서비스_3차_Gemini_API_추천_설계.md)의 응답/실패 계약 | [solver.py](../../backend/recommendation/solver.py), [provider.py](../../backend/recommendation/provider.py) | 176/180/184±1ms·정확히→초과→부족·거리/Q/ID·UNKNOWN 구분·부모 전체N//5(최소1)·등록밖/중복/이유 누락·실패 시 부모 유지 |
| 요청·제외·승인·복구 — R-05 | 설계도6/7절 → [공통 계약](../product/3차_공통_개발_계약과_검증_기준.md)의 소유/revision/멱등 → 통합 계약5.2/6절 | [urls.py](../../backend/cafe/urls.py) → [api.py](../../backend/recommendation/api.py) → [inputs.py](../../backend/recommendation/inputs.py)/[service.py](../../backend/recommendation/service.py) → [모델](../../backend/recommendation/models.py)/[worker.py](../../backend/recommendation/worker.py) | 엄격 타입·소유/CSRF·동일 키 재전송 우선·전체 제외 교체·취소 연결·원자 저장·사이클409·승인 조건·lease 세대/토큰·과거 스냅샷 |
| 공개 화면·날씨 패널 — W-06/U-01 | 서비스 화면 흐름 → 설계도3/6/7절 → [메인 시안](../assets/mockups/05-main-v8-compact-feedback-no-language.png) → 적용 도메인 계약 | [main.tsx](../../frontend/src/main.tsx) → [PublicPage.tsx](../../frontend/src/PublicPage.tsx), [api.ts](../../frontend/src/api.ts), [types.ts](../../frontend/src/types.ts), [style.css](../../frontend/src/style.css) | 지역만 필수·초기 미선택·조건 미반영·생성 잠금·첫 곡 커버/공통 대체·메인 시간 비표시·앞3시간/실황 구분·PC/모바일·오래된 응답 격리 |
| 평가·관리자 제외 이력 — U-02/F-07/Q-04 협력 | 설계도6-8/6-9 → 공통 계약 → [JSON 계약](../contracts/3차_공통_API_이벤트.schema.json)·[고정 예시](../fixtures/3차_공통_계약_예시.json) | [Feedback.tsx](../../frontend/src/Feedback.tsx), PublicPage.tsx, [AdminPages.tsx](../../frontend/src/AdminPages.tsx) | GET reaction/rating과 PUT value 대응·결과 버전 귀속·평가 선택 사항·실패와 제외 실패 구분·동일 키 재시도·ADMIN+피드백 권한·검색/커서/as_of·당시 조건/곡 |
| 로그인·음악 관리 화면 — I-05/M-06/A-03/A-04 협력 | 서비스 로그인/관리 흐름 → 설계도3/7절 → B 공통/관리 API 계약 | AdminPages.tsx, api.ts, main.tsx | 역할 선택 없음·서버 landing_path/허용 메뉴·원본/결과 스키마·행별 오류·검수와 등록/READY 분리. 관리 DTO는 B와 대조 |
| 펭귄 안내 — U-03~U-05 | 서비스 안내 흐름 → 설계도3-5 → [확정 PNG](../assets/penguin/penguin-guide-first.png) | [Guide.tsx](../../frontend/src/Guide.tsx), PublicPage.tsx, `frontend/public/penguin-guide-first.png` | 공통 원본·수동 시작·1/3~3/3·위젯X/안내X/Esc·초점 복원·저장 실패·실제 음악/광고 이벤트 격리 |
| 공개 배너 — AD-04, AD-05/AD-06 협력 | [광고 정책](../product/3차_광고_운영_회의_결정사항_목록.md)의 채택 규정 → 설계도9절 → B의 실제 delivery/측정 인계 | [Banner.tsx](../../frontend/src/Banner.tsx), PublicPage.tsx, style.css | 상하단 일반 흐름·독립 실패·50%/연속1초·탭/이미지/안내 조건·valid_until·3초 중단·동일 event_id. 실제 측정 검증은 아직 대기 |
| 환경·실행·인계 | 본 문서 → 실행·연결 인계 → 해당 분야 계약 | [settings.py](../../backend/cafe/settings.py), `backend/.env.example`, `frontend/.env.example`, 잠금 파일 | 모의/실제 구분·설정 이름만 기록·실제 키 제외·A/B/INF 호출 경계·버전/기동/종료·실측/복구 기록 |

날씨를 수정하는 경우 [01 수집/지역](../handoff/weather/01_날씨_수집과_지역매핑.md) → [02 정규화](../handoff/weather/02_날씨_데이터규격과_정제.md) → [03 저장](../handoff/weather/03_날씨_저장구조.md) → [04 호출/시험](../handoff/weather/04_API호출과_RDB적재시험.md) → [05 분류](../handoff/weather/05_날씨분류와_계절기준.md)에서 필요한 계약을 이어 읽습니다. 원문의 로컬 시험·과거 음악 분류 설명을 현행 음악 통합 계약보다 우선하지 않습니다.

이 브랜치에 없는 최신 ADS/저장 인계 파일을 현재 파일처럼 링크하지 않습니다. 이번 공개 배너 수정에서는 `git show ec0c7e3:docs/handoff/ads/README.md`와 `git show ec0c7e3:docs/handoff/ads/01_광고_화면_API와_측정_계약.md` 원문을 읽고 link_url/중첩delivery_id·상단 문맥 확보·표시/측정을 맞췄습니다. 전체 ADS/저장 인계의 전수 대조나 B 실제 서버 계약 확인을 뜻하지 않습니다.

화면 대조는 [메인05](../assets/mockups/05-main-v8-compact-feedback-no-language.png)·[로그인06](../assets/mockups/06-login.png)·[안내01](../assets/mockups/01-guide-region-weather-3step.png)을 직접 열어 수행합니다. 색상/배치만 아니라 입력 형태·반응 텍스트·목록 밖 별점·날씨/안내/광고 격리를 확인합니다. [Header](../../frontend/src/components/Header.tsx)·[WeatherPanel](../../frontend/src/components/WeatherPanel.tsx)·[Icons](../../frontend/src/components/Icons.tsx)는 PublicPage/Login이 공유하는 표시 진입점입니다. 목업의 예시 곡 수/날씨를 실제 값으로 고정하거나 전체 PNG를 화면으로 붙이지 않습니다.

## 4. 코드 초안의 책임 경계

| 위치 | 책임 | 변경 시 지킬 경계 |
|---|---|---|
| `pipeline/music/` | 원본 기반 변환·검증·충돌 보고 | HTTP 요청·화면 상태·원격 API 호출을 넣지 않음 |
| `backend/music/` | 음악4개 모델·조회·로컬 적재·불변 카탈로그 발행 | 사용자 결과/평가 테이블을 음악4개에 포함해 세지 않음 |
| `backend/recommendation/policy.py` | 점수·매핑·필수 필터·최초 허용 범위 | DB/HTTP/SDK와 분리. 미정 테마 가점을 추가하지 않음 |
| `solver.py` / `provider.py` | 기본 규칙 시간 조합 / 명시 Gemini 재설정 | 실패한 모델 응답을 solver로 보정하거나 기본 추천에서 Gemini를 호출하지 않음 |
| `api.py` / `inputs.py` | HTTP 매핑·엄격 입력 검증 | 화면 값으로 owner/role/총시간/점수/검증 성공을 신뢰하지 않음 |
| `service.py` | 상태 변경·멱등·revision·트랜잭션 조율 | 외부 호출 중 DB 잠금을 유지하지 않음. B 공통 outbox를 별도 규격으로 복제하지 않음 |
| `worker.py` | claim/heartbeat·계산·최종 검증·유효 lease 완료 | API202와 작업 성공을 구분. 실행 중인 초안을 재조회해 입력을 바꾸지 않음 |
| `frontend/src/` | 공개·로그인·음악/이력 화면·안내·공개 배너·API 연결 | B의 인증/평가/광고 서버나 A의 수집 파이프라인을 프론트엔드로 대체하지 않음 |
| `backend/cafe/` | C를 실행하는 통합용 호스트 초안 | B의 공통 프로젝트에 연결할 때 URLconf/설정·guest를 조율. 중복 공통 서버를 운영 완료로 취급하지 않음 |

공통 로그인·음악 관리·관리자 제외 이력의 **화면은 C**, 서버 인증/권한·관리/평가 API는 B입니다. 광고 관리 화면은 B, 공개 배너 배치는 C입니다. A는 날씨 사실·유효성을 공급하고 C는 이를 점수/화면에 연결합니다. INF는 실제 배치·접속·운영을, PL은 분류/수용 정책을 조율합니다.

## 5. 코드와 문서 정리 기준

### 코드 초안

- 현재 작성된 실행 코드를 초안의 출발점으로 유지합니다. 같은 기능의 `v2`, `new`, `final` 사본을 만들거나 테스트용 성공 경로를 운영 API처럼 중복 구현하지 않습니다.
- Python 모듈은 `snake_case.py`, React 컴포넌트는 `PascalCase.tsx`를 사용하고 기존 폴더 책임을 따릅니다. 새 디렉터리는 실제 책임이 생길 때 추가합니다.
- UI 상태/표시, API 직렬화, 업무 검증, DB 조율, 외부 어댑터를 구분합니다. 큰 PublicPage/AdminPages를 분리할 때도 요청 본문·잠금·revision·멱등 키·실패 보존 의미를 유지하고 관련 검증을 실행합니다. 이 문서 작성 자체로 일괄 분리를 수행한 것은 아닙니다.
- 원본 값·정규화 값·승인 연결·READY 카탈로그·당시 스냅샷을 구분합니다. 현재 곡 값으로 과거 결과/이벤트를 복원하지 않습니다.
- 미연결 기능은 안전하게 실패하거나 연결 대기로 표시합니다. 임의 분류·권한·외부 성공·통계를 생성하지 않습니다. 합성 자료는 명시적 `C_LOCAL_DEMO`와 `is_test`로 구분합니다.
- B/A 어댑터의 상세 DTO가 아직 임시인 곳은 실행 인계에 남기고, 그 형식을 공통 제품 계약으로 확정했다고 표현하지 않습니다.
- 공개한 migration은 과거 파일을 다시 쓰지 않고 새 migration으로 변경합니다. 실제 운영 DB의 물리 변경·데이터 변환은 별도 인계와 검증을 거칩니다.

### 문서와 산출물

| 종류 | 기록 위치 | 기록할 내용 |
|---|---|---|
| 정책·API·저장·수용 계약 | `docs/product/`, `docs/contracts/`, `docs/fixtures/` | 확정 값·의미·버전·고정 기대값. 제품 변경 시 연결된 기준 문서를 함께 대조 |
| 수령 자료 | `docs/handoff/<분야>/` | 출처/원문·수령 상태·채택 범위. 보관본을 현행으로 승격하지 않음 |
| 정리 기준·작업 진입점 | 이 문서 | 문서→코드→검증 라우팅, 담당 경계, 정리 순서 |
| 실행·오류·연결 방법 | `docs/runbook/C_구현과_연결_인계.md` | 설정 이름·명령·현재 어댑터·실제 연결 전제·복구 방법 |
| 검증 결과 | `docs/acceptance/` | 대상 코드/환경·입력·기대/실제·증거·미실행·보류 |
| 로컬 생성물 | `artifacts/`, `frontend/dist/`, 로컬DB | 보고서·스크린샷·빌드·검증DB. 현재 Git 제외 상태를 유지 |

문서의 작성일은 보존하고 실제 수정일만 갱신합니다. 원본 CSV·실제 비밀값·생성물·가상환경·node_modules를 코드 초안에 포함하지 않습니다. README는 요약/진입점이며 계약을 독립된 다른 값으로 복제하지 않습니다.

## 6. 검증과 완료 기록

| 바뀐 내용 | 우선 실행할 검증 | 현재 검증 코드 |
|---|---|---|
| 변환·점수·필수 필터·시간·Gemini 의미 검증 | 입력/경계·정확 계산·실패 분류 | [test_policy.py](../../backend/recommendation/tests/test_policy.py) |
| 요청·소유·제외·승인·불변 결과 | API 소유/CSRF·원자성·멱등/충돌·실패 보존 | [test_api.py](../../backend/recommendation/tests/test_api.py) |
| 음악 모델·태그 조회·발행 | 제약·곡당 한 행·검수False·발행 보존 | [음악 테스트](../../backend/music/tests.py), migration 차이 검사 |
| 공개/안내/로그인·모바일 연결 | 타입/빌드 후 실제 브라우저 흐름 | [smoke.cjs](../../frontend/scripts/smoke.cjs) |
| 평가 화면·재시도 | GET/PUT 계약·전환/취소·실패 시 다른 기능 유지 | [feedback-smoke.cjs](../../frontend/scripts/feedback-smoke.cjs). B 고정 응답 검증이며 실제 B 서버 검증은 아님 |
| 공개 배너·문맥·측정 | 상단→하단·link_url/delivery_id·연속노출·동일 본문 재전송·안내 격리·실패3초·기한/캐시 | [ad-smoke.cjs](../../frontend/scripts/ad-smoke.cjs). B 계약 고정 응답이며 실제 광고 DB/운영 통계 검증은 아님 |
| 선택 조건 비교 | 정규화된 선택의 동일/변경 판정 | [api.test.ts](../../frontend/src/api.test.ts) |
| 라우팅/문서 링크만 수정 | 로컬 링크 존재·파일 경로·담당/상태 표현·diff 공백 | 해당 문서 검사. 동작이 바뀌지 않았다면 전체 앱 테스트를 형식적으로 반복하지 않음 |

완료 기록에는 다음을 남깁니다.

1. 요청 범위·태스크 ID·변경한 동작과 파일
2. 읽은 계약/코드와 실제 확인 범위
3. 실행한 검증의 환경·입력·기대/실제 결과
4. 문서 대조·고정 계산·모의 API·실제 서버·운영 복구 중 어떤 증거인지
5. 남은 오류/미정·차단 범위·필요 자료·연결 담당

문서 링크 확인을 실행 테스트로, B 고정 응답을 실제 저장/집계로, SQLite 단일 작업자를 PostgreSQL 다중 작업자 검증으로 보고하지 않습니다. 새 기능·환경 변경·실패·미해결 위험이 있을 때 필요한 검증을 추가합니다.

## 7. 다음 작업의 정리 순서

1. **공유 계약 대조:** 과거 브랜치 문서와 최신 사용자 결정의 충돌을 목록화하고 C에 영향을 주는 API·필드·버전·태스크를 맞춥니다. 보류된 이벤트 버전은 임의 수정하지 않습니다.
2. **A/B 어댑터 연결:** 날씨/지역·공통 소유/CSRF·평가·관리·광고의 실제 입출력을 확보하고 C 초안의 임시 DTO와 대조합니다. 한 도메인씩 연결하고 실패/권한·상태 보존을 검증합니다.
3. **추천·음악 실자료 연결:** 실제 검수 자료와 불변 발행을 연결하고 적격 규모·176~184분 성립·탐색/후보 확장·발행 실패를 확인합니다.
4. **운영 환경 검증:** INF와 실제 PostgreSQL/음악DB·다중 claim/lease·outbox·백업/복구·보관·Gemini 설정을 확인합니다. 외부 호출/배포를 이 문서만으로 실행하지 않습니다.
5. **내부 코드 정리:** 위 연결에서 드러난 책임 중복을 필요한 모듈로 분리하고 같은 검증으로 동작을 보존합니다. 무관한 일괄 포맷·재설계·태스크 선행 변경은 섞지 않습니다.

이 순서는 착수·정리 안내이며 기존 태스크의 직접 선행 관계를 대체하지 않습니다. 커밋·푸시·PR·병합·배포·외부 서비스 변경은 각각 사용자가 명시적으로 요청한 경우에만 수행합니다.
