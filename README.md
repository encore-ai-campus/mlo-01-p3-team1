# muther. - "오늘의 날씨를 들어보세요."
### *날씨와 취향을 담은 3시간의 선곡표*
<img src="./docs/assets/screenshots/00-muther-logo.png" alt="뮤더 로고와 펭귄 — 오늘의 날씨를 들어보세요" width="270">



<img src="./docs/assets/screenshots/06-home-updated.png" alt="뮤더 메인 화면 — 광고·날씨·추천 플레이리스트" width="400">

## 1. 팀원 소개

| 이름 | 역할 | 담당 업무 |
|---|---|---|
| 안길찬 | 팀장 | 프론트 및 백엔드·음악 추천 개발 |
| 김건우 | 팀원 | 프로젝트 총괄·백엔드·광고 개발 |
| 김민서 | 팀원 | 음악 데이터 분류·검수 |
| 오재석 | 팀원 | 날씨 데이터 수집·처리 |
| 이인건 | 팀원 | 인프라 구축·배포·운영 |

## 2. 프로젝트 개요

### 프로젝트명

- 뮤더 - 날씨 기반 플레이리스트 생성 서비스

### 프로젝트 기간
- 2026.10.15(목) - 2026.10.19(월)

### 프로젝트 소개

뮤더는 music과 weather의 합성어로, 카페·음식점 등 매장 운영자가 약 3시간의 선곡표를 받고 조정하는 서비스다. 날씨 반영 여부와 보컬·빠르기·테마·장르를 선택해 취향을 반영한다. 로그인 없이 이용하며 지역을 선택하지 않으면 날씨를 제외한 추천으로 처리한다.

### 프로젝트 필요성과 목표

직접 곡을 찾고 목록을 구성·조정하는 부담을 줄이는 것이 목표다. 준비 시간과 체감 부담, 만족도·날씨 적합성은 사용자 평가로 확인한다. 날씨 반영의 효과는 ON/OFF 비교로 살피며, 기능 구현과 사용자 효과를 구분한다.

3차의 광고 목표는 카페 광고의 게시·제어와 유효 노출·클릭·예상 사용량을 확인할 기반을 마련하는 것이다. 실제 매출이나 광고주의 지불 의사가 검증됐다는 의미는 아니다.

사업 목표·평가의 근거는 [BRD](./docs/BRD.md), 제품 기능과 수용 기준은 [PRD](./docs/PRD.md)를 참고한다.

### 서비스 구현 범위

| 구분 | 범위 |
|---|---|
| 3차 필수 | 비로그인 날씨 ON/OFF 추천, 일반곡 판정, 제외·재설정·평가·승인, 안내, 음악·피드백 관리, 카페 광고 관리·측정·집계, 운영·복구 검증 |
| 로컬 보조 검증 | YouTube 외부 연속 재생 연결, 보조 iframe, 음악 권한을 가진 관리자의 영상 등록·검수 |
| 4차 계획 | USER 계정, 본인 저장 선곡표·이력, 사용자 결제·유료 권한과 업종별 광고 매칭 |
| 이번 범위 제외 | 음원 파일 제공·자체 스트리밍, 외부 계정의 재생목록 자동 생성·저장. 기타 도입 여부는 BRD·PRD의 후속 범위를 따른다. |

YouTube는 검증된 영상만 원래 곡 순서대로 연결한다. 일부 곡만 연결되면 연결 곡 수·미연결 곡·재생시간 감소를 안내하며, 이를 전곡 또는 3시간 재생 완료로 보지 않는다. 운영 모드의 영상 검수는 허용하지 않는다.

### 사용자 흐름

1. 날씨 반영 여부와 취향을 선택한다. ON은 지역·유효 날씨를 확인하고, OFF는 지역 없이도 추천한다.
2. 선곡표를 확인하고 원하면 곡을 제외한다. 같은 조건의 다른 구성을 원하면 제외 저장 후 Gemini 재설정을 요청한다.
3. 곡별 반응·별점을 선택적으로 남기고 사용할 결과를 별도로 승인한다. 재생 연결은 사용자가 직접 선택한다.

