# ad-server/backend/domains/ads/management/commands/relay_ads_logs.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../../../../../ad-server/backend/domains/ads/management/commands/relay_ads_logs.py)

광고 로그 worker를 한 batch 실행하는 Django 관리 명령입니다. `--limit`은 기본 20이며 worker가 1~100 strict 정수 범위를 확인합니다. 시스템/migration 검사를 생략하고 `run_configured_relay`로 연결합니다.

출력은 claimed/sent/failed/stale 개수입니다. sink 미설정·도메인 오류·잘못된 batch 크기는 CommandError로 전달합니다. 무한 스케줄러나 PostgreSQL 구현을 제공하지 않으며 실제 공통 sink가 연결되기 전에는 전달을 시작하지 않습니다.

## AST 시그니처

```python
class Command(BaseCommand)
Command.add_arguments(self, parser)
Command.handle(self, *args, **options)
```
