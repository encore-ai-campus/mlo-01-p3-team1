# ad-server/backend/domains/ads/management/commands/refresh_ads_policy.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../../../../../ad-server/backend/domains/ads/management/commands/refresh_ads_policy.py)

refresh_ads_policy는 AdsBudgetService와 정책 저장소를 연결해 기본 한회만 갱신하고 ads_checked/blocked/metrics_rows 수를 출력합니다. 명시 --watch일 때만300초 시작 간격으로 반복하며 실행 시간을 대기에서 빼고 Ctrl+C로 종료합니다. 시스템·공통 migration 검사를 별도로 실행하지 않습니다.

DB/도메인 오류는 CommandError로 전달합니다. 이 파일 작성이 반복 프로세스·AWS 배포·스케줄러 실제 기동을 의미하지 않습니다. batch는 매 요청 실시간 대시보드나 실제 토큰 차감이 아닙니다.

## AST 시그니처

```python
class Command(BaseCommand)
Command.add_arguments(self, parser)
Command.handle(self, *args, **options)
```
