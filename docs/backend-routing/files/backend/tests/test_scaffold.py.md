# backend/tests/test_scaffold.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../backend/tests/test_scaffold.py)

DB 없이 health와 개발 골격의 차단 경계를 검증합니다. health 200/database_checked=False, AUTHORIZER 미설정 관리 POST의 503, 관리자 UI `/admin/ads`의 404, health URL 이름을 확인합니다.

SimpleTestCase와 테스트 호스트 설정을 사용하며 입력은 Django 테스트 클라이언트 요청, 출력은 assertion 결과입니다. 광고 관리 URL이 없는지 확인하던 이전 테스트는 공통 인증 미연결 시 차단되는지 확인하도록 변경했습니다. DB·업무 기능 검증은 각 광고 테스트 파일에 분리합니다.

## AST 시그니처

```python
class ScaffoldTests(SimpleTestCase)
ScaffoldTests.test_health_does_not_require_database(self)
ScaffoldTests.test_ad_mutations_fail_closed_before_auth_integration(self)
ScaffoldTests.test_health_route_is_registered(self)
```
