# ad-server/backend/domains/ads/errors.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../../../ad-server/backend/domains/ads/errors.py)

도메인 오류를 code/message/http_status/fields로 보존하여 HTTP 공통 오류에 연결합니다. ValidationError(422), NotFound(404), VersionConflict·IdempotencyConflict(409), DatabaseUnavailable(503)를 제공합니다.

입력은 각 검증·서비스·저장소의 실패 상황, 출력은 예외 객체입니다. `api/ads.py:error_response`가 이를 응답으로 변환합니다. `AdsError`는 DomainError의 별칭이며 별도 정책이나 오류 형식을 추가하지 않습니다.

## AST 시그니처

```python
class DomainError(Exception)
DomainError.__init__(self, code, message, http_status, fields=None)
class ValidationError(DomainError)
ValidationError.__init__(self, message='광고 입력을 확인해 주세요.', fields=None)
class NotFound(DomainError)
NotFound.__init__(self, message='광고 자료를 찾을 수 없습니다.')
class VersionConflict(DomainError)
VersionConflict.__init__(self, message='최신 광고를 확인하고 다시 저장해 주세요.', fields=None)
class IdempotencyConflict(DomainError)
IdempotencyConflict.__init__(self, message='같은 멱등키에 다른 요청을 사용할 수 없습니다.')
class DatabaseUnavailable(DomainError)
DatabaseUnavailable.__init__(self, message='광고 저장소에 연결할 수 없습니다.')
```
