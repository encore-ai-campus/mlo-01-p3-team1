# ad-server/backend/tests/test_common_bridge.py 연결 라우팅

- 작성일: 2026-10-18
- 수정일: 2026-10-18
- 담당: Codex / 사용자 승인 통합 정합성 수정
- 브랜치/기준: develop / 160a66c
- [대응 코드](../../../../../../ad-server/backend/tests/test_common_bridge.py)
- [기준·변경 전후·검증·남은 연결](../../../../../development/통합_정합성_수정_변경_라우팅.md)

## 호출·저장·검증 경계

네트워크를 모의하여 Bearer/Cookie·ADMIN/guest DTO·쿠키 전달과 잘못된 설정/응답/오류의 안전한 차단을 검증합니다. 실제 공통 호스트 인증 수용을 주장하지 않습니다.

## AST 시그니처

```python
class CommonBridgeTests(SimpleTestCase)
CommonBridgeTests.reply(self, body)
CommonBridgeTests.test_guest_cookie_forward_and_no_browser_assertions(self)
CommonBridgeTests.test_non_tls_production_bridge_is_rejected_before_request(self)
CommonBridgeTests.test_network_exception_is_sanitized(self)
CommonBridgeTests.test_oversized_identity_response_fails_closed(self)
```
