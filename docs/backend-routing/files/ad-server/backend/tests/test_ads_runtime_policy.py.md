# ad-server/backend/tests/test_ads_runtime_policy.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../../ad-server/backend/tests/test_ads_runtime_policy.py)

예산 양수/불투명 버전·검증 자료 미수령·정확300초/초과·잘못된 시각·오늘 일일/전체 cutoff·자정 fallback·DB 장애와 get_public_policy의 명시 배달/소재/역사 마커 연결을 시험합니다.

명령 시험은 기본 한회·300초 시작 간격 watch와 Ctrl+C(시각/sleep 대역)·실패 CommandError·sink 선검사·ad_budget_states 로그 한 batch 연결을 확인합니다. 실제 반복 기동이나 외부 DB/sink 실행은 하지 않습니다.

현행 로그 구조와 이전 자료 보존은 [광고 로그 저장 계약](../../../../../development/ads/MongoDB_광고_로그_저장_계약.md)을 따릅니다.

## AST 시그니처

```python
class RuntimeBudgetPolicyTests(SimpleTestCase)
RuntimeBudgetPolicyTests.setUp(self)
RuntimeBudgetPolicyTests.test_fresh_verified_budget_is_eligible_without_recomputing_usage(self)
RuntimeBudgetPolicyTests.test_unconfigured_nonpositive_or_boolean_budget_is_not_served(self)
RuntimeBudgetPolicyTests.test_budget_version_is_an_opaque_nonempty_string(self)
RuntimeBudgetPolicyTests.test_missing_configuration_or_verification_state_is_not_served(self)
RuntimeBudgetPolicyTests.test_exact_300_second_age_is_usable_and_next_millisecond_is_unavailable(self)
RuntimeBudgetPolicyTests.test_future_or_invalid_verification_timestamp_is_a_service_error(self)
RuntimeBudgetPolicyTests.test_current_daily_cutoff_blocks_display_and_total_lookup_is_unnecessary(self)
RuntimeBudgetPolicyTests.test_previous_daily_cutoff_does_not_carry_into_new_kst_day(self)
RuntimeBudgetPolicyTests.test_total_cutoff_survives_daily_rollover(self)
RuntimeBudgetPolicyTests.test_repository_failure_does_not_become_an_eligible_or_unlimited_budget(self)
RuntimeBudgetPolicyTests.test_runtime_policy_uses_adopted_delivery_and_material_rules(self)
class RuntimePolicyCommandsTests(SimpleTestCase)
RuntimePolicyCommandsTests.test_refresh_default_runs_one_batch_without_sleep_or_migrations(self)
RuntimePolicyCommandsTests.test_watch_uses_300_second_start_interval_and_handles_ctrl_c(self)
RuntimePolicyCommandsTests.test_refresh_database_failure_is_a_command_error(self)
```
