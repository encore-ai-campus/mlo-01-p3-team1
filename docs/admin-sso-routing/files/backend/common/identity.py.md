# backend/common/identity.py

- 작성/수정일: 2026-10-19
- 담당: Codex, 관리자 역할/SSO 변경
- 기준: develop@183ea87
- [역할·API·저장·실행/검증 연결](../../../../development/관리자_3역할과_SSO_변경_라우팅.md)

이 문서는 해당 변경의 선언을 연결하며, 기존 함수의 담당/기획 정책을 재정의하지 않습니다. 구체적인 변경 전후와 원격 미연결 상태는 위 변경 라우팅을 따릅니다.

```python
raw_request(request)
guest(request, bootstrap=False)
owner(request)
admin(request, permission=None)
class GuestCookieMiddleware
GuestCookieMiddleware.__init__(self, get_response)
GuestCookieMiddleware.__call__(self, request)
```
