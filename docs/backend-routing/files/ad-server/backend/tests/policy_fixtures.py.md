# ad-server/backend/tests/policy_fixtures.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../../ad-server/backend/tests/policy_fixtures.py)

MemoryPublicRepository를 확장한 테스트 저장소입니다. 기존8종 상태에 budget_states/metrics를 snapshot 대상으로 추가해 저장 실패 시 함께 되돌립니다. 정책 참조·버전/날짜·CAS·최초 전체 cutoff·원장 실제 행별 집계·멱등 지표 교체·요약의0/미연결 구분을 메모리에서 제공합니다.

실제 서비스 통합 시험의 대역이며 MongoDB validator·잠금/driver 경합이나 운영 예산을 대체하지 않습니다. fixture의 is_test=False는 격리 메모리에서 운영 판정 분기만 확인하기 위한 값입니다.

## AST 시그니처

```python
class MemoryPolicyRepository(MemoryPublicRepository)
MemoryPolicyRepository.__init__(self, *, is_test=False)
MemoryPolicyRepository.budget_state_id(self, ad_id, budget_version, metric_date_kst)
MemoryPolicyRepository.list_policy_ads(self)
MemoryPolicyRepository.usage_rows(self, ad_id)
MemoryPolicyRepository.get_budget_state(self, ad_id, budget_version, metric_date_kst)
MemoryPolicyRepository.latest_budget_state(self, ad_id, budget_version)
MemoryPolicyRepository.total_budget_cutoff(self, ad_id, budget_version)
MemoryPolicyRepository.save_budget_state(self, document, expected_revision)
MemoryPolicyRepository.replace_daily_metrics(self, ad_id, rows, as_of)
MemoryPolicyRepository.metrics_summary(self, now, ad_id=None)
```
