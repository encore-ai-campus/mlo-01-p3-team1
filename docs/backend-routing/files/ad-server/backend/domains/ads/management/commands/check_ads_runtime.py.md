# ad-server/backend/domains/ads/management/commands/check_ads_runtime.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../../../../../ad-server/backend/domains/ads/management/commands/check_ads_runtime.py)

설정·명시 --database 스키마/로그 점검 명령입니다. 미확인/불일치는 INCOMPLETE와 실패 종료로 구분합니다.

현행 로그 구조와 이전 자료 보존은 [광고 로그 저장 계약](../../../../../../../../development/ads/MongoDB_광고_로그_저장_계약.md)을 따릅니다.

## AST 시그니처

```python
class Command(BaseCommand)
Command.add_arguments(self, parser)
Command.handle(self, *args, **options)
```
