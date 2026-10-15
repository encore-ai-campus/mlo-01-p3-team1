# ad-server/backend/tests/test_ads_public_mongo_integration.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../../ad-server/backend/tests/test_ads_public_mongo_integration.py)

ADS_RUN_MONGO_TESTS=1에서만 실행되는 실제 MongoDB 통합 시험입니다. loopback·ads-rs primary를 검사하고 무작위 UUID의 ads_integration_*_dev DB에 관리/공개 strict validator와 인덱스를 적용합니다. 시험 전용 DB 경계를 확인한 뒤 자료를 준비/정리하며 공유/운영 DB를 사용하지 않습니다.

실제 원자 커서/배달 snapshot·최초 판정/claim/반복/예상 항목·동시 event ID/서로 다른 ID·발급 키 경합·예상 원장 실패 rollback·중단 전 발생 보고·중단 승리 후 stale 제공 차단·proof와 이미지/공개 정보 제한·validator를 검증합니다. fixture 정책은 운영값이 아닙니다.

공개 이벤트 relay의 실패 후 재시도·SENT와 원본 판정/최초 응답/예상 원장 불변도 실제 MongoDB validator 아래에서 검증합니다. PostgreSQL 역할의 sink는 대역입니다.

실제 PostgreSQL sink·브라우저 노출 조건·AWS 운영/복구는 이 시험에 포함하지 않습니다. 실행 결과는 공통 광고 검증 기록을 따르며 AST 목록 자체를 실행 통과로 간주하지 않습니다.

선택 split_deadlines=True의 새 배달과 표시 마감이 없는 기존 배달을 같은 strict manifest로 저장하고, 잘못된 표시 마감 거절과 자정 전 발생의 지연 보고를 실제 MongoDB에서 검증합니다. 이는 일일 경계 운영 결정이나 provider 활성화를 의미하지 않습니다.

## AST 시그니처

```python
class AdsPublicMongoIntegrationTests(SimpleTestCase)
AdsPublicMongoIntegrationTests.setUpClass(cls)
AdsPublicMongoIntegrationTests.setUp(self)
AdsPublicMongoIntegrationTests.create_ad(self, **overrides)
AdsPublicMongoIntegrationTests.provide(self, placement='top', **overrides)
AdsPublicMongoIntegrationTests.event_data(self, delivery, event_type='VIEWABLE_IMPRESSION', **overrides)
AdsPublicMongoIntegrationTests.record(self, delivery, data, **overrides)
AdsPublicMongoIntegrationTests.stop(self)
AdsPublicMongoIntegrationTests.public_state(self)
AdsPublicMongoIntegrationTests.concurrent(self, functions)
AdsPublicMongoIntegrationTests.test_real_delivery_atomically_stores_cursor_snapshot_and_explicit_policy(self)
AdsPublicMongoIntegrationTests.test_real_split_deadlines_keep_old_schema_compatible_and_accept_late_report(self)
AdsPublicMongoIntegrationTests.test_real_highest_priority_and_tie_rotation_are_separate_per_placement(self)
AdsPublicMongoIntegrationTests.test_real_counted_event_commits_claim_repeat_ledger_and_pending_log_together(self)
AdsPublicMongoIntegrationTests.test_real_bottom_impression_and_click_keep_distinct_claims_and_units(self)
AdsPublicMongoIntegrationTests.test_real_event_log_retry_preserves_measurement_and_original_response(self)
AdsPublicMongoIntegrationTests.test_real_replay_after_stop_and_expiry_preserves_first_response_and_all_state(self)
AdsPublicMongoIntegrationTests.test_real_concurrent_same_event_id_commits_one_event_and_one_usage(self)
AdsPublicMongoIntegrationTests.test_real_concurrent_distinct_ids_for_one_delivery_consume_one_type_only(self)
AdsPublicMongoIntegrationTests.test_real_parallel_deliveries_share_repeat_window_and_suppressed_claim_is_consumed(self)
AdsPublicMongoIntegrationTests.test_real_concurrent_request_key_replay_advances_rotation_once(self)
AdsPublicMongoIntegrationTests.test_real_ledger_failure_rolls_back_claim_window_event_and_ad_lock(self)
AdsPublicMongoIntegrationTests.test_real_delayed_event_before_stop_uses_historical_active_snapshot(self)
AdsPublicMongoIntegrationTests.test_real_stop_winning_after_candidate_read_retries_without_serving_stale_ad(self)
AdsPublicMongoIntegrationTests.test_real_image_requires_proof_and_does_not_expose_owner_or_internal_metadata(self)
AdsPublicMongoIntegrationTests.test_real_strict_validators_reject_boolean_revision_extras_and_nonestimated_ledger(self)
```
