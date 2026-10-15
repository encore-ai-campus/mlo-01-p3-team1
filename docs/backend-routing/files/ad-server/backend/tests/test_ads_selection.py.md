# 광고 선정 규칙 검증

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- 원본: [ad-server/backend/tests/test_ads_selection.py](../../../../../../ad-server/backend/tests/test_ads_selection.py)

20개 순수 도메인 테스트입니다. 기간 밀리초 경계·최고 priority·ID 정렬/삭제 후 순환·위치별 커서·환경/예산 검사·3초 표시 상한을 확인하며 실제 DB/공개 배너를 실행하지 않습니다.

시그니처는 `.cache/routing-next-ads-rules.json`의 Python AST 결과를 사용했습니다.

MongoDB에서 복원한 BSON Int64 priority를 허용하면서 bool/범위 오류는 거절하는 사례를 추가했습니다.

## AST 시그니처

```python
class AdSelectionTests(TestCase)
AdSelectionTests.setUp(self)
AdSelectionTests.select(self, candidates, **overrides)
AdSelectionTests.test_inclusive_start_and_exclusive_end_at_millisecond_precision(self)
AdSelectionTests.test_priority_preserves_valid_bson_int64_values(self)
AdSelectionTests.test_timezone_and_submillisecond_inputs_are_normalized_to_mongodb_precision(self)
AdSelectionTests.test_ineligible_candidates_never_override_an_eligible_lower_priority(self)
AdSelectionTests.test_highest_priority_including_negative_values_is_selected(self)
AdSelectionTests.test_tied_priority_is_independent_of_input_order_and_uses_codepoint_sort(self)
AdSelectionTests.test_removed_previous_id_uses_successor_and_wraps_when_no_greater_id(self)
AdSelectionTests.test_top_and_bottom_cursors_are_independent(self)
AdSelectionTests.test_no_eligible_candidate_preserves_existing_cursor(self)
AdSelectionTests.test_calculation_without_advance_preserves_cursor_and_inputs(self)
AdSelectionTests.test_single_candidate_keeps_same_cursor_value_after_wrap(self)
AdSelectionTests.test_server_test_environment_is_explicit_and_isolated(self)
AdSelectionTests.test_budget_unknown_and_missing_are_rejected(self)
AdSelectionTests.test_candidate_validation_rejects_malformed_server_data(self)
AdSelectionTests.test_selection_rejects_duplicate_ids_and_invalid_parameters(self)
class AdDisplayValidityTests(TestCase)
AdDisplayValidityTests.setUp(self)
AdDisplayValidityTests.test_display_is_limited_to_three_seconds_from_evaluation(self)
AdDisplayValidityTests.test_earlier_ad_end_and_event_expiry_cap_display(self)
AdDisplayValidityTests.test_ended_or_expired_display_returns_none(self)
AdDisplayValidityTests.test_normalization_and_explicit_timezone_are_required(self)
AdDisplayValidityTests.test_valid_until_handles_last_datetime_without_overflow(self)
```
