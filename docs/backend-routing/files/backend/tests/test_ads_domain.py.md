# backend/tests/test_ads_domain.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../backend/tests/test_ads_domain.py)

메모리 트랜잭션 대역을 사용해 서비스 동작을 검증합니다. 상태 경계·멱등 재생/경합·version/no-op·중단과 PUT·원본 보존·실패 시 롤백·미정 입력 거절·UTC 정규화·이미지 디코딩/해시·불변 PENDING payload를 확인합니다.

입력은 고정 clock/id·광고/이미지/actor fixture이며 출력은 assertion 결과입니다. 이 메모리 검증은 MongoDB driver/replica set의 실제 실행 근거와 구분합니다. AST 목록의 중첩 commit/fixture는 테스트 지원 코드입니다.

## AST 시그니처

```python
class MemoryRepository
MemoryRepository.__init__(self)
MemoryRepository.run(self, callback)
MemoryRepository.get_mutation(self, source, actor, operation, scope, key_hash)
MemoryRepository.get_asset(self, asset_id)
MemoryRepository.get_ad(self, ad_id)
MemoryRepository.insert_asset(self, document)
MemoryRepository.insert_ad(self, document)
MemoryRepository.insert_mutation(self, document)
MemoryRepository.replace_ad(self, ad_id, expected_version, document)
image_bytes(image_format='PNG')
class AdsDomainTests(SimpleTestCase)
AdsDomainTests.setUp(self)
AdsDomainTests.create(self)
AdsDomainTests.test_status_inclusive_start_exclusive_end_and_pause(self)
AdsDomainTests.test_create_replay_preserves_original_status_and_does_not_duplicate(self)
AdsDomainTests.test_idempotency_conflict_changes_nothing(self)
AdsDomainTests.test_update_replay_precedes_version_check_and_snapshot_is_immutable(self)
AdsDomainTests.test_noop_does_not_increment_version_or_updated_at(self)
AdsDomainTests.test_stop_and_put_preserve_paused_and_original_asset(self)
AdsDomainTests.test_upload_replay_uses_bytes_hash_and_actor_namespace(self)
AdsDomainTests.test_second_stop_is_noop_and_replay_uses_first_response(self)
AdsDomainTests.test_audit_failure_rolls_back_ad_and_asset(self)
AdsDomainTests.test_conditional_write_failure_rolls_back_and_records_no_success(self)
AdsDomainTests.test_unknown_tag_boolean_priority_and_invalid_duration_rejected(self)
AdsDomainTests.test_normalized_utc_inputs_hash_the_same(self)
AdsDomainTests.test_missing_asset_and_tampered_sha_are_not_accepted(self)
AdsDomainTests.test_image_limit_decode_and_animation_validation(self)
AdsDomainTests.test_log_payload_is_pending_immutable_and_has_no_image_or_auth_secret(self)
```
