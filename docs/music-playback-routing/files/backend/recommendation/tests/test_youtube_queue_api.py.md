# backend/recommendation/tests/test_youtube_queue_api.py 라우팅

- 작성일/수정일: 2026-10-16
- 담당: 키 없는 음악 통합팀 / 외부 YouTube 큐
- 기준 브랜치/커밋: feature/ad-logic / f22f974
- 소스: `backend/recommendation/tests/test_youtube_queue_api.py`
- 통합 근거: docs/development/YouTube_키없는_등록과_검수_변경_라우팅.md

## 기준 → 회귀 검증

TransactionTestCase 5건이 메모리 Django DB의 합성 선곡표를 생성하고 registry 조회를 통제하여 GET /api/playlists/{playlist_id}/youtube-queue와 native_queue를 검증합니다. 실제 YouTube 접근·계정 API·음원·LLM은 호출하지 않습니다.

전체 원래 순서와 iframe BLOCKED/native_verified=true의 독립 사용, account_saved=false와 공식 임시 큐 URL·불변 snapshot/outbox, 중복 ID/미등록의 부분 결과·is_complete=false, iframe VERIFIED만으로 native 승인 대체 금지, 다른 소유자/제외 미반영의 registry 조회 전 차단, 운영의 로컬 fallback 금지를 확인합니다. 합성 ID와 metadata source는 실제 재생/청취나 47곡 완료의 증거가 아닙니다.

## AST 시그니처

검사기 `.local-preview-logs/keyless-routing-audit.json`의 python_files[].symbols를 기록합니다.

```python
class YoutubeQueueApiTests(TransactionTestCase)
YoutubeQueueApiTests.setUp(self)
YoutubeQueueApiTests.test_owned_native_queue_preserves_order_and_result_without_search_or_account_write(self)
YoutubeQueueApiTests.test_partial_queue_does_not_silently_deduplicate_or_claim_complete(self)
YoutubeQueueApiTests.test_pending_native_review_does_not_use_iframe_verification_as_substitute(self)
YoutubeQueueApiTests.test_foreign_owner_and_unapplied_exclusions_never_read_mapping_registry(self)
YoutubeQueueApiTests.test_unconfigured_production_has_no_local_registry_fallback(self)
```
