# ad-server/backend/api/ads_sandbox.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../../ad-server/backend/api/ads_sandbox.py)

정식 서비스와 분리한 로컬 광고 확인 화면·접근 확인·개발 ADMIN/guest 어댑터입니다. `local_guard`는 sandbox 설정·테스트 DB/환경·MongoDB loopback 제한과 요청의 실제 REMOTE_ADDR/Host를 확인합니다. 전달 헤더의 임의 사용자/역할은 인증 근거가 아닙니다.

실행별 접근 코드로 서명한 instance/kind 쿠키를 발급하며 쿠키는 HttpOnly·SameSite=Strict·8시간의 로컬 HTTP 범위입니다. 같은 프로세스의 서명/instance를 검증하고 공유 PostgreSQL 계정/세션을 만들거나 운영 인증으로 사용하지 않습니다. 로그인·로그아웃·수동 갱신은 기존 CSRF/Origin 검사를 유지합니다.

`SandboxMiddleware`는 이 별도 설정으로 실행한 기존 `/api/` 관리/공개 경로도 로컬 로그인으로 보호합니다. 응답별 nonce CSP·no-store·no-referrer·frame 차단을 적용합니다. 일반 서비스 URLconf에는 이 화면을 등록하지 않습니다.

| 경로 | view·결과 |
|---|---|
| `GET /` | `home` → 개발 대시보드로 이동 |
| `GET/POST /dev/ads/login` | `login` → 접근 코드 확인·서명 쿠키/CSRF 토큰 회전 |
| `GET /dev/ads/` | `dashboard` → 기존 광고 API를 호출하는 임시 화면 |
| `POST /dev/ads/logout` | `logout` → 로컬 관리자/guest 쿠키 제거, 광고 게시 상태 유지 |
| `GET /dev/ads/status` | `status` → worker 상태·테스트 DB명·is_test·로그 NOT_CONNECTED |
| `POST /dev/ads/refresh` | `refresh` → 기존 예산/통계 작업1회, 경합409·오류503 |

`sandbox_guest`는 최초 bootstrap에서 개발용 guest 쿠키를 만들고 같은 instance의 검증 문맥을 재사용합니다. `is_test=true`인 배달/측정은 운영 카운트/예상량0이며 실제 운영 노출 조건을 우회하지 않습니다. 예외 문자열·접속 URI·접근 코드·proof를 상태/오류에 넣지 않습니다.

## AST 시그니처

```python
local_guard(request)
_cookie(request, name, salt)
read_admin(request)
_set_cookie(response, name, value, salt)
sandbox_admin(request, action)
sandbox_guest(request, *, bootstrap)
class SandboxMiddleware
SandboxMiddleware.__init__(self, get_response)
SandboxMiddleware.__call__(self, request)
csrf_failure(request, reason='')
home(request)
login(request)
dashboard(request)
logout(request)
status(request)
refresh(request)
```
