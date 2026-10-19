# ad-server/backend/api/common_bridge.py 연결 라우팅

- 작성일: 2026-10-18
- 수정일: 2026-10-18
- 담당: Codex / 사용자 승인 통합 정합성 수정
- 브랜치/기준: develop / 160a66c
- [대응 코드](../../../../../../ad-server/backend/api/common_bridge.py)
- [기준·변경 전후·검증·남은 연결](../../../../../development/통합_정합성_수정_변경_라우팅.md)

## 호출·저장·검증 경계

광고 서버 → 내부 Bearer와 원래 Cookie → 공통 ads-context의 ADMIN/guest 검증을 연결합니다. TLS/로컬 DEBUG 제한·리다이렉트 거부·응답 크기/시간 제한·Set-Cookie 전달을 유지합니다. 브라우저 role/owner 주장·공통 사용자 원본 복제는 사용하지 않습니다.

## AST 시그니처

```python
class NoRedirect(HTTPRedirectHandler)
NoRedirect.redirect_request(self, *args, **kwargs)
call_common(request, action, bootstrap=False)
authorize_admin(request, action)
resolve_guest(request, *, bootstrap)
```
