# 공통 관리자와 YouTube 검수 통합·자료 인계 변경 라우팅

- 작성일: 2026-10-19
- 수정일: 2026-10-19
- 담당/범위: B 통합 조율, I-05·M-06·U-01 / 사용자 요청의 광고·음악·피드백·YouTube 검수 관리 연결과 자료 패키지
- 기준: `feature/ad-logic@cc11dec` / 동일 트리의 `develop@3bda1d3`. 2026-10-19 사용자가 이번 통합 변경22개 파일의 커밋·푸시와 CI 성공 후 develop 병합을 명시했습니다. 게시 전 최신 develop 이력을 merge로 연결하고 실제 게시/CI/병합 결과는 해당 GitHub PR 기록으로 확인합니다.

## 기준 → 실제 연결

기능/사용자 흐름·구현 설계도·추천 가이드·구현 태스크의 공통 ADMIN/음악 권한과 로컬 영상 검수 예외를 대조했습니다. 2026-10-19 사용자는 URL 후보·재생 검수까지 공통 관리자에 포함하도록 선택했습니다. 음악18개/추천식·시간·불변 결과·광고 정책·수령 원문은 유지합니다.

기존 React `/admin/ads`, `/admin/music`, `/admin/feedback/exclusions`는 서버의 `allowed_menus`와 공통 로그인으로 이미 연결돼 있었습니다. 별도 광고 `/dev/ads`는 접근 코드·시험 MongoDB를 쓰는 개발 도구여서 데이터/인증을 공통 관리자와 합친 상태가 아니었습니다. YouTube 도구도 공개 결과 아래 별도 접근 코드를 사용했습니다.

이번에는 `/admin/music/youtube`를 음악 관리 권한(`common.manage_music`) 메뉴에 추가하고 기존 영상 등록/목록/CSV/검수 패널을 재사용합니다. 서버 `/api/admin/youtube-review/{status,tracks,mappings,import,verify,block,native-verify,native-block}`는 매 요청 활성 staff 세션과 음악 권한, 변경 요청 CSRF를 검사합니다. 별도 접근 코드를 요구하거나 관리자 응답에 그 파일 위치를 보내지 않습니다. 권한만 다른 계정은 광고/피드백 또는 임의 익명 결과에 접근하지 못합니다.

## 변경 파일과 동작

| 실제 코드 | 변경 전후·저장/호출 |
|---|---|
| `backend/common/api.py:account_data_for_user/account_data/Login` | 허용 메뉴4개를 실제 권한으로 산출. 광고 권한이 있으면 기존 광고 진입, 음악만 있으면 음악 진입. 권한 없는 계정 로그인403. 프런트도 응답의 허용 경로와 고정 내부 경로를 대조 |
| `backend/common/youtube_review.py` | ADMIN 세션 어댑터. 기존 `youtube_review_api`의 검증/원자 저장을 재사용. 현재 GENERAL 카탈로그만 사용하고 `playlist_id` 입력을 거절해 사용자 결과 범위와 분리 |
| `backend/cafe/urls.py` | 공통 관리자용8경로 추가. 기존 로컬 코드 API와 공개 재생 API 유지 |
| `frontend/src/features/admin/YoutubeAdmin.tsx`, `main.tsx` | 공통 메뉴·로그아웃·권한 확인 후 재사용 검수 패널 표시 |
| `YoutubeReviewPanel.tsx`, `youtubeReview.ts` | ADMIN 모드에서는 공통 API/CSRF·세션을 사용하고 `playlist_id`와 로컬 접근 코드 입력/잠금 버튼을 보내지 않음. 기존 공개 결과 로컬 검수 모드는 유지 |
| `backend/common/test_youtube_admin.py`, `tests.py` | 공통 세션/권한/회수·CSRF·충돌/전체 거절·독립 승인·운영503 회귀. 기존 메뉴 수 기대값4로 조정 |

