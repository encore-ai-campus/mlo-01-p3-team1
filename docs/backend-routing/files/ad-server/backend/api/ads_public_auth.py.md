# ad-server/backend/api/ads_public_auth.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../../ad-server/backend/api/ads_public_auth.py)

공통 서버가 검증한 `PublicGuestContext`와 명시적인 `AdsPublicPolicy`를 로드하는 연결 경계입니다. `ADS_GUEST_CONTEXT_PROVIDER`는 raw Django request와 bootstrap 여부를 받고 내부 owner_guest_id, bool 측정 가능 여부와 선택 응답 finalizer를 반환합니다. 광고 서비스가 사용자·쿠키 원본을 새로 만들지 않습니다.

쿠키 불가 상태는 owner_guest_id=None/measurement_available=False로 표현할 수 있습니다. 측정 가능인데 소유 참조가 없거나 타입/콜백이 잘못되면 GUEST_UNAVAILABLE/503입니다. `ADS_PUBLIC_POLICY_PROVIDER` 누락·예외·잘못된 객체는 ADS_POLICY_UNAVAILABLE/503으로 가립니다. 테스트 provider의 선택값을 운영 기본값으로 사용하지 않습니다.

## AST 시그니처

```python
class PublicGuestContext
resolve_guest(request, *, bootstrap: bool) -> PublicGuestContext
load_public_policy() -> AdsPublicPolicy
```
