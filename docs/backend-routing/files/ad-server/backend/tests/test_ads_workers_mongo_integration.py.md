# ad-server/backend/tests/test_ads_workers_mongo_integration.py

- 작성일: 2026-10-15
- 수정일: 2026-10-16
- [원본 코드](../../../../../../ad-server/backend/tests/test_ads_workers_mongo_integration.py)

별도 전용 로컬 replica set의 격리 UUID 개발 DB에서 읽기 점검·이전 로그 보존·무결성/인덱스 차이·보관 조회의 원본/이미지/인덱스 불변을 검증합니다. 연결 실패 후 작업자를 중단/정상 저장소로 재시작하여 집계 중복과 로그 변경이 없음을 확인합니다. 실제 공유 인증·장기 주기 관측·운영 복구는 별도입니다.

[실행/검증 범위](../../../../../runbook/광고_보관_점검과_배치_종료.md)

## AST 시그니처

```python
class AdsWorkersMongoIntegrationTests(SimpleTestCase)
AdsWorkersMongoIntegrationTests.setUpClass(cls)
AdsWorkersMongoIntegrationTests.setUp(self)
AdsWorkersMongoIntegrationTests.test_inspection_does_not_mutate_originals_claims_or_metrics(self)
AdsWorkersMongoIntegrationTests.test_real_unique_index_drift_is_reported_without_repair(self)
AdsWorkersMongoIntegrationTests.test_legacy_logs_remain_readable_and_unmodified_under_new_validator(self)
AdsWorkersMongoIntegrationTests.test_corrupted_log_is_reported_without_repair_or_business_changes(self)
AdsWorkersMongoIntegrationTests.test_retention_review_preserves_real_documents_indexes_and_binary_assets(self)
AdsWorkersMongoIntegrationTests.test_watch_connection_failure_then_restart_preserves_logs_and_avoids_duplicate_metrics(self)
```
