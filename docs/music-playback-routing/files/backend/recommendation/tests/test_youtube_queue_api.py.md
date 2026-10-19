# backend/recommendation/tests/test_youtube_queue_api.py 라우팅

## 2026-10-19 수집 URL 공개 연결 — 현행

- 담당: Codex root / U-01·M-06·Q-02 연결 수정
- 브랜치/기준: feature/youtube-url-connection / develop a7dfafb
- 작성/수정: 2026-10-19. 기존 수령 원문은 보존합니다. 아래 앞 단계 서술은 당시 구현 이력이며 이번 절이 현행입니다.
- 계약·전체 검증: [수집 URL 연결 변경 라우팅](../../../../../development/수집_URL_공개화면_연결_변경_라우팅.md).

HTTP 소유/제외 선검사와 운영 fail-closed를 유지하고 batch 조회 mock으로 갱신합니다. iframe 승인만 있는 영상도 미검수 외부 영상으로 큐에 포함하되 native 승인으로 표시하지 않는 회귀를 검증합니다. 공개 후보 포함·native 독립 판정·중복 대안·실제 공유 DB 읽기는 신규 test_youtube_collected_links에서 추가 검증합니다.

### AST 시그니처 — 검사 결과

```python
class YoutubeQueueApiTests(TransactionTestCase)
YoutubeQueueApiTests.setUp(self)
YoutubeQueueApiTests.test_owned_native_queue_preserves_order_and_result_without_search_or_account_write(self)
YoutubeQueueApiTests.test_partial_queue_does_not_silently_deduplicate_or_claim_complete(self)
YoutubeQueueApiTests.test_iframe_only_review_is_included_without_claiming_native_approval(self)
YoutubeQueueApiTests.test_foreign_owner_and_unapplied_exclusions_never_read_mapping_registry(self)
YoutubeQueueApiTests.test_unconfigured_production_has_no_local_registry_fallback(self)
```

## 앞 단계 기록

- 작성일: 2026-10-16
- 수정일: 2026-10-18
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

## 2026-10-18 develop 동기화 보완

합성 날씨 provider를 명시합니다. 순서·소유·추천/승인 불변과 외부 재생/iframe 승인 분리 검증은 유지합니다.

기준 develop `8bdad88`·기존 feature/ad-logic `0a0cc82`의 대조와 실제 재검증은 [통합 기록](../../../../../development/feature_전체_동기화_변경_라우팅_20261018.md)을 따릅니다.
