# 카페 날씨 기반 음악 서비스

2026-10-18 최신 구현: 현재 HTTP 입력 계약은 [phase3-20261016.3](./config/contracts/basic-request.phase3-20261016.3.schema.json)입니다. 지역 생략/null/공백은 날씨 OFF로 정규화합니다. 광고 proof 전달·배달 유지, 운영 GENERAL 필터, 카탈로그 등록 순번·제외 revision 조회와 CI의 현재 기준은 [통합 정합성 수정 라우팅](./docs/development/통합_정합성_수정_변경_라우팅.md)을 우선합니다. 수령 문서와 과거 계약은 보존합니다.

지역의 날씨와 음악 취향을 반영해 카페 운영자에게 선곡표를 제공하는 서비스입니다.

- 수정일: 2026-10-18
- 현재 단계: develop에 광고·추천/음악·공개 화면·날씨 코드를 수령한 뒤 폴더/개발 경로를 정리했습니다. 공통 인증·피드백·음악 관리·광고 인증·날씨 어댑터를 통합 작업 중이며 실제 운영 DB/호스트 연결은 별도 검증 대상입니다.

## 통합 작업 시작점 — 2026-10-16

초기 기준은 `develop@b4499c5`이며 광고(PR #5), 추천·음악·공개 화면(PR #6), 날씨(PR #7)를 수령했습니다. 이후 인프라·공통 연결과 음악/재생을 PR #8/#9로 반영했고 PR #10에서 feature 이력을 보존해 통합했습니다. 이번 수정의 출발점은 `develop@160a66c`이며 실제 운영 연결 완료와 구분합니다.

현재 실제 경로·분리된 실행 환경·이동 전후 매핑·검증은 [통합 폴더 변경 라우팅](./docs/development/통합_폴더_정리_변경_라우팅.md), 분야별 문서 진입은 [개발 문서 색인](./docs/development/README.md), 설정 위치는 [환경 설정 안내](./config/environments/README.md)를 먼저 확인합니다. 수령 원문은 보존하며 예전 코드 경로는 변경 라우팅의 매핑으로 찾아갑니다.

추천·음악의 기존 구현/검증 이력은 [C 실행 인계](./docs/runbook/C_구현과_연결_인계.md)와 [C 검증 기록](./docs/acceptance/C_로컬_검증_20261015.md), 광고는 [광고 실행 인계](./docs/runbook/광고_서버_개발_준비.md)를 따릅니다. 과거 실행 결과와 이번 경로 변경 검증을 구분합니다.

최신 사용자 선택으로 YouTube는 **API 키 없는 외부 연속 재생 기본·접이식 iframe 보조**입니다. 기존 대시보드에 URL/CSV 등록·미연결 검수와 외부/삽입 독립 검수·철회를 연결했습니다. 전체GENERAL86,485곡과 불변 추천 결과를 유지하고 LLM·원격 검색을 기본 경로에서 호출하지 않습니다. 고정 승인47개의 YouTube 목록 수용과 실제1→2→3 자연 진행을 확인했으며, 새 일반 추천의 미연결 곡은 n/m곡으로 명시합니다. [최신 검증](./docs/acceptance/YouTube_키없는_등록과_검수_검증_20261016.md)·[변경 라우팅](./docs/development/YouTube_키없는_등록과_검수_변경_라우팅.md)·[운영 가이드](./docs/development/music/YouTube_로컬_재생_기획과_구현_가이드.md)를 먼저 확인합니다. 계정 자동 저장·물리 음향·Premium·47곡 전체 완주·공유 ADMIN/AWS는 별도입니다. [앞 단계 iframe 기록](./docs/acceptance/대시보드_중앙_YouTube_iframe_검증_20261016.md)과 [일반 후보 복구](./docs/acceptance/일반_추천_후보와_재생시험_분리_검증_20261016.md)는 이력으로 보존합니다.

## 1. 프로젝트 소개

운영자가 동 단위 지역을 선택하면 현재 날씨와 예보를 확인하고 매장 분위기에 맞는 선곡표를 받을 수 있습니다. 보컬·빠르기·테마·장르는 선택 사항이며 기본 추천은 비로그인으로 이용합니다.

3차에는 규칙 기반 추천·Gemini 재설정·평가·관리자 기능·상하단 광고를 개발합니다. 이번 로컬 YouTube 외부 재생은 위 예외 범위이며 계정에 재생목록을 자동 저장하지 않습니다. 4차 사용자 계정·선곡표 저장/이력·결제와 계정 외부 연결은 별도 범위입니다.

## 2. 주요 기능

| 기능 | 제공 방향 |
|---|---|
| 지역·날씨 | 동 단위 지역, 현재 날씨와 앞 3시간 예보 표시. 수집/조회는 6시간 범위 |
| 기본 추천 | 검수된 음악과 날씨·취향을 사용한 규칙 추천 및 시간 조합 |
| 취향 선택 | 보컬·빠르기·테마/장르 복수 선택. 국가·언어 기능은 3차에서 제외 |
| 제외·재설정·승인 | 제외 초안 저장, Gemini 3.8 Flash(`gemini-3.8-flash`) 명시 재설정, 검증된 결과 버전 승인 |
| 음악 평가 | 곡별 좋아요/싫어요, 선곡표 전체 별점 1~5점과 평가 취소 |
| 사용 안내 | 같은 펭귄 원본을 사용하는 3단계 안내와 다시 보기 |
| 관리자 | 로그인·음악 등록/검수·제외 피드백 조회·광고 운영/통계 |
| 광고 | 상하단 배너·별도 측정. 익명 문맥/광고별 노출60초·클릭5분 제한, 지연5분·발생일KST, 광고 원본/delivery90일·집계/예상 원장/관리 변경 이력365일 |

표준 선곡 목표는 180분, 허용 범위는 176~184분이며 자동 단축은 사용하지 않습니다. 메인에는 재생시간을 표시하지 않고 서버에서 검증합니다. 사용자 선택 ON/OFF·기본 ON을 적용합니다. ON은5날씨×2패턴의 E/A≥20·W≥75 뒤 활성 선호75:25, OFF는 날씨 독립 P_OFF를 사용합니다. 일반 추천은 명확한 시즌·행사곡을 제외하고 애매한 곡·미판정은 보류하며, 필터 후 새 목록의 시간을 검증합니다. 혼합 최초 auto/fast·실제 검수·환경 등 미정은 임의 확정하지 않습니다.

화면 참고: [메인](./docs/assets/mockups/05-main-v8-compact-feedback-no-language.png) · [로그인](./docs/assets/mockups/06-login.png) · [광고 관리자](./docs/assets/mockups/07-admin-ads.png)

## 3. 기술 스택

다음 표는 현재 수령 코드의 실행 스택입니다. 목표 문서 계약은 FastAPI/Pydantic·SQLAlchemy/Alembic이며 Django에서의 이식 완료를 뜻하지 않습니다. 실제 설치 버전·접속·실행 결과는 환경 검증과 구분하고 [음악·재생 정본 라우팅](./docs/development/음악_재생_정본_변경_라우팅.md)에서 차이를 확인합니다.

| 영역 | 기술/구성 |
|---|---|
| 프론트엔드 | React · TypeScript · Vite |
| API | Python · Django · Django REST Framework |
| 온라인 업무 DB | PostgreSQL · Django ORM/migrations (로컬 고정 검증은 명시적 SQLite 모드) |
| 규칙 추천 작업자 | Python · OR-Tools CP-SAT |
| 명시 재설정 | Gemini 3.8 Flash (`gemini-3.8-flash`) · Google Gen AI Python SDK (`google-genai`) |
| 이벤트 처리 | Kafka · Spark |
| 로그·피드백 | PostgreSQL · B 담당 실제 파이프라인 연결 대기 |
| 날씨 이력·최신 조회 | MongoDB · Elasticsearch |
| 날씨 원문 보관 | 로컬 파일 · S3 |
| 환경 | 로컬 클러스터 연결 검증 후 AWS 이전 |

음악은 저장소에 포함한 [spotify_dataset.csv](./docs/handoff/music/spotify_dataset.csv)와 추천·표시18개＋검수 보조1개를 사용합니다. 음악4개 테이블의 ORM 모델/초기 migration은 작성했으며 실제 음악 RDB 제품/접속/운영 DDL 확정과는 구분합니다. [음악 인계](./docs/handoff/music/README.md)와 C 실행 인계를 함께 확인합니다.

## 4. 시스템 구성도

아래는 구현할 구성이며 설치·운영 연결 완료를 나타내지 않습니다.

```mermaid
flowchart TB
    subgraph DATA[데이터 준비]
        CSV[음악 CSV] --> REVIEW[원본 변환·분류 검수]
        REVIEW --> MUSIC[검증된 음악 RDB 카탈로그]
        KMA[기상청 API허브] --> COLLECT[날씨 수집]
        COLLECT --> RAW[원문: 로컬·S3]
        COLLECT --> WK[Kafka]
        WK --> WS[Spark 정규화]
        WS --> MONGO[MongoDB 날씨 이력]
        MONGO --> ES[Elasticsearch 최신 조회]
    end
    subgraph SERVICE[추천 서비스]
        WEB[공개 화면·지역/취향 선택] --> API[Django]
        ES --> API
        API --> WORKER[추천 작업자]
        MUSIC --> WORKER
        WORKER --> RULE[기본: 규칙·시간 조합]
        WORKER --> GEMINI[명시 재설정: Gemini]
        RULE --> CHECK[필수 조건·시간·날씨 검증]
        GEMINI --> CHECK
        CHECK --> DB[PostgreSQL 작업·결과·업무 상태]
        DB --> API
        API --> RESULT[선곡표 확인·제외·평가·승인]
    end
    subgraph FEEDBACK[피드백 축적]
        RESULT --> SAVE[API 상태·피드백·outbox 원자 저장]
        SAVE --> FK[Kafka]
        FK --> FS[Spark 정제·집계]
        FS --> LOGDB[PostgreSQL 로그·피드백]
    end
```

광고는 별도 도메인에서 관리해 공개 화면의 상하단 배너에 연결합니다. 광고 지표는 음악 피드백과 분리합니다. 상세 API·저장·예외 흐름은 [구현 설계도](./docs/product/카페_음악_서비스_구현_설계도.md)를 참조합니다.

## 5. 폴더 구조와 담당 분야

```text
frontend/
  src/features/             공개 추천·날씨·음악 선택·평가·광고 배너·안내·관리 화면
  src/shared/               공통 API 클라이언트·타입
  src/components/           공통 헤더·아이콘
  tests/                    개발 API 프록시 연결 검증
backend/
  cafe/                     추천/공통 API 호스트 설정·URL
  recommendation/           추천 API·작업자·결과/평가
  music/                    음악 모델·발행·migration
  weather/                  지역·도로명·날씨 조회 함수(HTTP 어댑터 연결 대기)
ad-server/
  backend/                  독립 광고 Django·MongoDB·광고 작업자·로컬 도구
  config/environments/ads/   광고 로컬 DB 환경
pipeline/
  music/                    음악 입력·정제
  weather/                  날씨 수집·정규화·저장/발행·Spark 패키징
music_playback/             시즌 판정·일반 ON 후보/180분 재구성·오프라인 검증 CLI
prototype/youtube-player/   개발 검수 보조 iframe·수동 매핑 확인(사용자 주진입 아님)
analysis/weather_music_20261016/general/  기존 입력을 보존한 필터 후 분석 산출물
config/environments/        실행 단위별 환경 위치 안내
tests/                     날씨 경로·Spark ZIP 회귀 검증
docs/
  development/              현행 코드 경로·변경 라우팅·문서 색인
  backend-routing/          기존 광고 파일별 인계 색인
  handoff/                  수령 원문(변경하지 않음)
  product/                  제품 기준·보관 이력
  runbook/ acceptance/       기존 실행·검증 이력
  contracts/ fixtures/      API 계약·고정 예시
  assets/                   목업·공통 펭귄 원본
```

광고와 추천은 현재 별도 Django 실행 단위입니다. 같은 가상환경에 의존성을 합치지 않습니다. Vite에서 광고 API는 기본 8000, 나머지 API는 기본 8001로 전달합니다. 공유 ADMIN/guest·지역 HTTP API·날씨 추천 입력 어댑터와 운영 배포는 이 폴더 정리로 완료되지 않습니다.

| 담당 | 분야 |
|---|---|
| A | 날씨 수집·지역 매핑·정규화·저장/조회 코드와 검증 |
| B | 공통 백엔드·피드백·광고 API/집계·광고 관리 화면·통합 조율 |
| C | 공개 프론트엔드·공통 로그인/음악/피드백 화면·추천·음악 데이터 |
| INF | 설치·접속·운영 환경·CI/보호·배포/복구 |
| PL | 기획·UX·분류/수용 기준·일정·검수/시연 취합 |

실제 이름과 일정은 미배정이며 상세 경계는 [AGENTS.md](./AGENTS.md)를 따릅니다.

## 6. 개발 시작 방법

1. [개발 문서 색인](./docs/development/README.md)에서 제품 기준 → 분야별 인계 → 현재 코드 경로 순서로 확인합니다.
2. [환경 설정 안내](./config/environments/README.md)에 따라 추천·광고·날씨 의존성과 설정을 분리합니다. 실제 비밀값은 추적하지 않습니다.
3. 추천 API는 기존 루트 가상환경에서 `python -m backend.manage runserver 127.0.0.1:8001`, 광고 API는 광고 가상환경/폴더에서 `python manage.py run_ads_dev --port 8000`을 사용합니다. 해당 실행 모드의 필수 설정과 공유 인증 대기를 먼저 확인합니다.
4. 프론트는 `frontend/`에서 `pnpm dev`로 실행합니다. 개발 프록시 목적지는 `.env.local`에서 지정할 수 있습니다. 광고 sandbox의 단독 8001 실행과 추천 API 8001을 동시에 사용하지 않습니다.
5. 날씨 명령은 저장소 루트에서 `python -m pipeline.weather.run_collector`, `python -m pipeline.weather.submit_spark`, `python -m pipeline.weather.publish_admin`입니다. 이 명령들은 실제 외부 호출/저장을 수행하므로 INF/A 설정과 준비가 필요하며 이번 정리에서 실행하지 않았습니다.

날씨 `.env` 인계 위치는 `pipeline/weather/.env`입니다. 기상청 KMA_API_KEY는 실행 환경변수가 없을 때 이 파일에서 자동으로 읽습니다. Kafka·DB 등 다른 설정과 추천 서버 설정은 프로세스 환경변수로 전달해야 합니다. [날씨 환경설정 변경 라우팅](./docs/development/날씨_환경설정_변경_라우팅.md)을 확인합니다. 추천·광고 작업자/자료 준비와 실제 실행의 자세한 경계는 [통합 폴더 변경 라우팅](./docs/development/통합_폴더_정리_변경_라우팅.md)을 따릅니다.

## 7. 협업 방법과 상세 문서

브랜치 기본안은 `main`(검증된 기준/릴리스)·`develop`(통합)·작업별 브랜치입니다. develop에서 분기해 PR·리뷰로 통합하고 검증 후 main에 반영합니다. 원격 저장소와 main/develop은 존재합니다. 보호 설정·필수 CI의 실제 적용 여부는 별도 확인 대상이며 상세 절차는 [CONTRIBUTING.md](./CONTRIBUTING.md)를 따릅니다.

| 문서 | 확인할 내용 |
|---|---|
| [서비스 기능 및 사용자 흐름](./docs/product/카페_음악_서비스_기능_및_사용자_흐름_정리.md) | 기능·화면·3차/4차 범위 |
| [구현 설계도](./docs/product/카페_음악_서비스_구현_설계도.md) | API·저장·작업 처리·예외 |
| [음악 통합 계약](./docs/product/3차_음악_정책_통합_계약.md) | 현행 음악18개/검수 보조·필수 필터·규칙/Gemini·176~184분 |
| [Gemini 재설정 설계](./docs/product/카페_음악_서비스_3차_Gemini_API_추천_설계.md) | 외부 응답·후보 제한·실패/부모 보존 |
| [구현 태스크](./docs/product/카페_음악_추천_서비스_3차_구현_태스크.md) | 작업 ID·선행 관계·완료 조건 |
| [공통 개발 계약](./docs/product/3차_공통_개발_계약과_검증_기준.md) | 기술·입출력·상태·공통 검증 |
| [확인·인계 목록](./docs/product/3차_사용자_확인과_담당자_인계_목록.md) | 남은 결정·담당 자료·보완 사항 |
| [구현 결정과 원문 보관](./docs/product/3차_구현_결정과_익명문맥_원문보관_가이드.md) | 최신 결정·익명 소유·로컬/S3·인프라 수령 상태 |
| [광고 정책과 결정사항](./docs/product/3차_광고_운영_회의_결정사항_목록.md) | 광고 운영·측정·초기 정책과 남은 결정 |
| [음악 컬럼 정의](./docs/handoff/music/음악_분류_컬럼_정의.md) | 음악18개·원본 변환·검수 우선 입력 |
| [음악·재생 정본 라우팅](./docs/development/음악_재생_정본_변경_라우팅.md) | ON/OFF·시즌 적격·원문/현재 코드/목표 스택 차이·단계별 구현과 검증 연결 |
| [기존 대시보드 YouTube 연결 가이드](./docs/development/music/YouTube_로컬_재생_기획과_구현_가이드.md) | PublicPage 유지·곡별 검색/영상 직접 열기·전체 네이티브 목록 검증·iframe 검수 이력 분리 |
| [날씨 인계 자료](./docs/handoff/weather/01_날씨_수집과_지역매핑.md) | 수집/지역 매핑부터 정제·저장·분류로 연결 |
| [인프라 인계 안내](./docs/handoff/infra/README.md) · [AWS 구축 계획](./docs/handoff/infra/AWS_인프라_구축_계획서.md) | 로컬 개발에서 AWS 이전으로 연결·원문 수령 상태·서비스 조율 사항 |

안내 시안: [1 지역·날씨](./docs/assets/mockups/01-guide-region-weather-3step.png) · [2 음악 취향](./docs/assets/mockups/02-guide-music-3step.png) · [3 선곡표](./docs/assets/mockups/03-guide-playlist-3step.png). 공통 자산은 [확정 펭귄 PNG](./docs/assets/penguin/penguin-guide-first.png)를 재사용합니다.

이전 정책은 `docs/product/archive/`에 보관합니다. 시안·인계 자료의 시험 이력과 현행 계약은 구분하며 미확보 코드 링크는 실제 실행 경로로 간주하지 않습니다.

현재 기능 연결의 구현·시험·남은 운영 연결과 2026-10-16 재지정된 날씨 문서 기준은 [서비스 통합 구현 변경 라우팅](./docs/development/서비스_통합_구현_변경_라우팅.md)을 우선 확인합니다. 수령 원문은 보존하며, 날씨의 최신 저장 방향은 PostgreSQL 매핑 / Elasticsearch 최신·공통 특징 / 원천 응답 파일 미보관입니다.
