# ad-server/backend/tests/test_ads_api.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../../ad-server/backend/tests/test_ads_api.py)

공통 ADMIN 어댑터의 테스트 대역과 메모리 저장소를 사용해 HTTP 경계를 검증합니다. 미연결 503·권한/비활성·클라이언트 신원 무시·본문 해석 전 인증/CSRF, strict body/priority·멱등키·원응답 재생·버전·정지 상태·multipart 원본/미리보기·서명 커서·실제 개수와 미연결 측정·공통 오류/응답 헤더를 확인합니다.

입력은 Django 테스트 클라이언트 요청과 대역 identity/저장소이며 출력은 assertion 결과입니다. 테스트 provider는 운영 인증 구현으로 사용하지 않습니다. 실제 MongoDB·공통 PostgreSQL 접속은 검증하지 않습니다. 아래 목록에는 테스트 fixture와 중첩 helper도 AST에 잡힌 그대로 포함합니다.

선택 예산 쌍의 관리 API 저장/부분 입력 무저장과 materialized0/집계 시각 반환을 추가 검증합니다.

현행 로그 구조와 이전 자료 보존은 [광고 로그 저장 계약](../../../../../development/ads/MongoDB_광고_로그_저장_계약.md)을 따릅니다.

## AST 시그니처

```python
allowed_admin(request, action)
missing_admin(request, action)
user_identity(request, action)
inactive_admin(request, action)
forbidden_admin(request, action)
unavailable_auth(request, action)
class AdsApiTests(SimpleTestCase)
AdsApiTests.setUp(self)
AdsApiTests.post_json(self, path, data, **headers)
AdsApiTests.assert_error(self, response, status, code, fields=None)
AdsApiTests.test_unconnected_auth_fails_closed_and_ignores_client_identity_headers(self)
AdsApiTests.test_shared_provider_controls_401_403_and_503_before_body_parsing(self)
AdsApiTests.test_invalid_shared_identity_is_service_failure(self)
AdsApiTests.test_csrf_missing_token_rejects_before_malformed_json(self)
AdsApiTests.test_untrusted_origin_rejects_before_malformed_json_even_with_csrf(self)
AdsApiTests.test_valid_csrf_and_auth_allow_json_parse_error_as_422(self)
AdsApiTests.test_unknown_fields_report_actual_sorted_names_and_save_nothing(self)
AdsApiTests.test_priority_rejects_bool_string_and_float_without_coercion(self)
AdsApiTests.test_idempotency_header_required(self)
AdsApiTests.test_create_replay_uses_server_actor_and_original_body_with_new_request_header(self)
AdsApiTests.test_same_key_different_body_returns_conflict(self)
AdsApiTests.test_update_and_stop_preserve_stop_and_replay_before_old_version(self)
AdsApiTests.test_upload_multipart_replays_original_asset_without_extra_file(self)
AdsApiTests.test_upload_rejects_non_image_and_extra_fields(self)
AdsApiTests.test_preview_uses_read_authority_and_creates_no_operational_data(self)
AdsApiTests.test_asset_read_returns_original_bytes_with_admin_auth(self)
AdsApiTests.test_summary_distinguishes_real_counts_and_unconnected_measurement(self)
AdsApiTests.test_summary_returns_materialized_zero_and_batch_time(self)
AdsApiTests.test_budget_pair_is_saved_through_authenticated_management_api(self)
AdsApiTests.test_partial_budget_pair_is_rejected_by_http_without_write(self)
AdsApiTests.test_list_accepts_filters_and_returns_signed_cursor_bound_to_them(self)
AdsApiTests.test_list_rejects_malformed_cursor_unknown_duplicate_filters_and_bad_page_sizes(self)
AdsApiTests.test_invalid_filter_enum_uses_option_invalid_error(self)
AdsApiTests.test_database_failure_uses_common_503_without_exposing_connection_details(self)
AdsApiTests.test_configured_contract_version_is_response_header_only(self)
```
