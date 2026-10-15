# backend/tests/test_ads_log_relay.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../backend/tests/test_ads_log_relay.py)

메모리 claim collection과 sink 대역으로 로그 전달을 검증합니다. 미설정 sink의 선차단·불변 감사/응답/payload·명시적인 True ack·실패 재시도·단일 claim/만료 재획득·늦은 ack 배제·commit 후 ack 실패의 동일 ID 재전달·test 범위·한 batch 명령을 확인합니다.

입력은 고정 clock, PENDING 레코드, sink 동작이며 출력은 assertion 결과입니다. 공통 PostgreSQL의 실제 멱등 저장/네트워크 장애 검증과 구분합니다. 중첩 sink/helper도 AST 시그니처 목록에 포함합니다.

## AST 시그니처

```python
_value(document, path)
_matches(document, query)
_set(document, path, value)
class MemoryCollection
MemoryCollection.__init__(self, document)
MemoryCollection.find_one_and_update(self, query, update, **kwargs)
MemoryCollection.update_one(self, query, update)
class AdsLogRelayTests(SimpleTestCase)
AdsLogRelayTests.setUp(self)
AdsLogRelayTests.worker(self, sink=lambda log_event_id, payload, payload_hash: True)
AdsLogRelayTests.test_missing_sink_blocks_before_repository_access(self)
AdsLogRelayTests.test_success_keeps_audit_response_and_payload_immutable(self)
AdsLogRelayTests.test_sink_exception_keeps_pending_and_only_exception_type(self)
AdsLogRelayTests.test_false_or_none_does_not_acknowledge_sink_success(self)
AdsLogRelayTests.test_only_one_worker_claims_unexpired_record(self)
AdsLogRelayTests.test_expired_claim_can_be_reclaimed_and_late_worker_cannot_ack(self)
AdsLogRelayTests.test_commit_before_ack_failure_redelivers_same_id_without_duplicate(self)
AdsLogRelayTests.test_test_mode_does_not_claim_production_record(self)
AdsLogRelayTests.test_command_reports_missing_sink_without_database(self)
AdsLogRelayTests.test_command_runs_bounded_batch_once(self)
```
