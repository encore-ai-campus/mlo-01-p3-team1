# backend/cafe/settings.py 라우팅

- 작성일/수정일: 2026-10-16
- 담당: C 공개 대시보드·YouTube 재생 통합
- 범위: 기존 중앙 iframe 재생·LLM 없는 공식 검색·API 연결 후속
- 기준 브랜치/커밋: feature/ad-logic / f22f974
- 소스: [backend/cafe/settings.py](../../../../../backend/cafe/settings.py)

## 기준과 공급·소비

로컬 Django 통합 호스트의 프로세스 환경을 읽어 인증·DB·날씨·추천/작업자·명시 Gemini 재설정 설정을 공급합니다. 이번 변경은 키 없는 기본 재생과 선택 공식 검색 설정을 공급하며 .env의 실제 비밀값을 이 문서나 저장소에 복사하지 않습니다. 공개 대시보드가 키를 보내거나 비밀번호를 전달하지 않습니다.

`YOUTUBE_DATA_API_KEY`가 우선이며 비어 있으면 `YOUTUBE_API_KEY`를 읽습니다. 키는 서버 환경에서만 사용합니다. `YOUTUBE_SEARCH_TIMEOUT_SECONDS` 기본 8초, `YOUTUBE_SEARCH_PER_OWNER_MINUTE` 기본 6회, `YOUTUBE_SEARCH_DAILY_LIMIT` 기본 80회, `YOUTUBE_SEARCH_CACHE_SECONDS` 기본 21,600초를 검색 resolver가 소비합니다. 이 값은 로컬 실행 기본값이며 실제 vendor 할당량·운영 예산을 승인했다는 의미가 아닙니다.

## 이번 변경과 검증

YOUTUBE_PLAYBACK_MODE 기본값은 KEYLESS이며 KEYLESS/OPTIONAL_SEARCH 이외의 값은 기동 오류입니다. KEYLESS는 API 키가 이미 환경에 있어도 검색하지 않으며 별도 registry의 실제 iframe PLAYING 보고와 원곡 확인을 마친 VERIFIED만 사용합니다. 기존 snapshot VERIFIED도 자동 승격하지 않습니다. 운영 미연결/저장소 장애는 기술 상태로 멈추고 미연결/검수 대기/차단은 MAPPING_REQUIRED로 구분합니다.

OPTIONAL_SEARCH는 명시 선택 경로로 보존합니다. 이 분기에서만 새 공식 검색에 서버 API 키를 사용하며 키가 없으면 API_KEY_MISSING을 표시합니다. Gemini·LLM·계정 OAuth 연결과 별도입니다. 실제 API 키 등록·공식 검색 성공·Chrome/Premium 확인은 수용 기록의 실행 여부를 따릅니다.

기존 LOCAL_DEMO/SQLite와 운영 PostgreSQL·공유 소유자/이벤트 어댑터 경계를 유지합니다. 이번 검색 설정 추가는 새 migration이나 음악 카탈로그/선곡표 저장을 유발하지 않습니다.

보조 registry 기본 경로는 BASE_DIR/.local-preview-logs/youtube-mappings.sqlite3, 접근코드는 같은 폴더 youtube-review-access.json이며 각 module의 YOUTUBE_REGISTRY_PATH/YOUTUBE_REVIEW_ACCESS_FILE 설정 주입으로 격리 시험이 가능합니다. 두 실제 파일은 Git 제외이며 공유 운영 DB/ADMIN 완료가 아닙니다. [키 없는 통합 라우팅](../../../../development/YouTube_키없는_등록과_검수_변경_라우팅.md)을 따릅니다.

[대시보드 연결 가이드](../../../../development/music/YouTube_로컬_재생_기획과_구현_가이드.md)·[자동 검색 변경 라우팅](../../../../development/YouTube_자동검색_변경_라우팅.md)·[중앙 iframe 수용 기록](../../../../acceptance/대시보드_중앙_YouTube_iframe_검증_20261016.md)을 함께 확인합니다. 수령 원문과 기존 backend-routing은 수정하지 않습니다.

## AST 시그니처

검사 JSON의 python_files[].symbols를 정본으로 기록합니다.

검사기가 추출한 클래스·함수·메서드는 0개입니다. 모듈 수준 설정/URL 등록의 공급·소비 경계를 위에 기록했습니다.
