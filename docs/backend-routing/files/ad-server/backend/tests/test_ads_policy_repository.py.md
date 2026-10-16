# ad-server/backend/tests/test_ads_policy_repository.py

- 작성일: 2026-10-15
- 수정일: 2026-10-16
- [원본 코드](../../../../../../ad-server/backend/tests/test_ads_policy_repository.py)

driver/session 대역으로 정책 저장소의 snapshot 상속·환경 범위·ESTIMATED 원장 그룹·버전/날짜별 상태 키·전체 최초 cutoff·revision CAS/중복 경합·집계 교체·BSON Int64/bool 구분·0/PENDING/coverage 요약을 검증합니다.

스키마 시험은 추가2컬렉션·strict 타입/양수 한도/고유키·dry-run 무연결·로컬 개발 경계·strict validator/index 적용을 확인합니다. 실제 DB 검증은 별도 통합 시험입니다.

연결 생성·primary·캐시·미설정 및 시험/운영 환경 전달 검사는 [공통 연결 시험](./test_ads_repository_configuration.py.md)으로 통합했습니다. 저장소별 트랜잭션·경합·집계·스키마 검증은 유지합니다.

## AST 시그니처

```python
class AdsPolicyRepositoryTests(SimpleTestCase)
AdsPolicyRepositoryTests.setUp(self)
AdsPolicyRepositoryTests.collection(self, name)
AdsPolicyRepositoryTests.state(self, revision=1)
AdsPolicyRepositoryTests.metric(self, **overrides)
AdsPolicyRepositoryTests.test_run_keeps_policy_subclass_and_one_session_for_both_writes(self)
AdsPolicyRepositoryTests.test_all_policy_ads_are_environment_scoped_without_status_filter(self)
AdsPolicyRepositoryTests.test_usage_groups_only_estimated_ledger_in_ad_environment(self)
AdsPolicyRepositoryTests.test_state_identity_scopes_version_day_and_environment_without_delimiter_collision(self)
AdsPolicyRepositoryTests.test_state_lookup_uses_scoped_hash_and_latest_verified_order(self)
AdsPolicyRepositoryTests.test_total_cutoff_returns_earliest_non_null_without_current_day_filter(self)
AdsPolicyRepositoryTests.test_state_cas_matches_previous_revision_and_does_not_upsert(self)
AdsPolicyRepositoryTests.test_first_state_duplicate_reopens_transaction_to_read_winner(self)
AdsPolicyRepositoryTests.test_budget_writes_require_transaction_correct_environment_identity_and_revision(self)
AdsPolicyRepositoryTests.test_metrics_replace_grouped_rows_idempotently_without_ledger_writes_or_deletes(self)
AdsPolicyRepositoryTests.test_metrics_allow_explicit_zero_and_reject_negative_boolean_duplicate_groups(self)
AdsPolicyRepositoryTests.test_bson_int64_counts_and_revisions_are_valid_without_accepting_booleans(self)
AdsPolicyRepositoryTests.test_empty_metrics_are_pending_instead_of_fabricating_zero(self)
AdsPolicyRepositoryTests.test_summary_reports_today_lifetime_kst_coverage_and_explicit_zero(self)
class AdsPolicySchemaTests(SimpleTestCase)
AdsPolicySchemaTests.test_manifest_limits_two_collections_strict_fields_positive_limits_and_unique_scopes(self)
AdsPolicySchemaTests.test_schema_dry_run_never_opens_database(self)
AdsPolicySchemaTests.test_apply_rejects_shared_host_or_non_dev_database_before_driver_creation(self)
AdsPolicySchemaTests.test_apply_uses_strict_error_validation_and_requires_ads_primary(self)
```
