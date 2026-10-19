# ad-server/backend/tests/test_ads_jobs.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../../ad-server/backend/tests/test_ads_jobs.py)

정책 작업 실패 재시도·안전한 상태·고정 주기·중복 실행 방지·제한 종료와 외부 로그 의존성 제거를 검사합니다.

현행 로그 구조와 이전 자료 보존은 [광고 로그 저장 계약](../../../../../development/ads/MongoDB_광고_로그_저장_계약.md)을 따릅니다.

## AST 시그니처

```python
class AdsJobsTests(SimpleTestCase)
AdsJobsTests.test_failed_job_recovers_without_leaking_exception_text(self)
AdsJobsTests.test_unknown_result_payload_is_not_exposed(self)
AdsJobsTests.test_blocked_log_thread_does_not_delay_policy_and_shutdown_is_bounded(self)
AdsJobsTests.test_watch_retries_after_failure_without_catchup_burst(self)
AdsJobsTests.test_successful_command_outputs_safe_counts(self)
AdsJobsTests.test_unavailable_error_code_and_text_are_sanitized(self)
AdsJobsTests.test_only_policy_runs_without_external_log_dependency(self)
AdsJobsTests.test_failed_policy_command_has_nonzero_exit_semantics(self)
```
