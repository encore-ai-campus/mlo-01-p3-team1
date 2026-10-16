# ad-server/backend/tests/test_ads_public_repository.py

- 작성일: 2026-10-15
- 수정일: 2026-10-16
- [원본 코드](../../../../../../ad-server/backend/tests/test_ads_public_repository.py)

driver/session 대역으로 공개 저장 어댑터의 트랜잭션 상속·환경 범위·후보 조건/정렬·revision CAS·고유키 재조회·반복 키·최초 claim·시각 $max·과거 snapshot 정렬·광고 잠금·재시도 라벨 보존을 검증합니다. 실제 DB 원자성은 별도 MongoDB 통합 시험입니다.

스키마 시험은 공개5컬렉션·TTL 없음·선택 발급 키 partial unique·명령 dry-run 무연결·공유 호스트 선차단·strict validator/index 옵션 전달을 확인합니다. 운영 DB 적용이나 미정 정책 확정이 아닙니다.

현행 로그 구조와 이전 자료 보존은 [광고 로그 저장 계약](../../../../../development/ads/MongoDB_광고_로그_저장_계약.md)을 따릅니다.

연결 생성·primary·캐시·미설정 및 시험/운영 환경 전달 검사는 [공통 연결 시험](./test_ads_repository_configuration.py.md)으로 통합했습니다. 저장소별 트랜잭션·경합·집계·스키마 검증은 유지합니다.

## AST 시그니처

```python
class PublicAdsRepositoryTests(SimpleTestCase)
PublicAdsRepositoryTests.setUp(self)
PublicAdsRepositoryTests.collection(self, name)
PublicAdsRepositoryTests.test_run_keeps_public_subclass_and_session_for_all_atomic_components(self)
PublicAdsRepositoryTests.test_candidates_exclude_stopped_wrong_scope_and_end_boundary_with_stable_order(self)
PublicAdsRepositoryTests.test_rotation_initial_insert_then_cas_increments_revision_and_scopes_environment(self)
PublicAdsRepositoryTests.test_state_insert_collision_reopens_transaction_and_sees_winner(self)
PublicAdsRepositoryTests.test_failed_state_cas_does_not_upsert_or_overwrite_winner(self)
PublicAdsRepositoryTests.test_repeat_identity_is_per_owner_ad_placement_type_and_environment(self)
PublicAdsRepositoryTests.test_repeat_state_initializes_at_one_and_compares_previous_revision(self)
PublicAdsRepositoryTests.test_unique_event_collision_replays_committed_result_after_new_transaction(self)
PublicAdsRepositoryTests.test_delivery_request_lookup_scopes_nullable_owner_placement_and_hash(self)
PublicAdsRepositoryTests.test_claim_only_first_type_conditional_and_preserves_other_claim(self)
PublicAdsRepositoryTests.test_claim_rejects_untrusted_field_path_and_unconsuming_decision(self)
PublicAdsRepositoryTests.test_touch_uses_max_to_keep_latest_receive_time(self)
PublicAdsRepositoryTests.test_reconfirmation_updates_usage_time_without_inventing_event_receive_time(self)
PublicAdsRepositoryTests.test_historical_lookup_uses_server_change_time_and_version_tiebreak(self)
PublicAdsRepositoryTests.test_ad_lock_restores_unchanged_ad_and_turns_cas_failure_into_retry(self)
PublicAdsRepositoryTests.test_public_writes_reject_nontransaction_or_wrong_environment(self)
PublicAdsRepositoryTests.test_driver_write_conflict_label_reaches_driver_callback_retry(self)
class PublicAdsSchemaTests(SimpleTestCase)
PublicAdsSchemaTests.test_manifest_adds_only_five_public_collections_without_ttl_or_extra_business_fields(self)
PublicAdsSchemaTests.test_delivery_optional_idempotency_key_has_partial_unique_index(self)
PublicAdsSchemaTests.test_schema_dry_run_does_not_open_database(self)
PublicAdsSchemaTests.test_apply_refuses_shared_host_before_driver_creation(self)
PublicAdsSchemaTests.test_apply_forwards_partial_unique_index_and_strict_validation(self)
```
