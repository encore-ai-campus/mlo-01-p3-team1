# ad-server/backend/tests/test_ads_public_log_relay.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../../ad-server/backend/tests/test_ads_public_log_relay.py)

실제 공개 서비스가 만든 COUNTED 이벤트의 log_relay를 메모리 collection과 sink 대역에 연결합니다. 미연결 sink의 DB 접근 전 차단·ad_events/processed_at 연결·원본 판정/응답/예상 원장 불변·실패 PENDING/재시도·commit 후 ack 실패의 동일 ID 재전달·정렬 필드 제한·한 batch 명령을 검증합니다.

실제 PostgreSQL 저장/네트워크 시험은 아니며 fixture 정책을 사용합니다. 실제 MongoDB validator와 relay 상태 변경의 호환성은 test_ads_public_mongo_integration.py에서 별도로 검증합니다.

## AST 시그니처

```python
class AdsPublicLogRelayTests(SimpleTestCase)
AdsPublicLogRelayTests.setUp(self)
AdsPublicLogRelayTests.worker(self, sink)
AdsPublicLogRelayTests.test_missing_sink_blocks_before_any_ad_repository_access(self)
AdsPublicLogRelayTests.test_configured_event_relay_uses_public_collection_and_processing_order(self)
AdsPublicLogRelayTests.test_success_preserves_event_decision_response_payload_and_usage(self)
AdsPublicLogRelayTests.test_failed_sink_retains_pending_and_retry_uses_original_payload(self)
AdsPublicLogRelayTests.test_commit_before_ack_failure_redelivers_same_event_id_idempotently(self)
AdsPublicLogRelayTests.test_sort_field_accepts_only_management_or_event_timestamp(self)
AdsPublicLogRelayTests.test_command_reports_missing_sink_without_database_access(self)
AdsPublicLogRelayTests.test_command_runs_one_bounded_event_batch(self)
```
