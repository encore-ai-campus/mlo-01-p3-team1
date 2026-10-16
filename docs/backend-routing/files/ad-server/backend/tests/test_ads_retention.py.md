# ad-server/backend/tests/test_ads_retention.py

- 작성일: 2026-10-16
- 수정일: 2026-10-16
- [원본 코드](../../../../../../ad-server/backend/tests/test_ads_retention.py)

90/365일 경계·기산점·KST 다음 자정·무변경 미정·잘못된/미래 시각·참조 관측·표본 제한·환경 분리·읽기 전용과 명령 실패/삭제 모드 부재를 검증합니다. DB는 대역이며 실제 MongoDB 시험과 구분합니다.

[실행/검증 범위](../../../../../runbook/광고_보관_점검과_배치_종료.md)

## AST 시그니처

```python
retention_database(documents)
class AdsRetentionTests(SimpleTestCase)
AdsRetentionTests.setUp(self)
AdsRetentionTests.state(self, name, document, now=None)
AdsRetentionTests.test_event_uses_first_received_time_and_exact_ninety_day_boundary(self)
AdsRetentionTests.test_delivery_uses_later_real_use_or_first_new_event_receipt(self)
AdsRetentionTests.test_admin_and_ledger_keep_distinct_365_day_bases(self)
AdsRetentionTests.test_metrics_uses_next_kst_midnight_instead_of_refresh_time(self)
AdsRetentionTests.test_noop_management_retention_is_pending(self)
AdsRetentionTests.test_missing_naive_future_invalid_or_overflow_bases_are_reported(self)
AdsRetentionTests.test_inspection_is_bounded_environment_scoped_and_never_mutates(self)
AdsRetentionTests.test_reference_observations_use_same_environment_without_payload_or_user_data(self)
AdsRetentionTests.test_delivery_open_or_invalid_report_window_is_reviewed(self)
AdsRetentionTests.test_invalid_input_is_rejected_before_querying(self)
AdsRetentionTests.test_invalid_sample_makes_report_fail_without_repair(self)
AdsRetentionTests.test_command_prints_safe_report_and_has_no_apply_mode(self)
AdsRetentionTests.test_command_failure_redacts_connection_and_invalid_basis_is_nonzero(self)
```
