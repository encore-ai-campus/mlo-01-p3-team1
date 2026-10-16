# ad-server/backend/domains/ads/management/commands/run_ads_workers.py

- 작성일: 2026-10-15
- 수정일: 2026-10-16
- [원본 코드](../../../../../../../../../ad-server/backend/domains/ads/management/commands/run_ads_workers.py)

기존300초 예산/통계 작업의 단발/명시 반복 명령입니다. watch는 시작 상태 즉시 출력, 오류 후 다음 주기 재시도, Ctrl+C·메인 스레드 SIGTERM 시 제한 종료와 원래 핸들러 복원을 지원합니다. 상주 서비스 설치/실제 Linux 신호 검증은 별도입니다.

[실행/검증 범위](../../../../../../../../runbook/광고_보관_점검과_배치_종료.md)

## AST 시그니처

```python
class Command(BaseCommand)
Command.add_arguments(self, parser)
Command.handle(self, *args, **options)
Command.watch(self, group)
```
