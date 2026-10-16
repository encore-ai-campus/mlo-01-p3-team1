# ad-server/backend/tests/test_ads_mongo_integration.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../../ad-server/backend/tests/test_ads_mongo_integration.py)

실제 replica set의 독립 테스트 DB에서 3컬렉션 lifecycle·원본/멱등 재생·버전/no-op 경쟁·시각 경계·validator·트랜잭션 롤백·동시 동일 멱등키 요청을 검증합니다.

`ADS_RUN_MONGO_TESTS=1`일 때만 실행합니다. 테스트 URI/DB 경계를 확인하고 랜덤한 ads_integration_<32자리 hex>_dev DB를 생성·정리하며 공유/운영 DB에 사용하지 않습니다. 입력은 실제 MongoDB와 고정 fixture, 출력은 assertion 및 클래스 단위 skip/실패입니다. 공통 ADMIN·MongoDB 로그·공개 배너의 운영 검증을 대신하지 않습니다. 중첩 동시 작업 helper는 아래 AST 목록에 포함합니다.

현행 로그 구조와 이전 자료 보존은 [광고 로그 저장 계약](../../../../../development/ads/MongoDB_광고_로그_저장_계약.md)을 따릅니다.

## AST 시그니처

```python
_cleanup_test_database(mongo_client, database_name)
_image_bytes(color='red')
class AdsMongoIntegrationTests(SimpleTestCase)
AdsMongoIntegrationTests.setUpClass(cls)
AdsMongoIntegrationTests.setUp(self)
AdsMongoIntegrationTests.create_ad(self)
AdsMongoIntegrationTests.test_real_lifecycle_commits_three_collections_and_pending_audit(self)
AdsMongoIntegrationTests.test_upload_replay_and_replacement_preserve_original_bytes(self)
AdsMongoIntegrationTests.test_replay_returns_original_response_after_schedule_end(self)
AdsMongoIntegrationTests.test_stale_snapshot_noop_racing_update_preserves_committed_change(self)
AdsMongoIntegrationTests.test_changed_body_idempotency_and_stale_version_conflict(self)
AdsMongoIntegrationTests.test_noop_preserves_stored_version_and_updated_at(self)
AdsMongoIntegrationTests.test_database_filters_match_schedule_boundaries(self)
AdsMongoIntegrationTests.test_database_validator_rejects_unknown_targeting_field(self)
AdsMongoIntegrationTests.test_database_validator_rejects_boolean_priority(self)
AdsMongoIntegrationTests.test_callback_failure_rolls_back_ad_and_audit_together(self)
AdsMongoIntegrationTests.test_simultaneous_same_key_create_returns_one_committed_result(self)
```
