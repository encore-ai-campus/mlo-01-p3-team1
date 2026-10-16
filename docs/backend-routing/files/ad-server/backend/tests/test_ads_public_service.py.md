# ad-server/backend/tests/test_ads_public_service.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../../ad-server/backend/tests/test_ads_public_service.py)

실제 AdsPublicService와 원자 rollback 메모리 fixture를 연결한 도메인 시험입니다. 선정/위치별 순환·발급 키 재전송·기존 delivery 재확인·만료/중단·서명/소유·쿠키 불가·허용 입력·최초 판정/예상 항목/MongoDB 내장 로그 원자성·8/5/15 단가를 검증합니다.

최초 응답은 중단/만료 뒤에도 보존하며 다른 본문 충돌·동시 최초 처리·억제 delivery 소비·정확한60/300초 경계·과거 게시 상태·KST 발생일·저장 실패 rollback을 확인합니다. 잠금 대기 중 중단 시각 소급 방지와 현재 종료 시각 단축의 표시 기한 반영도 검증합니다.

메모리 동시성·fixture 정책이며 실제 MongoDB/공유 guest/PostgreSQL/브라우저 구현의 운영 완료를 의미하지 않습니다.

split_deadlines=True를 명시한 선택 fixture에서 표시/보고 마감 분리·KST 자정 전 발생의 다음날 수신·정확한 표시 만료 발생 제외·300초 경계 수용·표시 마감의 HMAC 서명 포함을 추가 확인합니다. 기본False와 기존 delivery 동작은 유지하며 운영 provider를 활성화하지 않습니다.

측정 잠금 대기 이후의 실제 판정 시각으로 반복 창을 시작해52초 조기 재인정을 억제하는 재현도 포함합니다.

현행 로그 구조와 이전 자료 보존은 [광고 로그 저장 계약](../../../../../development/ads/MongoDB_광고_로그_저장_계약.md)을 따릅니다.

## AST 시그니처

```python
class AdsPublicServiceTests(SimpleTestCase)
AdsPublicServiceTests.setUp(self)
AdsPublicServiceTests.identifier(self)
AdsPublicServiceTests.make_service(self, **overrides)
AdsPublicServiceTests.create_ad(self, **overrides)
AdsPublicServiceTests.provide(self, placement='top', **overrides)
AdsPublicServiceTests.event(self, response, event_type='VIEWABLE_IMPRESSION', **overrides)
AdsPublicServiceTests.stop(self)
AdsPublicServiceTests.usage_entry(self, event_id)
AdsPublicServiceTests.test_highest_priority_ad_is_served_with_server_image_and_delivery(self)
AdsPublicServiceTests.test_tie_rotation_is_separate_for_top_and_bottom(self)
AdsPublicServiceTests.test_unavailable_budget_returns_empty_without_advancing_rotation(self)
AdsPublicServiceTests.test_request_key_replay_keeps_original_response_and_cursor(self)
AdsPublicServiceTests.test_parallel_request_key_creates_one_delivery(self)
AdsPublicServiceTests.test_reconfirm_keeps_same_delivery_and_does_not_move_cursor(self)
AdsPublicServiceTests.test_reconfirm_does_not_extend_event_expiration(self)
AdsPublicServiceTests.test_stopped_ad_is_removed_on_reconfirm_without_replacement(self)
AdsPublicServiceTests.test_wrong_owner_or_tampered_delivery_proof_is_hidden(self)
AdsPublicServiceTests.test_cookie_unavailable_can_display_without_inventing_a_guest(self)
AdsPublicServiceTests.test_unknown_body_fields_cannot_supply_accounting_decisions(self)
AdsPublicServiceTests.test_counted_event_saves_claim_window_usage_and_local_log_together(self)
AdsPublicServiceTests.test_bottom_impression_and_click_record_distinct_expected_tokens(self)
AdsPublicServiceTests.test_replay_retains_first_decision_after_stop_and_expiration(self)
AdsPublicServiceTests.test_same_event_id_changed_input_conflicts_without_new_mutations(self)
AdsPublicServiceTests.test_event_owner_and_proof_are_checked_even_when_event_id_exists(self)
AdsPublicServiceTests.test_new_event_id_for_consumed_delivery_type_is_duplicate(self)
AdsPublicServiceTests.test_parallel_first_events_count_delivery_type_once(self)
AdsPublicServiceTests.test_suppression_consumes_new_delivery_but_keeps_repeat_window(self)
AdsPublicServiceTests.test_exact_impression_repeat_boundary_is_counted(self)
AdsPublicServiceTests.test_exact_click_repeat_boundary_is_counted(self)
AdsPublicServiceTests.test_delayed_event_before_stop_uses_historical_ad(self)
AdsPublicServiceTests.test_event_at_stop_is_invalid_without_consuming_delivery(self)
AdsPublicServiceTests.test_more_than_300_seconds_delay_is_recorded_without_counting(self)
AdsPublicServiceTests.test_metric_day_uses_occurrence_kst_instead_of_receive_day(self)
AdsPublicServiceTests.test_event_or_usage_failure_rolls_back_all_eight_states(self)
AdsPublicServiceTests.test_failed_delivery_insert_does_not_advance_rotation(self)
AdsPublicServiceTests.test_image_requires_delivery_proof_and_active_current_ad(self)
AdsPublicServiceTests.test_response_mutation_cannot_change_stored_replay(self)
AdsPublicServiceTests.test_stop_waiting_for_lock_does_not_backdate_historical_validity(self)
AdsPublicServiceTests.test_reconfirmation_caps_display_at_shortened_current_end(self)
AdsPublicServiceTests.test_split_delivery_expiry_allows_delayed_report_after_midnight(self)
AdsPublicServiceTests.test_split_delivery_rejects_new_occurrence_at_display_expiry(self)
AdsPublicServiceTests.test_split_delivery_exact_receive_delay_is_still_allowed(self)
AdsPublicServiceTests.test_split_delivery_display_deadline_is_part_of_proof(self)
AdsPublicServiceTests.test_measurement_lock_wait_uses_actual_decision_time_for_repeat_window(self)
```
