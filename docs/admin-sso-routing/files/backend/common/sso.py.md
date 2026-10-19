# backend/common/sso.py

- 작성/수정일: 2026-10-19
- 담당: Codex, 관리자 역할/SSO 및 운영·로그 대시보드 분리
- 기준: develop@183ea87
- [코드·API·설정·검증 연결](../../../../development/관리자_3역할과_SSO_변경_라우팅.md)

```python
secure_url(value)
oidc_client()
claims_role(claims)
sync_identity(claims)
logout_url(request)
class SSOLogin(Endpoint)
SSOLogin.get(self, request)
class SSOCallback(Endpoint)
SSOCallback.get(self, request)
class KibanaDashboard(Endpoint)
KibanaDashboard.get(self, request)
class OperationsDashboard(KibanaDashboard)
class LogDashboard(KibanaDashboard)
```
