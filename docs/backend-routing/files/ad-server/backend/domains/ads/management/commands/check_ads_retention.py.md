# ad-server/backend/domains/ads/management/commands/check_ads_retention.py

- 작성일: 2026-10-16
- 수정일: 2026-10-16
- [원본 코드](../../../../../../../../../ad-server/backend/domains/ads/management/commands/check_ads_retention.py)

기존 광고 보관 기산점·기간 도래·참조의 읽기 점검 명령입니다. primary/환경을 확인하고 제한 표본만 검사합니다. --apply·삭제·TTL 모드는 없습니다. 잘못된 기산점/DB 장애는 실패 종료로 알리며 비밀값을 출력하지 않습니다.

[실행/검증 범위](../../../../../../../../runbook/광고_보관_점검과_배치_종료.md)

## AST 시그니처

```python
class Command(BaseCommand)
Command.add_arguments(self, parser)
Command.handle(self, *args, **options)
```
