# 관리자 SSO 코드 라우팅

작성/수정일: 2026-10-19. 담당: Codex. 기준: develop@183ea87.

역할·API·저장·검증·인계의 전체 흐름은 [관리자 SSO 변경 라우팅](../development/관리자_3역할과_SSO_변경_라우팅.md)을 따릅니다. 파일별 선언은 아래 문서에서 확인합니다.

- [backend/common/admin_roles.py](files/backend/common/admin_roles.py.md)
- [backend/common/sso.py](files/backend/common/sso.py.md)
- [backend/common/sso_tokens.py](files/backend/common/sso_tokens.py.md)
- [backend/common/sso_provision.py](files/backend/common/sso_provision.py.md)
- [backend/common/management/commands/provision_sso_admin.py](files/backend/common/management/commands/provision_sso_admin.py.md)
- [backend/common/management/commands/bootstrap_admin.py](files/backend/common/management/commands/bootstrap_admin.py.md)
- [backend/common/management/commands/prepare_runtime.py](files/backend/common/management/commands/prepare_runtime.py.md)
- [backend/common/management/commands/check_runtime.py](files/backend/common/management/commands/check_runtime.py.md)
- [backend/common/models.py](files/backend/common/models.py.md)
- [backend/common/identity.py](files/backend/common/identity.py.md)
- [backend/common/test_admin_sso.py](files/backend/common/test_admin_sso.py.md)
- [backend/common/test_runtime.py](files/backend/common/test_runtime.py.md)
- [backend/cafe/settings.py](files/backend/cafe/settings.py.md)
- [backend/common/migrations/0006_alter_guest_options_adminssoidentity.py](files/backend/common/migrations/0006_alter_guest_options_adminssoidentity.py.md)
- [backend/common/admin_dashboards.py](files/backend/common/admin_dashboards.py.md)
