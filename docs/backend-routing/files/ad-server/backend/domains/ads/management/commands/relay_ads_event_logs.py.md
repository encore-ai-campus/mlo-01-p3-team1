# ad-server/backend/domains/ads/management/commands/relay_ads_event_logs.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../../../../../ad-server/backend/domains/ads/management/commands/relay_ads_event_logs.py)

`relay_ads_event_logs --limit N`으로 공개 측정의 PENDING 로그를 공통 PostgreSQL sink에 한 batch 전달합니다. run_configured_event_relay를 호출하며 처리 결과 claimed/sent/failed/stale 수를 출력합니다. 기본 limit은20, worker가1~100 범위를 검증합니다.

관리 로그 명령 relay_ads_logs와 별도로 ad_events만 대상으로 합니다. sink 미설정은 DB claim 전에 차단합니다. 명령은 자체 스케줄러·PostgreSQL 테이블·일별 광고 집계를 만들지 않습니다. 실제 공통 sink 연결/운영 전달 검증은 별도입니다.

## AST 시그니처

```python
class Command(BaseCommand)
Command.add_arguments(self, parser)
Command.handle(self, *args, **options)
```
