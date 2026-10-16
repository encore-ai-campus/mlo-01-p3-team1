# ad-server/backend/domains/ads/management/commands/check_ads_logs.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../../../../../ad-server/backend/domains/ads/management/commands/check_ads_logs.py)

관리·측정·소진 MongoDB 로그의 건수/제한 표본 무결성을 읽기 점검합니다. 누락/손상은 실패로 알리고 자동 수정하지 않습니다.

현행 로그 구조와 이전 자료 보존은 [광고 로그 저장 계약](../../../../../../../../development/ads/MongoDB_광고_로그_저장_계약.md)을 따릅니다.

## AST 시그니처

```python
class Command(BaseCommand)
Command.add_arguments(self, parser)
Command.handle(self, *args, **options)
```
