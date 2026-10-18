# backend/recommendation/tests/test_api.py 연결 라우팅

- 작성일: 2026-10-18
- 수정일: 2026-10-18
- 담당: Codex / 사용자 승인 통합 정합성 수정
- 브랜치/기준: develop / 160a66c
- [대응 코드](../../../../../../backend/recommendation/tests/test_api.py)
- [기준·변경 전후·검증·남은 연결](../../../../../development/통합_정합성_수정_변경_라우팅.md)

## 호출·저장·검증 경계

합성 카탈로그 참조를 v3로 갱신합니다. 기존 일반/고정 재생 목록 분리·운영 범위·부모 고정·멱등·소유/평가/제외 API 회귀는 유지합니다.

## AST 시그니처

```python
class ApiTests(TransactionTestCase)
ApiTests.setUp(self)
ApiTests.post(self, path, body, key='key', client=None)
ApiTests.basic(self)
ApiTests.result(self)
ApiTests.test_verified_catalog_reuse_and_hash_change(self)
ApiTests.catalog_copy(self, version, source_ref, is_test=True, ready=True)
ApiTests.test_general_recommendation_and_warmup_skip_latest_fixed_playback_catalog(self)
ApiTests.test_fixed_playback_catalog_alone_cannot_supply_general_recommendation(self)
ApiTests.test_catalog_selection_keeps_production_catalog_scope(self)
ApiTests.test_preview_parent_keeps_catalog_when_new_general_catalog_is_published(self)
ApiTests.test_historical_fixed_playback_result_stays_readable_and_parent_fixed(self)
ApiTests.test_default_flow_idempotency_ownership(self)
ApiTests.test_off_mode_does_not_depend_on_weather(self)
ApiTests.test_all_selected_tags_keep_raw_selection_but_use_any_filter(self)
ApiTests.test_strict_inputs_and_country_language_rejection(self)
ApiTests.test_exclusion_noop_revision_retry_and_approval_block(self)
ApiTests.test_cycle_change_409_before_provider_and_failure_preserves_parent(self)
ApiTests.test_csv_uses_gemini_and_preserves_catalog_seed_and_local_approval(self)
ApiTests.test_csv_missing_key_does_not_fall_back_to_rules(self)
ApiTests.test_local_feedback_restores_reactions_and_rating_without_changing_approval(self)
ApiTests.test_stale_and_invalid_exclusion_roll_back(self)
ApiTests.test_csrf_is_required_for_anonymous_mutation(self)
ApiTests.test_expired_job_does_not_generate_result(self)
ApiTests.test_weather_change_during_generation_rejects_stale_result(self)
ApiTests.test_snapshot_preserved_after_catalog_mutation(self)
ApiTests.test_expired_worker_cannot_fail_job_and_recovery_can_finish(self)
ApiTests.test_expired_worker_exception_does_not_overwrite_recoverable_job(self)
```
