# backend/recommendation/tests/test_youtube_review_api.py 라우팅

- 작성일/수정일: 2026-10-16
- 담당: API 키 없는 YouTube 등록·검수 백엔드 / 통합팀
- 기준 브랜치/커밋: feature/ad-logic / f22f974
- 소스: `backend/recommendation/tests/test_youtube_review_api.py`
- 통합 근거: docs/development/YouTube_키없는_등록과_검수_변경_라우팅.md

## 기준 → HTTP·저장 회귀 검증

10개 TransactionTestCase가 시험 전용 URLconf·메모리 Django DB·workspace 임시 registry를 사용합니다. 두 곡 합성 일반 카탈로그와 익명 소유 문맥으로 실제 review Endpoint를 호출합니다.

공개 status의 secret 비노출과 보호 경로 코드 필수, URL 등록→검수→차단 및 summary/filter, 뒤 행 미존재/stale CSV의 전체 rollback·행 번호 오류, 허용되지 않은 status 필드 거절, 본인/타인 playlist 구분, 올바른 코드가 있어도 CSRF 필수, 운영 미연결 503을 확인합니다. 카탈로그 tracks와 추천 Job 수가 바뀌지 않는 것도 검증합니다.

native-verify가 iframe BLOCKED를 바꾸지 않으면서 전체 준비 집계에 포함되고 native-block으로 외부 승인만 철회하는 왕복도 확인합니다. 최신 일반 카탈로그에서 빠진 과거 본인 선곡표의 곡도 playlist_id·소유 검사를 통과한 경우 등록할 수 있고, 타인의 같은 요청은 404인 것을 추가 확인합니다. 닫히지 않은 CSV 헤더/행의 따옴표는 각각 CSV_HEADERS_INVALID/CSV_ROW_INVALID로 전체 거절하며 저장하지 않습니다.

2026-10-16 registry 16건과 이 API 10건을 포함한 백엔드 전체 136건이 통합 담당 실행에서 통과했습니다. 이 시험은 실제 공유 ADMIN·운영 DB·YouTube 삽입·사용자 Chrome/Premium 완료의 근거가 아닙니다.

## AST 시그니처

검사기 `.local-preview-logs/keyless-routing-audit.json`의 python_files[].symbols를 그대로 기록합니다.

```python
class YoutubeReviewApiTests(TransactionTestCase)
YoutubeReviewApiTests.setUp(self)
YoutubeReviewApiTests.post(self, suffix, body, headers=None, client=None)
YoutubeReviewApiTests.test_status_has_no_secret_and_all_review_routes_require_local_code(self)
YoutubeReviewApiTests.test_registration_verification_block_and_filtered_review_queue(self)
YoutubeReviewApiTests.test_unknown_track_in_later_csv_row_prevents_all_writes(self)
YoutubeReviewApiTests.test_csv_duplicate_stale_and_unsupported_fields_are_rejected(self)
YoutubeReviewApiTests.test_owned_playlist_scope_does_not_expose_foreign_results(self)
YoutubeReviewApiTests.test_csrf_required_with_valid_review_code(self)
YoutubeReviewApiTests.test_production_disabled_and_rejects_even_valid_local_code(self)
YoutubeReviewApiTests.test_native_review_keeps_iframe_blocked_but_counts_as_playback_ready(self)
YoutubeReviewApiTests.test_owned_historical_track_registration_survives_catalog_replacement(self)
YoutubeReviewApiTests.test_unclosed_csv_quote_rejects_entire_import(self)
```
