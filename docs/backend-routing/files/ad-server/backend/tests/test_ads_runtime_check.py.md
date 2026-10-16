# ad-server/backend/tests/test_ads_runtime_check.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../../ad-server/backend/tests/test_ads_runtime_check.py)

설정/DB 읽기 점검·validator/인덱스/TTL 차이·오류 비밀값 비노출과 실제 공유 인증 미검증 경계를 검사합니다.

현행 로그 구조와 이전 자료 보존은 [광고 로그 저장 계약](../../../../../development/ads/MongoDB_광고_로그_저장_계약.md)을 따릅니다.

## AST 시그니처

```python
schema_database()
class AdsRuntimeCheckTests(SimpleTestCase)
AdsRuntimeCheckTests.test_configuration_inspection_does_not_call_auth_or_sink_or_database(self)
AdsRuntimeCheckTests.test_missing_import_and_invalid_public_url_are_not_echoed(self)
AdsRuntimeCheckTests.test_expected_schema_passes_and_missing_collection_is_reported(self)
AdsRuntimeCheckTests.test_validator_weakening_unique_drift_and_unexpected_ttl_fail_checks(self)
AdsRuntimeCheckTests.test_database_exception_redacts_connection_details(self)
AdsRuntimeCheckTests.test_passing_local_checks_still_do_not_claim_shared_auth_or_postgres_commit(self)
AdsRuntimeCheckTests.test_command_without_database_flag_returns_unconfirmed_with_nonzero_semantics(self)
AdsRuntimeCheckTests.test_command_can_return_successful_bounded_report(self)
```