읽기/쓰기: ADMIN 세션→권한→LOCAL_DEMO/범위 검사→동일 GENERAL track_id→기존 곡 revision/CSV 전체 검증→별도 SQLite의 mapping/track_revision/review_audit 원자 저장→같은 DB를 조회하는 공개 native queue. 신규 등록은 CANDIDATE이며 외부 승인과 iframe 승인은 계속 독립입니다. 추천 카탈로그/과거 결과에 승인 상태를 복사하지 않습니다.

## 실행·광고 연결과 한계

공통 로그인은 공통 서버의 계정·세션을 사용합니다. 기존 `bootstrap_admin`은 새 계정에 `manage_ads manage_music view_feedback` 권한을 명시해 발급하며 비밀번호는 각 PC에서 별도 준비합니다. `ADMIN_SESSION_SECONDS`는 실행자가 명시합니다. 자료 패키지에 계정/비밀번호·접근 코드·.env·쿠키는 넣지 않습니다.

Vite는 광고 `/api/admin/ads`·`ad-assets`를 광고 서버(기본8000), 로그인/음악/피드백/새 YouTube API를 공통 서버(기본8001)로 전달합니다. 별도 광고 서버는 `ADS_COMMON_API_URL`과 양쪽 동일한 `ADS_INTERNAL_SECRET`으로 기존 브리지를 사용하고 브라우저 세션 Cookie를 공통 서버에 검증합니다. 이 값은 각 PC에서 발급/설정합니다. 광고 데이터는 광고 MongoDB이며 YouTube SQLite와 다릅니다. `/dev/ads`의 sandbox 계정/쿠키를 공통 관리자에 재사용하지 않습니다. 실제 별도 광고 MongoDB와 실행 설정 연결은 환경별 확인 대상입니다.

현재 YouTube 저장소는 로컬 SQLite이므로 공통 ADMIN으로 들어가더라도 LOCAL_DEMO에서만 열립니다. 운영 모드는 status.enabled=false, 목록/변경503입니다. 공유 ADMIN 인증 어댑터 연결을 운영 저장소·다중 PC 동시 검수 완료로 보고하지 않습니다. 공개 결과의 과거 소유 검사·기존 운영자 코드 도구는 그대로입니다.

## 전달과 검증

전달 패키지는 SQLite backup API 스냅샷, 원래306개 수집 자료, 음악 CSV/분류 manifest·판정 CSV, 상한 초과660개 기록, 공유 검수 근거, 이번 코드 패치, SHA256 목록과 복원 가이드를 포함합니다. 기존 사용자/추천 결과 DB·환경/인증 비밀은 포함하지 않습니다. 새 PC의 비어 있는 검수 DB에 복원하며 이미 작업한 DB와 자동 병합하지 않습니다.

실제 실행: 공통/기존 YouTube API **49개 통과**, 백엔드 공통·음악·추천·날씨 전체 **240개 통과**, 프런트 Vitest **52개 통과**, TypeScript·Vite 빌드·마이그레이션 변경 없음 검사 통과입니다. 라우팅 검사는 광고87파일/908심볼·통합22파일/200심볼 문제0건입니다. DB 복원/전달 검증은 패키지의 검증 보고서에서 확인합니다. 원곡/전곡 완주·물리 음향·운영 광고 MongoDB 수용은 이번 시험에 포함하지 않습니다. 소스 AST와 1:1 문서는 [통합 색인](../integration-routing/README.md)으로 연결합니다.

게시 범위는 위 통합 코드·시험·라우팅·제품 문서22개입니다. 전달용 ZIP·그 내부 패치·SHA256 목록·로컬 DB·접근 코드·.env·수집 원본은 Git 제외 상태와 원래 바이트를 유지합니다. 전달 ZIP은 통합 전 기준 코드에 적용하는 과거 스냅샷입니다. 이번 변경이 반영된 develop을 받은 PC는 ZIP의 코드 패치를 중복 적용하지 않고, 해시 확인→자료 복원→새 로컬 공통 DB/카탈로그·본인 계정 준비 순서를 따릅니다. 기존 검수 DB와 자동 병합하지 않습니다.
