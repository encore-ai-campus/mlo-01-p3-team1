# ad-server/backend/tests/test_ads_policy_mongo_integration.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../../ad-server/backend/tests/test_ads_policy_mongo_integration.py)

명시 ADS_RUN_MONGO_TESTS=1에서만 loopback ads-rs primary·무작위 UUID _dev DB에 관리/공개/정책 manifest를 적용하는 실제 MongoDB 시험입니다. 공유/운영 DB에는 연결하지 않습니다.

검증 전 초과 사용 후 예산 종료·정확 cutoff 제외/이전 발생 지연 인정·지표/상태/광고 rollback·증액 새 버전 검증/옛 cutoff 보존·측정/검증 경합 직렬화·실제0지표/첫 소진 로그 재시도·ENDED cursor의 기간/예산 종료 조건 보존을 검증합니다. 실제 PostgreSQL과 AWS 운영/복구는 별도이며 정책값은 시험용입니다.

## AST 시그니처

```python
class AdsPolicyMongoIntegrationTests(SimpleTestCase)
AdsPolicyMongoIntegrationTests.setUpClass(cls)
AdsPolicyMongoIntegrationTests.setUp(self)
AdsPolicyMongoIntegrationTests.provide(self, **extra)
AdsPolicyMongoIntegrationTests.event(self, delivery, kind='VIEWABLE_IMPRESSION', *, occurred_at=None, event_id=None)
AdsPolicyMongoIntegrationTests.state(self)
AdsPolicyMongoIntegrationTests.test_real_usage_can_exceed_limit_before_verification_then_ad_ends(self)
AdsPolicyMongoIntegrationTests.test_real_cutoff_excludes_boundary_but_accepts_earlier_delayed_excess(self)
AdsPolicyMongoIntegrationTests.test_real_batch_failure_rolls_back_metrics_state_and_ad_annotation(self)
AdsPolicyMongoIntegrationTests.test_real_budget_increase_revalidates_and_preserves_old_cutoff(self)
AdsPolicyMongoIntegrationTests.test_real_event_and_verification_race_is_serialized_without_lost_usage(self)
AdsPolicyMongoIntegrationTests.test_real_zero_metrics_and_budget_relay_retry_remain_distinct(self)
AdsPolicyMongoIntegrationTests.test_real_ended_cursor_keeps_budget_or_period_filter(self)
```
