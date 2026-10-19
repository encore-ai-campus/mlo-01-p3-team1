# backend/common/test_runtime.py

- 작성/수정일: 2026-10-19
- 담당: Codex, 관리자 역할/SSO 변경
- 기준: develop@183ea87
- [역할·API·저장·실행/검증 연결](../../../../development/관리자_3역할과_SSO_변경_라우팅.md)

이 문서는 해당 변경의 선언을 연결하며, 기존 함수의 담당/기획 정책을 재정의하지 않습니다. 구체적인 변경 전후와 원격 미연결 상태는 위 변경 라우팅을 따릅니다.

```python
class RuntimeCommandsTests(SimpleTestCase)
RuntimeCommandsTests.test_deferred_archive_is_explicit_and_does_not_hide_database_failure(self)
RuntimeCommandsTests.test_deferred_archive_requires_a_preserved_local_original(self)
RuntimeCommandsTests.test_prepare_dry_run_never_migrates_or_imports(self)
RuntimeCommandsTests.test_config_check_does_not_open_connections(self)
RuntimeCommandsTests.test_connection_failure_cannot_be_reported_ready(self)
RuntimeCommandsTests.test_music_pending_can_start_admin_but_not_claim_recommendations_ready(self)
class PreparedAccountTests(TestCase)
PreparedAccountTests.test_existing_admin_is_not_reset_by_preparation(self)
PreparedAccountTests.test_new_admin_requires_explicit_permissions(self)
class DeferredPublicationTests(TestCase)
DeferredPublicationTests.test_publication_still_requires_explicit_deferral_review_and_preserved_bytes(self)
```
