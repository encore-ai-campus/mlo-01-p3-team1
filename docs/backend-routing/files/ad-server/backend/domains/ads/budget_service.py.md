# ad-server/backend/domains/ads/budget_service.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../../../ad-server/backend/domains/ads/budget_service.py)

5분 검증·통계를 한회 수행하는 업무 서비스입니다. 각 광고를 현재 상태로 다시 읽고 실제 광고 잠금을 얻은 뒤 예상 원장을 발생일KST/위치별로 집계합니다. 오늘 원본이 없으면 명시0행을 기록하고, 지표·예산 상태·서버용 종료 annotation을 같은 MongoDB 트랜잭션에 저장합니다. 최종 광고 교체 실패는 성공으로 넘기지 않고 전체 rollback합니다.

일일/전체 양의 예산과 budget_version이 있어야 검증 상태를 만듭니다. 검증 합계가 한도 이상이면 최초 daily_blocked_at/total_blocked_at을 기록합니다. 검증 전 합계 초과와 차단 전 발생의300초 지연 보고는 인정할 수 있으며 예약·실제 차감·초과0 보장을 추가하지 않습니다. 첫 중단 로그의 payload/hash는 후속 집계에도 보존합니다.

예산 버전/발생일별 상태로 과거 일일 차단과 전체 최초 cutoff를 유지합니다. annotation의 최초 차단 시각은 daily/total 중 이른 값이며 전체 종료에는 자동 시간 해제를 두지 않습니다. 관리자의 paused/일정/수정 version/updated_at/신원을 바꾸지 않고 수동 중단을 해제하지 않습니다. budget_occurrence_eligible은 발생 당시 관리 snapshot의 예산 버전과 cutoff를 비교하며 최초 응답 재반환은 공개 서비스가 먼저 처리합니다.

## AST 시그니처

```python
configured_budget(ad)
budget_occurrence_eligible(repository, ad, occurred_at)
class AdsBudgetService
AdsBudgetService.__init__(self, repository, *, clock=None)
AdsBudgetService._now(self)
AdsBudgetService._stop_log(self, state)
AdsBudgetService._refresh(self, repository, ad_id)
AdsBudgetService.run_once(self)
```
