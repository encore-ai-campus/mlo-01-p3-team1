# ad-server/backend/tests/test_ads_sandbox.py

- 작성일: 2026-10-15
- 수정일: 2026-10-16
- [원본 코드](../../../../../../ad-server/backend/tests/test_ads_sandbox.py)

로컬 확인 도구의 HTTP 인증·출처·기존 API 격리와 프로세스/worker 경계를 검사합니다. 실제 CSRF를 활성화한 APIClient를 사용하고 fixture 접근 코드·instance·서명키와 메모리 광고 저장소/모의 프로세스로 재현합니다. 실제 공유 사용자 DB·운영 인증을 검증하는 시험이 아닙니다.

일반 URLconf의 개발 경로404·미로그인 API401·실제 Host/IP 및 sandbox/test DB 제한403·원문 역할/ID 무시·서명/instance/kind/쿠키 만료·CSRF/교차 Origin 거부·CSP nonce/no-store/same-origin referrer·POST 로그아웃/수동 갱신·안전한 오류를 검사합니다.

인증한 관리 업로드/공개 배달은 같은 is_test=True 저장 영역을 사용하고 측정 응답은 MEASUREMENT_UNAVAILABLE·counted=False이며 예상 원장 항목은 없습니다. 기존 MongoDB 프로세스는 시작/소유하지 않음·직접 시작한 MongoDB 실패 정리·batch 실패 잠금 해제/클래스명 상태·worker 단일 기동과 종료도 대역으로 검사합니다.

고정 시험의 통과 수치와 실제 MongoDB/HTTP/브라우저 실행 근거는 광고 수용 문서를 따릅니다. 본 파일의 테스트 정의나 AST 일치를 실제 운영 연결 성공으로 표시하지 않습니다.

현행 로그 구조와 이전 자료 보존은 [광고 로그 저장 계약](../../../../../development/ads/MongoDB_광고_로그_저장_계약.md)을 따릅니다.

## AST 시그니처

```python
class AdsSandboxTests(SimpleTestCase)
AdsSandboxTests.setUp(self)
AdsSandboxTests.csrf_headers(self)
AdsSandboxTests.login(self)
AdsSandboxTests.signed_admin(self, *, instance=None, kind='ads-sandbox-admin')
AdsSandboxTests.test_general_urlconf_does_not_expose_temporary_admin(self)
AdsSandboxTests.test_login_requires_csrf_and_correct_access_code(self)
AdsSandboxTests.test_login_issues_instance_bound_http_only_cookie(self)
AdsSandboxTests.test_missing_admin_redirects_page_and_denies_api_without_database_access(self)
AdsSandboxTests.test_public_ad_routes_also_require_local_admin_before_guest_or_database_access(self)
AdsSandboxTests.test_tampered_wrong_instance_and_wrong_kind_cookies_are_not_admin(self)
AdsSandboxTests.test_expired_admin_cookie_is_rejected(self)
AdsSandboxTests.test_local_guard_blocks_remote_ip_and_host_and_ignores_forwarded_headers(self)
AdsSandboxTests.test_sandbox_flag_is_required_even_with_valid_cookie(self)
AdsSandboxTests.test_guard_rejects_non_test_or_different_database_before_authentication(self)
AdsSandboxTests.test_login_has_no_store_and_per_response_nonce_content_security_policy(self)
AdsSandboxTests.test_status_requires_admin_and_reports_only_sandbox_health(self)
AdsSandboxTests.test_runtime_guard_rejects_remote_and_malformed_uris_without_database_connection(self)
AdsSandboxTests.test_launcher_rejects_regular_settings_before_starting_mongo_or_worker(self)
AdsSandboxTests.test_cross_origin_login_is_rejected_with_valid_csrf_token(self)
AdsSandboxTests.test_logout_requires_post_csrf_and_revokes_browser_cookie(self)
AdsSandboxTests.test_manual_policy_refresh_requires_csrf_and_runs_once(self)
AdsSandboxTests.test_manual_refresh_reports_busy_without_exposing_database_error_details(self)
AdsSandboxTests.test_sandbox_authorizer_does_not_accept_client_account_or_role(self)
AdsSandboxTests.test_local_guest_requires_admin_and_cookie_reuse_is_stable(self)
AdsSandboxTests.test_authenticated_management_and_public_requests_share_test_ads_only(self)
AdsSandboxTests.test_existing_mongo_is_not_started_or_owned_by_launcher(self)
AdsSandboxTests.test_failed_owned_mongo_start_terminates_only_owned_process(self)
AdsSandboxTests.test_failed_batch_releases_lock_and_status_has_only_error_class(self)
AdsSandboxTests.test_worker_starts_once_and_stop_releases_waiting_thread(self)
```

## 2026-10-16 로컬 프레젠테이션 추가

```python
AdsSandboxTests.test_login_assets_are_local_allowlisted_and_do_not_expose_source_or_content(self)
AdsSandboxTests.test_presentation_copy_is_read_again_and_escaped_without_relaxing_csp(self)
```

허용 에셋의 내용/MIME·알 수 없는 파일404·원격403·운영 URLconf404, 문구 재조회/이스케이프·CSP 유지·외부 모듈 로딩을 검증합니다.

## 2026-10-16 로그인 출처 충돌 수정

sandbox HTTP 헤더와 두 HTML meta를 same-origin으로 통일했습니다. 일반 폼의 Origin 보존과 기존 CSRF 유지, null/외부/다른 포트 거부를 검증하며 허용 출처 확장이나 csrf_exempt는 없습니다. AST 시그니처 변경은 없습니다.
