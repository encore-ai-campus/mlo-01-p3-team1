# backend/recommendation/models.py 연결 라우팅

- 작성일: 2026-10-18
- 수정일: 2026-10-18
- 담당: Codex / 사용자 승인 통합 정합성 수정
- 브랜치/기준: develop / 160a66c
- [대응 코드](../../../../../backend/recommendation/models.py)
- [기준·변경 전후·검증·남은 연결](../../../../development/통합_정합성_수정_변경_라우팅.md)

## 호출·저장·검증 경계

Catalog.save가 신규 카탈로그와 DB 자동 증가 CatalogPublication을 같은 트랜잭션/DB alias에 기록합니다. 기존 카탈로그 갱신은 새 순번을 만들지 않습니다. Job/Playlist는 당시 카탈로그 FK와 snapshot을 유지합니다.

## AST 시그니처

```python
uid()
class OwnerLock(models.Model)
class Catalog(models.Model)
Catalog.save(self, *args, **kwargs)
class CatalogPublication(models.Model)
class Family(models.Model)
class Job(models.Model)
class Playlist(models.Model)
class DemoFeedback(models.Model)
class Idempotency(models.Model)
class PendingEvent(models.Model)
```