ON에서 날씨 분류가 바뀌면 편집·미저장 제외·진행 중 작업이 없는 상태에서 같은 조건·제외 목록을 유지한 규칙 추천으로 갱신한다. 같은 분류나 OFF에서는 날씨만으로 재선곡하지 않는다. 실패 시 기존 결과를 보존하고 변경 전 날씨로 만든 결과임을 표시한다.

## 3. 기술 스택

| 영역 | 기술 | 역할 |
|---|---|---|
| 화면 | React · TypeScript · Vite | 공개 추천·로그인·음악/피드백·광고 관리 화면 |
| API | Python · Django · Django REST Framework | 입력·권한 검사, 작업 등록, 결과·관리 API |
| 온라인 업무·로그 DB | PostgreSQL · Django ORM · migrations | 계정·세션·작업·결과·평가·이벤트·피드백 원본/정제/집계 |
| 기본 추천 | Python 작업자 · OR-Tools CP-SAT · 정수 subset-sum | 필수 조건 검사와 시간 조합. 동일 점수 후보에는 subset-sum 경로 사용 |
| 명시 재설정 | Gemini 3.8 Flash (`gemini-3.8-flash`) · `google-genai` | 같은 조건·적격 후보에서 다른 선곡표 구성 |
| 이벤트 처리 | Kafka · Spark | 날씨·피드백 이벤트 전달, 정규화·정제·집계·재처리 |
| 음악 기준 저장 | PostgreSQL · 음악 속성 4개 테이블 · 불변 카탈로그 | ORM·migration 구현과 AWS 적재·발행 기록이 있으며 적재 체크포인트 등 운영 테이블은 별도 |
| 광고 업무 저장 | MongoDB 광고 전용 논리 DB · replica set 트랜잭션 | 광고·이미지·제공·판정·집계·예상 원장·관리 이력 |
| 날씨 저장·검색 | PostgreSQL · Elasticsearch | PostgreSQL 지역/격자 매핑, Elasticsearch 최신 자료·공통 특징 조회. 현행 날씨 경로는 MongoDB·원천 응답 파일 보관을 사용하지 않음 |
| 원본·배포 자료 | 로컬 파일 · S3 | 음악 원본은 로컬 보존, 운영 S3 보관은 명시 보류. S3 설치 artifact·체크포인트와 구분 |
| 외부 음악 연결 | YouTube 외부 링크 · IFrame Player | API 키 없는 외부 연속 재생 연결과 접이식 보조 플레이어. 로컬 검증과 AWS 적용 구분 |
| 문서·협업 | Markdown · Mermaid · GitHub | 설계 공유, 작업·리뷰·통합 관리 |
| 실행 환경 | 로컬 · AWS EC2/systemd · CloudFront · ALB · nginx | HTTPS 접속 페이지와 AWS 기본 추천 검증 기록 존재. 전체 기능 수용·장애 복구는 별도 |

공통 API와 별도 광고 API는 Django로 실행한다. 음악 원본의 운영 S3 보관은 사용자 결정으로 보류한 상태이며 로컬 원본·해시를 확인한다. 날씨 실행 경로는 PostgreSQL 지역 매핑과 Elasticsearch를 사용한다.

