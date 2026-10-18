# backend/common/music_api.py 연결 라우팅

- 작성일: 2026-10-18
- 수정일: 2026-10-18
- 담당: Codex / 사용자 승인 통합 정합성 수정
- 브랜치/기준: develop / 160a66c
- [대응 코드](../../../../../backend/common/music_api.py)
- [기준·변경 전후·검증·남은 연결](../../../../development/통합_정합성_수정_변경_라우팅.md)

## 호출·저장·검증 경계

등록→원본 보관→검수→명시 발행 API와 ADMIN 권한/CSRF/멱등/원본 SHA 검사를 유지합니다. readiness의 카탈로그 목록은 등록 순번을 사용합니다. export/publish가 공급하는 시즌 적격·판정 버전을 이어받습니다.

## AST 시그니처

```python
mutation(request, user, scope, body, operation)
class Imports(Endpoint)
Imports.post(self, request)
class Reviews(Endpoint)
Reviews.get(self, request)
class ReviewUpdate(Endpoint)
ReviewUpdate.post(self, request, track_id)
class Readiness(Endpoint)
Readiness.get(self, request)
class Publish(Endpoint)
Publish.post(self, request)
```
