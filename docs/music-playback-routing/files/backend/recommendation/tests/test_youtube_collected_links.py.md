# backend/recommendation/tests/test_youtube_collected_links.py 라우팅

## 2026-10-19 수집 URL 공개 연결 — 현행

- 담당: Codex root / U-01·M-06·Q-02 연결 수정
- 브랜치/기준: feature/youtube-url-connection / develop a7dfafb
- 작성/수정: 2026-10-19. 기존 수령 원문은 보존합니다. 아래 앞 단계 서술은 당시 구현 이력이며 이번 절이 현행입니다.
- 계약·전체 검증: [수집 URL 연결 변경 라우팅](../../../../../development/수집_URL_공개화면_연결_변경_라우팅.md).

Django 공유 DB 어댑터의 실제 테이블에서 미검수 후보 큐/링크 포함·승인 및 감사 보존·native 우선·iframe 차단 독립·native 철회·중복 영상 대안·두 SELECT 조회·1201개 ID의 500개 단위 분할을 검증합니다. SQLite의 공유 어댑터 시험은 통과했고 PostgreSQL은 application-tests.yml의 postgres-regressions 대상에 추가했습니다. 테스트 성공을 운영 DB 적용으로 기록하지 않습니다.

### AST 시그니처 — 검사 결과

```python
class CollectedYoutubeLinksTests(TestCase)
CollectedYoutubeLinksTests.setUp(self)
CollectedYoutubeLinksTests.test_candidates_in_queue_and_links_without_promoting_reviews_or_changing_tracks(self)
CollectedYoutubeLinksTests.test_native_approval_preferred_but_iframe_block_and_native_block_stay_independent(self)
CollectedYoutubeLinksTests.test_duplicate_approved_video_falls_back_to_another_collected_candidate(self)
CollectedYoutubeLinksTests.test_batch_read_limits_queries_to_requested_tracks_and_handles_unknown_and_duplicate_ids(self)
CollectedYoutubeLinksTests.test_more_than_sqlite_parameter_limit_uses_bounded_batches(self)
```