구현·배포 기록은 [통합 구현 기록](https://github.com/encore-ai-campus/mlo-01-p3-team1/blob/183ea87c7fb6f9878da51e51eb5c6408699374ee/docs/development/서비스_통합_구현_변경_라우팅.md)과 [AWS 배포 기록](https://github.com/encore-ai-campus/mlo-01-p3-team1/blob/183ea87c7fb6f9878da51e51eb5c6408699374ee/docs/development/INF_AWS_앱배포_변경_라우팅.md)을 참고한다. 문서와 코드의 확인 범위는 부록에서 구분한다.

### 시스템 구성도

```mermaid
flowchart TB
    subgraph WEATHER[날씨 수집과 조회]
        KMA[기상청 API허브] --> COLLECT[수집기]
        COLLECT --> WK[Kafka]
        WK --> WS[Spark 정규화]
        WS --> ES[Elasticsearch 최신 자료·공통 특징]
        MAP[PostgreSQL 지역·격자 매핑] --> WEATHER_API[날씨 조회 어댑터]
        ES --> WEATHER_API
    end
    subgraph MUSIC[음악 준비]
        CSV[음악 CSV] --> REVIEW[변환·분류·검수]
        REVIEW --> MRDB[음악 RDB 4개 테이블]
        MRDB --> CATALOG[버전이 고정된 추천 카탈로그]
    end
    subgraph SERVICE[선곡표 추천과 조정]
        WEB[React 공개 화면] --> API[Django API]
        WEATHER_API --> API
        API --> WORKER[추천 작업자]
        CATALOG --> WORKER
        WORKER --> RULE[ON/OFF·GENERAL 필터·규칙·시간 조합]
        WORKER --> GEMINI[명시 요청 시 Gemini]
        RULE --> CHECK[일반곡·조건·시간·ON 날씨 검증]
        GEMINI --> CHECK
        CHECK --> STATE[PostgreSQL 업무 상태·결과]
        STATE --> API
        API --> WEB
    end
    subgraph FEEDBACK[피드백 처리]
        API --> EVENT[PostgreSQL 상태·이벤트·outbox 원자 저장]
        EVENT --> FK[Kafka]
        FK --> FS[Spark 정제·집계]
        FS --> LOG[PostgreSQL 피드백·로그]
    end
    subgraph ADS[광고 운영]
        ADMIN[관리자 인증·광고 관리 화면] --> AM[광고 MongoDB]
        AM --> DELIVERY[광고 제공 API]
        DELIVERY --> BANNER[공개 상하단 배너]
        BANNER --> MEASURE[노출·클릭 수신과 판정]
        MEASURE --> AM
        AM --> STATS[5분 주기 통계·예상 원장]
        STATS --> ADMIN
        AM --> RELAY[관리 이력 내부 log_relay]
        RELAY --> LOG
    end
    BANNER -.-> WEB
    EDGE[CloudFront HTTPS·ALB·nginx] --> WEB
    WEB -. 사용자 명시 이동 .-> YOUTUBE[YouTube 외부 연속 재생·로컬 검증]
```

## 4. WBS 및 요구사항 명세서

아래 A/B/C/INF/PA는 BRD의 책임 단위다. 개인별 담당 업무는 상단 팀원 소개와 함께 확인한다.

| 작업 묶음 | 주담당·협력 | 작업내용·주요 산출물 |
|---|---|---|
| 요구사항·UX·수용 기준 | PA · A/B/C/INF 협력 | 입력·화면·범위·검수 기준, 확인할 결정과 시연 계획 |
| 실행·배포 환경 | INF · A/B/C 협력 | DB·Kafka·Spark·검색 환경, 접속·기동·배포·복구 절차, CI·보호 검증 |
| 날씨 | A · C/INF 협력 | 지역/격자 매핑, 수집·정제·저장·조회 코드, 정상·누락·만료 샘플과 검증 |
| 공통 백엔드·피드백 | B · A/C/INF 협력 | 인증·소유·업무 상태·이벤트 저장, 피드백 파이프라인, 관리자 이력 API |
| 음악·추천 | C · B/PA/INF 협력 | CSV 정제·음악 카탈로그, 규칙 추천·Gemini 재설정·검증. 관리/검수 API는 B와 연결 |
| 공개 화면·안내 | C · A/B/PA 협력 | 지역·날씨·선곡표·평가·승인, 공통 로그인·음악/피드백 화면, 펭귄 안내·공개 배너 |
| 광고 | B · C/INF/PA 협력 | B는 관리 화면·API·저장·측정/집계, C는 공개 배너 배치·반응형·화면 연결 |
| 통합 검증·인계 | B 통합 조율 · 전원 | 각 담당의 코드·데이터·권한 검증, INF의 환경/복구 검증, PA의 평가·시연 취합 |

작업별 ID·선행 관계는 [구현 태스크](https://github.com/encore-ai-campus/mlo-01-p3-team1/blob/183ea87c7fb6f9878da51e51eb5c6408699374ee/docs/product/카페_음악_추천_서비스_3차_구현_태스크.md)를 참고하되, 제품 범위와 수용 기준은 수정된 BRD·PRD를 함께 확인한다.

## 5. 요구사항 명세서

[PRD v0.2](./docs/PRD.md)에 기능 ID·우선순위·품질 요구사항·수용 기준을 정리했다. `active`는 적용할 요구사항, `local_demo`는 로컬 보조 검증 범위이며 구현 완료를 뜻하지 않는다.

| 영역 | 핵심 기준 |
|---|---|
| 날씨·취향 | 초기 날씨 선택은 ON이며 지역 미설정은 OFF로 처리한다. ON의 조회 장애를 임의로 OFF로 바꾸지 않는다. 테마·장르는 복수 선택하고 미선택·전체 선택을 같은 유효 조건으로 해석한다. |
| 기본 추천 | 판정 근거·버전이 있는 일반곡(GENERAL)만 사용하고 시즌·행사곡과 미판정 곡은 제외·보류한다. 중복 없이 목표 180분·허용 176~184분을 충족한다. |
| 날씨 갱신 | ON의 분류 변경에만 규칙 추천으로 새 결과를 만든다. 기존 조건·제외를 유지하며 이전 평가·승인을 복사하지 않고 오래된 응답의 덮어쓰기를 막는다. |
| 조정·평가·승인 | 제외 저장과 재설정 요청을 구분한다. 명시 재설정에만 Gemini를 사용하고 신규 곡·필수 조건을 검증한다. 평가는 선택 사항이며 자동 추천·제외·승인을 실행하지 않는다. 실패하면 기존 결과와 상태를 보존한다. |
| 관리자 | 공통 로그인 후 업무 권한에 맞는 메뉴로 진입하며 음악·피드백·광고 권한을 서버에서 검사한다. |
| 광고 | 통계와 예산 검증은 5분 주기다. 소진 확인 시각부터 신규 제공·기존 표시 자격을 차단하며, 확인 전의 유효 발생은 300초 이내 지연 보고를 인정한다. 실제 잔액은 차감하지 않는다. |

현행 입력·광고 기준은 [통합 정합성 기록](https://github.com/encore-ai-campus/mlo-01-p3-team1/blob/183ea87c7fb6f9878da51e51eb5c6408699374ee/docs/development/통합_정합성_수정_변경_라우팅.md)과 [광고 정책의 확정 절](https://github.com/encore-ai-campus/mlo-01-p3-team1/blob/183ea87c7fb6f9878da51e51eb5c6408699374ee/docs/development/ads/광고_미정_정책_결정_가이드.md)을 확인한다. 보존된 초기 계약·비교 초안을 현행 규정으로 그대로 적용하지 않는다.

## 6. ERD

### 음악 관계형 데이터 구조

음악 속성을 저장하는 4개 테이블의 컬럼·자료형·키·주요 제약을 표시했다. 참조 기준은 [음악 ORM](https://github.com/encore-ai-campus/mlo-01-p3-team1/blob/183ea87c7fb6f9878da51e51eb5c6408699374ee/backend/music/models.py)이며, 자료형은 PostgreSQL 기준으로 표기했다. 업무·피드백·영상 매핑·적재 운영 테이블은 별도다.

```mermaid
erDiagram
    music_album ||--o{ music_track : album_key
    music_track ||--o{ track_tag : track_id
    music_tag ||--o{ track_tag : tag_id

    music_album {
        bigint album_key PK "자동 증가 내부 키"
        text album_id UK "NULL 허용"
        text album_name "필수"
        text album_release_date "NULL 허용·원래 날짜 정밀도 유지"
    }
    music_track {
        text track_id PK "Spotify 곡 ID"
        text track_name "필수"
        text artists_name "필수·세미콜론 구분"
        text artists_id "NULL 허용·이름과 순서 대응"
        bigint album_key FK "필수·music_album 참조"
        integer duration_ms "필수·0 이상"
        boolean explicit "필수"
        smallint energy "NULL 허용·0~10"
        boolean mode "NULL 허용"
        smallint acousticness "NULL 허용·0~100"
        text raw_energy "NULL 허용·원본 정밀값"
        text raw_acousticness "NULL 허용·원본 정밀값"
        text raw_valence "NULL 허용·원본 정밀값"
        text speed "NULL 허용·slow/medium/fast/fastest"
        boolean instrumental "NULL 허용·최종 연주곡 판정"
        boolean instrumental_review_value "NULL 허용·확정 검수값"
        text play_url "필수·Spotify 곡 페이지"
    }
    music_tag {
        bigint tag_id PK "자동 증가 내부 키"
        text tag_type "genre/mood/instrument"
        text tag_code "tag_type과 함께 UNIQUE"
        text tag_name "필수"
        boolean is_active "필수·기본 false"
    }
    track_tag {
        text track_id PK, FK "복합 PK·music_track 참조"
        bigint tag_id PK, FK "복합 PK·music_tag 참조"
        text review_status "draft/approved·기본 draft"
    }
```

| 테이블 | 기본 키 | 역할 |
|---|---|---|
| music_album | album_key | 앨범 정보 |
| music_track | track_id | 곡·아티스트·음악 특성값과 앨범 참조 |
| music_tag | tag_id | 장르·분위기·악기 공통 사전 |
| track_tag | track_id + tag_id | 곡과 태그의 복수 연결·승인 상태 |

- PK는 기본 키, FK는 외래 키, UK는 고유 키다. 별도로 NULL 허용을 표시하지 않은 컬럼은 필수다.
- `music_tag`는 `(tag_type, tag_code)` 조합을 고유하게 관리하고, `track_tag`는 `(track_id, tag_id)`를 복합 기본 키로 사용한다.
- `genre`·`mood`·`main_inst`는 곡 테이블에 중복 저장하지 않고 태그 연결을 집계해 조회한다. `MusicImportRun`은 별도의 적재 체크포인트 모델이며 위 음악 속성 4개 테이블에 포함하지 않는다.

테이블 분리와 컬럼 의미는 [음악 테이블 설계](https://github.com/encore-ai-campus/mlo-01-p3-team1/blob/183ea87c7fb6f9878da51e51eb5c6408699374ee/docs/handoff/music/테이블_구조_설계.md)를 함께 참고한다.

## 7. 주요 프로시저

| 순서 | 주요 절차 | 작업내용 |
|---|---|---|
| 1 | 날씨 수집·정제·조회 | PostgreSQL 매핑으로 지역·격자를 연결하고 Kafka·Spark를 거쳐 Elasticsearch 최신 자료·공통 특징에 반영. 원천 응답 파일은 보관하지 않음 |
| 2 | 음악 정제·검수·발행 | CSV 변환·중복/오류 처리, 분류·검수·승인 후 버전이 고정된 추천 카탈로그 준비 |
| 3 | 기본 추천 | GENERAL 후보와 조건·카탈로그를 고정하고 날씨 ON/OFF별 점수·시간 조합 후 결과 저장. 지역 미설정은 OFF, ON은 유효 날씨 검증 |
| 4 | 날씨 분류 갱신 | ON의 분류 변경과 갱신 가능 상태를 확인해 같은 조건·제외로 규칙 추천. 같은 분류·OFF는 유지하고 실패·오래된 응답에서 기존 결과 보존 |
| 5 | 제외·재설정·승인 | 전체 제외 초안을 저장하고 명시 요청에만 같은 조건으로 재설정. 신규 곡·시간·필수 조건 검증 후 새 결과를 저장하고 별도 승인 |
| 6 | 피드백 기록·집계 | 평가·제외·취소·재설정·승인의 당시 조건과 결과 버전을 저장하고 이벤트를 정제·집계 |
| 7 | 광고 관리·제공 | 관리자 인증 후 등록·수정·중단·미리보기, 게시 자격과 위치에 따른 공개 제공 |
| 8 | 광고 측정·통계 | 유효 노출·클릭을 판정해 예상 원장에 기록하고 5분 주기로 통계·예산 검증. 소진 확인 이후 제공·표시 차단과 지연 보고 경계를 구분 |

### 기술별 입력·처리·출력(IN/OUT)

| 기술·구간 | 입력(IN) | 주요 처리 | 출력(OUT) |
|---|---|---|---|
| React | 사용자 선택·조작, API 응답 | 화면 상태·입력·반응형·안내 관리 | API 요청, 날씨·선곡표·관리 화면 |
| Django·DRF | 지역·취향·제외·평가·관리 요청 | 타입·소유·권한·버전 검사, 작업 등록·상태 저장 | 작업 ID·상태·결과·오류 응답 |
| 음악 RDB·카탈로그 | 정제 곡·앨범·태그·검수값 | 키·승인·GENERAL 판정·곡당 한 행 검증과 버전 고정 | 적격 음악 조회 자료·catalog_version |
| 추천 작업자 | 적격 일반곡·날씨 모드·취향·정책 | 모드별 필터·점수와 CP-SAT/정수 subset-sum 시간 조합 | 서버 검증을 거친 기본 선곡표 또는 실패 상태 |
| Gemini 어댑터 | 같은 적격 후보·시작 조건·저장된 제외 목록 | 명시 재설정 요청과 응답 해석 | 서버에서 신규 곡·시간·필수 조건을 검사할 재설정 후보 |
| Kafka | 날씨·업무 이벤트 | 영역별 전달·소비 | Spark 처리용 이벤트 |
| Spark | 날씨·피드백 이벤트 | 정규화·정제·집계·중복/역순 처리 | Elasticsearch 최신 자료·공통 특징, PostgreSQL 피드백 원본·정제·집계 |
| MongoDB | 광고·이미지·관리 변경·측정 자료 | 광고 영역 트랜잭션·판정·집계 | 광고 제공·통계 자료, PostgreSQL로 전달할 관리 로그 |
| Elasticsearch | 정규화 날씨·공통 특징 | 격자별 최신 상태 저장·조회·만료 검사 | 지역·대상시각별 날씨·상태·추천 입력 |
| PostgreSQL | 업무 상태·이벤트·당시 자료·정제/집계·로그 사본 | 원자 저장·중복 방지·조회·재처리 이력 관리 | 본인 결과·피드백·관리 조회·진단 자료 |
| 로컬 파일·S3 | 음악 원본, 설치 artifact·체크포인트 | 원본 근거·버전·해시 보관. 음악 원본의 운영 S3 보관은 보류 | 추적·재처리·복구용 자료 |

### 폴더 구조

```text
.
├─ README.md
├─ AGENTS.md
├─ CONTRIBUTING.md
└─ docs/
   ├─ BRD.md                   사업 요구사항 초안
   ├─ PRD.md                   제품 요구사항 초안
   ├─ product/                 기능·추천·계약·구현 태스크
   │  └─ archive/              이전 정책 이력
   ├─ contracts/               기계 판독 계약
   ├─ fixtures/                문서 단계의 고정 예시
   ├─ handoff/
   │  ├─ ads/                  광고 인계
   │  ├─ infra/                로컬·AWS 인프라 인계
   │  ├─ music/                음악 규격·테이블·선곡 규칙
   │  └─ weather/              날씨 수집·정제·저장 인계
   └─ assets/
      ├─ mockups/              화면 시안
      └─ penguin/              공통 펭귄 원본
```

위 구조는 로컬 문서 작업본이다. BRD·PRD가 참조한 구현 커밋에는 다음 경로가 있다.

```text
frontend/          공개·관리 화면
backend/           공통·음악·추천·날씨 API와 작업자
ad-server/         광고 API·MongoDB·집계 작업자
pipeline/          날씨·음악·피드백 처리
music_playback/    일반곡 판정·선곡표 구성 보조
deployment/aws/   AWS 앱 배포 설정
docs/development/ 구현·변경 기록
docs/acceptance/  검증 결과와 증빙
```

**전체 구조와 실행·인계 절차는 [참조 구현 트리](https://github.com/encore-ai-campus/mlo-01-p3-team1/tree/183ea87c7fb6f9878da51e51eb5c6408699374ee)와 그 안의 `docs/runbook/`을 확인한다. 위 코드 경로가 현재 로컬 문서 폴더에 모두 존재한다는 뜻은 아니다.*

## 8. 수행결과(테스트/시연 페이지)

### 기록으로 확인한 범위

- 다음은 BRD·PRD와 구현·배포 기록에 남은 결과를 요약한 것이다. 이번 README 검수에서 서비스 시험을 새로 실행한 결과는 아니다.

| 영역 | 확인 기록 | 검증 범위 |
|---|---|---|
| 음악·기본 추천 | 정상 곡 89,740건 적재·사용자 확인에 따른 승인·카탈로그 발행, AWS 기본 추천 3개 조건 성공 | 최신 일반곡 정책과 배포 버전 일치, 전체 조건별 성공률·품질은 별도 확인 |
| 날씨·운영 | AWS 수집→Kafka→Spark→Elasticsearch와 실제 지역 조회·접속 기록 | 전 지역 가용성·운영 집계·부하·장애 전환·복구 전체를 확인한 결과는 아님 |
| Gemini | 실제 생성 요청의 503 응답과 기존 결과 보존 기록 | 실제 생성 성공·지연·품질·비용은 추가 검증 대상 |
| YouTube | 외부 링크·보조 iframe·공통 관리자 검수 연결과 일부 자연 전환의 로컬 기록 | 운영 배포·전곡 연결·3시간 완주와 구분. 영상 검수는 로컬 시험 모드의 음악 권한으로 제한 |
| 사용자 효과 | 준비 시간·부담·만족도·ON/OFF 비교 등의 평가 방법 제시 | BRD의 측정 제안과 실제 합의·수행한 평가를 구분 |

**89,741개는 최초 원본의 고유 ID 수이며, 89,740개는 필수 이름 누락 1곡을 격리한 정상 곡 수다. 과거 발행 수치를 최신 GENERAL 적격곡 수로 사용하지 않는다.*

근거: [BRD의 현재 확인 상태](./docs/BRD.md), [AWS 적재·발행·추천 기록](https://github.com/encore-ai-campus/mlo-01-p3-team1/blob/183ea87c7fb6f9878da51e51eb5c6408699374ee/docs/development/INF_AWS_앱배포_변경_라우팅.md), [통합 검증 기록](https://github.com/encore-ai-campus/mlo-01-p3-team1/blob/183ea87c7fb6f9878da51e51eb5c6408699374ee/docs/development/통합_정합성_수정_변경_라우팅.md).

### 테스트와 평가 기준

- [PRD](./docs/PRD.md)의 수용 기준으로 ON/OFF, 일반곡·시간·제외·중복, 날씨 분류 갱신, 재설정 실패 보존, 권한·평가·집계, 광고 소진·지연 보고 경계를 확인한다. 코드 시험·실제 API/DB·브라우저·운영 복구의 증빙은 구분한다.

- 로컬 CSV 프리뷰는 클릭부터 곡 목록 표시까지 **P95 2.5초 이하를 목표**로 한다. 목표를 실측 달성값으로 표현하지 않으며, 운영·Gemini·동시 요청·복구 성능은 해당 환경의 합의 기준과 결과를 확인한다. 일부 조합 계산 속도로 전체 요청 응답 시간을 대신하지 않는다.

### 서비스 접속·시연 화면


<img src="./docs/assets/screenshots/02-guide-weather.png" alt="사용 안내 1단계 — 지역과 날씨" width="526">

<img src="./docs/assets/screenshots/03-guide-preferences.png" alt="사용 안내 2단계 — 음악 취향 선택" width="526">

<img src="./docs/assets/screenshots/04-guide-playlist.png" alt="사용 안내 3단계 — 선곡표 확인과 승인" width="526">

<img src="./docs/assets/screenshots/05-playlist-result.png" alt="선곡표 결과와 YouTube 외부 연결 화면" width="526">

## 9. 한 줄 회고

| 담당 | 한 줄 회고 |
|---|---|
| 안길찬 | 작성 대기 |
| 김건우 | 작성 대기 |
| 김민서 | 작성 대기 |
| 오재석 | 작성 대기 |
| 이인건 | 작성 대기 |

## 10. PPT 링크

발표 자료 링크 등록 대기.

