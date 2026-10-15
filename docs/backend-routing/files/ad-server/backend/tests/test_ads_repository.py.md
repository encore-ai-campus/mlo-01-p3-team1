# ad-server/backend/tests/test_ads_repository.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../../ad-server/backend/tests/test_ads_repository.py)

MongoDB client/session/collection 대역으로 저장 어댑터의 연결 설정·primary·단일 session·트랜잭션 driver 재시도·멱등 unique 경합·실패 처리·트랜잭션 밖 쓰기 차단·version 조건/no-op 잠금·test 범위·분리된 조회 사본·커서/요약을 검증합니다.

입력은 driver 대역과 callback fixture이며 출력은 assertion 결과입니다. 실제 primary/커밋·동시 실행 결과는 별도 MongoDB 통합 테스트로 확인합니다. 중첩 helper 시그니처는 AST 자료 그대로 아래에 포함합니다.

## AST 시그니처

```python
class AdsRepositoryTests(SimpleTestCase)
AdsRepositoryTests.setUp(self)
AdsRepositoryTests.tearDown(self)
AdsRepositoryTests.test_unconfigured_repository_rejects_before_driver_creation(self)
AdsRepositoryTests.test_api_configuration_allows_private_replica_and_reuses_client(self)
AdsRepositoryTests.test_standalone_or_secondary_does_not_run_mutation(self)
AdsRepositoryTests.test_transaction_configuration_and_all_writes_use_one_session(self)
AdsRepositoryTests.test_driver_callback_retry_cannot_mutate_service_document(self)
AdsRepositoryTests.test_domain_error_keeps_conflict_status(self)
AdsRepositoryTests.test_failed_commit_returns_no_success_and_hides_driver_details(self)
AdsRepositoryTests.test_idempotency_unique_race_reopens_transaction_and_replays_winner(self)
AdsRepositoryTests.test_other_unique_conflict_is_not_replayed(self)
AdsRepositoryTests.test_write_outside_transaction_is_rejected(self)
AdsRepositoryTests.test_compare_and_swap_uses_expected_version_and_environment(self)
AdsRepositoryTests.test_unchanged_update_locks_with_real_write_and_restores_original(self)
AdsRepositoryTests.test_noop_lock_condition_conflict_aborts_before_restoration(self)
AdsRepositoryTests.test_noop_restore_conflict_does_not_return_success(self)
AdsRepositoryTests.test_changed_update_does_not_run_noop_lock(self)
AdsRepositoryTests.test_reads_are_detached_from_driver_and_share_test_scope(self)
AdsRepositoryTests.test_read_failure_becomes_service_unavailable(self)
AdsRepositoryTests.test_list_has_stable_sort_cursor_and_separate_more_flag(self)
AdsRepositoryTests.test_stopped_filter_wins_over_schedule_and_summary_reports_actual_counts(self)
```
