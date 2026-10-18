# backend/recommendation/tests/test_api.py 라우팅

- 작성일: 2026-10-16
- 수정일: 2026-10-18
- 담당: C 공개 대시보드·추천/음악 통합
- 범위: 일반 추천 후보와 고정 재생 시험 카탈로그 분리·오류 진단 후속
- 기준 브랜치/커밋: feature/ad-logic / f22f974
- 소스: [backend/recommendation/tests/test_api.py](../../../../../../backend/recommendation/tests/test_api.py)

## 기준과 공급·소비

Django TransactionTestCase와 메모리 시험 DB에서 합성 catalog·익명 세션·CSRF/멱등 키를 공급합니다. API/Job/Playlist/Family/피드백 저장과 작업자를 연결하고, 외부 YouTube·공유 운영 DB·실제 CSV 전체를 이 모듈에서 호출하지 않습니다.

기존 범위는 기본 생성·ON/OFF·원본 선택 보존·입력 차단·소유/CSRF·제외/승인·프리뷰 재설정·평가·스냅샷·날씨 만료/변경·임대 복구입니다. API 응답의 신규 사용자 catalog 선택 필드는 도입하지 않습니다.

## 이번 변경과 검증

추가 회귀 5건은 최신 전체 catalog와 더 최신 고정 재생 catalog가 함께 있을 때 신규 일반 추천/사전 로딩이 전체 catalog를 고르는지, 고정 목록만 있으면 503이며 Family/Job 생성이 롤백되는지, 운영 catalog 범위가 유지되는지 검증합니다. 또 일반 부모·과거 고정 목록 부모의 재설정은 원래 catalog를 고정하고, 과거 선곡표 snapshot을 계속 조회할 수 있는지 확인합니다.

추가 5건은 독립 표적 실행에서 모두 통과했습니다. 합성 곡 수는 실제 47곡의 청취나 86,485곡의 전수 품질 검증을 대체하지 않습니다. 실제 통합 백엔드/프런트 검사 수와 결과는 수용 기록을 따릅니다.

[정책·화면·저장 연결 라우팅](../../../../../development/기존_대시보드_YouTube_연결_라우팅.md)과 [일반 추천/재생 시험 분리 수용 기록](../../../../../acceptance/일반_추천_후보와_재생시험_분리_검증_20261016.md)을 함께 확인합니다. 수령 원문과 기존 backend-routing 문서는 수정하지 않습니다.

## AST 시그니처

검사 JSON의 python_files[].symbols를 정본으로 기록합니다.

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
ApiTests.test_local_feedback_restores_reactions_and_rating_without_changing_approval(self)
ApiTests.test_stale_and_invalid_exclusion_roll_back(self)
ApiTests.test_csrf_is_required_for_anonymous_mutation(self)
ApiTests.test_expired_job_does_not_generate_result(self)
ApiTests.test_weather_change_during_generation_rejects_stale_result(self)
ApiTests.test_snapshot_preserved_after_catalog_mutation(self)
ApiTests.test_expired_worker_cannot_fail_job_and_recovery_can_finish(self)
ApiTests.test_expired_worker_exception_does_not_overwrite_recoverable_job(self)
```

## 2026-10-18 develop 동기화 보완

부모 카탈로그 고정 시험은 명시 Gemini 설정을 갖춘 enqueue까지만 확인합니다. develop의 키 미설정 시 규칙 대체 금지 시험을 함께 유지하며 실제 Gemini 호출은 하지 않습니다.

```python
ApiTests.test_csv_uses_gemini_and_preserves_catalog_seed_and_local_approval(self)
ApiTests.test_csv_missing_key_does_not_fall_back_to_rules(self)
```

기준 develop `8bdad88`·기존 feature/ad-logic `0a0cc82`의 대조와 실제 재검증은 [통합 기록](../../../../../development/feature_전체_동기화_변경_라우팅_20261018.md)을 따릅니다.
