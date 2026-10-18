# backend/cafe/urls.py 라우팅

- 작성일/수정일: 2026-10-16
- 담당: C 공개 대시보드·YouTube 재생 통합
- 범위: 기존 중앙 iframe 재생·LLM 없는 공식 검색·API 연결 후속
- 기준 브랜치/커밋: feature/ad-logic / f22f974
- 소스: [backend/cafe/urls.py](../../../../../backend/cafe/urls.py)

## 기준과 공급·소비

Django URLconf가 기존 추천·날씨·제외·평가·승인 Endpoint에 요청을 연결합니다. `POST /api/playlists/<str:pk>/youtube-playback` → `api.YoutubePlayback.as_view()`를 보조 iframe에 유지하고, 키 없는 운영자 등록·검수의 다음 8개 경로를 youtube_review_api에 연결합니다. 기본 외부 재생은 `GET /api/playlists/<str:pk>/youtube-queue` → youtube_queue_api.YoutubeQueue로 연결합니다.

| 경로 | 소비 클래스 |
|---|---|
| GET /api/youtube-review/status | ReviewStatus |
| GET /api/youtube-review/tracks | ReviewTracks |
| POST /api/youtube-review/mappings | ReviewMappings |
| POST /api/youtube-review/import | ReviewImport |
| POST /api/youtube-review/verify | ReviewVerify |
| POST /api/youtube-review/block | ReviewBlock |
| POST /api/youtube-review/native-verify | ReviewNativeVerify |
| POST /api/youtube-review/native-block | ReviewNativeBlock |

status를 제외한 검수 read/write는 로컬 운영자 접근코드를 요구하고 POST는 기존 CSRF를 유지합니다. 운영 ADMIN 어댑터 미연결은 503입니다. 음악18개/RDB정본·추천 전체 후보·기존 결과를 변경하지 않습니다. [키 없는 통합 라우팅](../../../../development/YouTube_키없는_등록과_검수_변경_라우팅.md)을 따릅니다.

## 이번 변경과 검증

공개 대시보드의 중앙 iframe 재생 제어가 본인 결과의 track_id와 실패한 video_id 제외 목록을 이 경로로 전송합니다. API는 CSRF → 익명 소유자/결과 소유 확인 → 엄격한 입력 → 결과 내 곡/제외 반영 확인 → KEYLESS 기본 registry resolver 순서로 처리합니다. OPTIONAL_SEARCH에서만 이전 공식 검색을 사용합니다. 음악 재추천·승인·곡 제외/평가 API와 분리하며 공개 재생 조회는 임의 외부 URL/비밀번호를 받지 않습니다. 영상 URL은 보호된 운영자 등록 API에만 보냅니다.

키 없는 기존 매핑, 미매핑 명시 상태, 다른 소유자/결과 밖 곡 차단, 제외 미반영 409, 잘못된 필드와 CSRF 차단은 신규 API 회귀로 확인합니다. 실제 iframe 재생과 자동 다음 곡 관찰은 별도 수용 기록입니다.

[대시보드 연결 가이드](../../../../development/music/YouTube_로컬_재생_기획과_구현_가이드.md)·[자동 검색 변경 라우팅](../../../../development/YouTube_자동검색_변경_라우팅.md)·[중앙 iframe 수용 기록](../../../../acceptance/대시보드_중앙_YouTube_iframe_검증_20261016.md)을 함께 확인합니다. 수령 원문과 기존 backend-routing은 수정하지 않습니다.

## AST 시그니처

검사 JSON의 python_files[].symbols를 정본으로 기록합니다.

검사기가 추출한 클래스·함수·메서드는 0개입니다. 모듈 수준 설정/URL 등록의 공급·소비 경계를 위에 기록했습니다.
