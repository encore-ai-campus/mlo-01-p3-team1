# ad-server/backend/tests/test_ads_budget_service.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../../ad-server/backend/tests/test_ads_budget_service.py)

실제 관리·공개·예산 서비스와 MemoryPolicyRepository를 연결합니다. 최초0검증/지표·검증 전 초과 인정·cutoff 후 신규/재확인/이미지 차단·과거 발생 지연 인정/정확 cutoff 제외·300초 경계·최초 응답 replay를 확인합니다.

반복 집계 중복 방지·첫 cutoff/로그 payload 보존·일일/전체 자정 경계·증액의 새 budget_version 첫 검증·수동 paused 유지·미설정 예산의0지표·상태 저장 실패와 최종 광고 교체 실패 rollback·legacy 마커 없는 배달 비소급을 검증합니다. 늦게 전체 소진이 확인돼도 먼저 발생한 일일 종료 annotation을 늦추지 않는지도 포함합니다. 실제 DB/배포/결제 시험과 구분합니다.

## AST 시그니처

```python
class AdsBudgetServiceTests(SimpleTestCase)
AdsBudgetServiceTests.setUp(self)
AdsBudgetServiceTests.identifier(self)
AdsBudgetServiceTests.current_ad(self)
AdsBudgetServiceTests.current_state(self, day='2026-10-15')
AdsBudgetServiceTests.provide(self, **overrides)
AdsBudgetServiceTests.test_later_total_exhaustion_does_not_move_first_daily_block_forward(self)
AdsBudgetServiceTests.test_failed_ad_annotation_rolls_back_metrics_and_budget_state(self)
AdsBudgetServiceTests.event_data(self, delivery, event_type='VIEWABLE_IMPRESSION', **overrides)
AdsBudgetServiceTests.record(self, delivery, data)
AdsBudgetServiceTests.change_budget(self, daily, total)
AdsBudgetServiceTests.exhaust_daily_and_refresh(self)
AdsBudgetServiceTests.test_initial_refresh_distinguishes_real_zero_and_makes_ad_eligible(self)
AdsBudgetServiceTests.test_reports_before_next_verification_can_exceed_budget_without_hard_cap(self)
AdsBudgetServiceTests.test_cutoff_hides_existing_delivery_new_delivery_and_image_without_manual_pause(self)
AdsBudgetServiceTests.test_pre_cutoff_event_arriving_after_cutoff_is_counted_even_if_it_exceeds_budget(self)
AdsBudgetServiceTests.test_exact_cutoff_and_later_occurrence_are_invalid_without_consuming_click(self)
AdsBudgetServiceTests.test_pre_cutoff_report_at_exact_300_second_receive_delay_is_valid(self)
AdsBudgetServiceTests.test_first_response_replay_is_stable_after_cutoff_and_delivery_expiration(self)
AdsBudgetServiceTests.test_refresh_replaces_metrics_and_keeps_first_cutoff_log_and_payload(self)
AdsBudgetServiceTests.test_daily_rollover_keeps_old_cutoff_and_releases_only_the_daily_boundary(self)
AdsBudgetServiceTests.test_total_cutoff_survives_daily_rollover(self)
AdsBudgetServiceTests.test_budget_increase_needs_new_version_verification_and_keeps_old_history(self)
AdsBudgetServiceTests.test_manual_stop_is_kept_across_budget_refresh_and_new_day(self)
AdsBudgetServiceTests.test_unconfigured_budget_gets_real_zero_metrics_without_a_budget_state(self)
AdsBudgetServiceTests.test_failed_budget_state_save_rolls_back_metrics_annotation_and_state(self)
AdsBudgetServiceTests.test_legacy_delivery_is_not_retroactively_subject_to_budget_cutoff(self)
```
