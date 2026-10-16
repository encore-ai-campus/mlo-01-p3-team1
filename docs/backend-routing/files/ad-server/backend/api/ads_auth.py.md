# ad-server/backend/api/ads_auth.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../../ad-server/backend/api/ads_auth.py)

공통 인증 담당자의 서버 어댑터를 호출하는 경계입니다. 설정 `ADS_ADMIN_AUTHORIZER`의 callable에 원래 Django request와 read/write action을 전달하고 불변 `AdminIdentity`를 받습니다. 클라이언트가 보낸 계정 ID·역할 헤더로 관리자를 정하지 않습니다.

미설정·가져오기 실패·잘못된 반환형/외부 참조는 AUTH_UNAVAILABLE(503), 미로그인/비활성은 AUTH_REQUIRED(401), ADMIN 역할/광고 권한 미충족은 FORBIDDEN(403)입니다. 안전하지 않은 HTTP 메서드는 세션 방식 CSRF 검증도 통과해야 합니다. 광고 DB에 계정·세션 원본을 생성하지 않습니다. 실제 공유 인증 어댑터 연결은 별도 담당 계약입니다.

## AST 시그니처

```python
class AdminIdentity
authorize_admin(request, action: str) -> AdminIdentity
```
