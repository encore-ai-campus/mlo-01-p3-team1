# ad-server/backend/domains/ads/management/commands/relay_ads_budget_logs.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../../../../../ad-server/backend/domains/ads/management/commands/relay_ads_budget_logs.py)

relay_ads_budget_logs --limit N으로 ad_budget_states.log_relay의 첫 소진 확인 로그를 한 batch 전달합니다. get_log_sink를 먼저 확인해 미설정이면 정책 저장소 접근/claim 전에 차단하고, 기존 AdsLogRelay의 created_at 정렬·claim/ack/재시도·동일 ID/hash 계약을 사용합니다.

이 명령은 예산 합계·cutoff·지표·원장을 다시 계산하지 않습니다. sink의 명시 True는 PostgreSQL durable commit 또는 동일 ID/동일 payload 확인을 의미하며 실제 PostgreSQL 연결은 별도입니다.

## AST 시그니처

```python
run_configured_budget_relay(limit=20)
class Command(BaseCommand)
Command.add_arguments(self, parser)
Command.handle(self, *args, **options)
```
