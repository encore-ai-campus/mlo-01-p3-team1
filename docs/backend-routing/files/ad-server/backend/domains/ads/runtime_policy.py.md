# ad-server/backend/domains/ads/runtime_policy.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../../../ad-server/backend/domains/ads/runtime_policy.py)

기본 공개 provider get_public_policy는 phase3-ads-20261015.1·1800초·split_deadlines=True·check_budget_history=True와 현재/과거 소재 helper를 연결합니다. cap_at_midnight=False로 배달 자체를 자정에 자동 종료하지 않습니다. 공유 guest·서명 키·HTTPS 주소는 외부 필수 설정입니다.

budget_eligible은 매 요청 원장 합계를 재계산하지 않고 저장된 검증 상태를 봅니다. 양의 예산2개와 불투명 budget_version이 없거나 검증 자료가 없으면 부적격입니다. 오늘 상태가 없으면 최근 검증 상태를 참조하여 자정의 빈 batch 구간을 새 캠페인 종료로 만들지 않습니다. 전날 일일 cutoff는 오늘에 적용하지 않고 전체 cutoff는 이어갑니다.

검증 시각이 잘못됐거나300초를 넘겨 낡으면 ADS_POLICY_UNAVAILABLE/503입니다. 이는 기술 장애이며 새로운 ENDED 상태/과거 실적 취소를 만들지 않습니다. 현재 일일/전체 차단 상태는 신규·기존 delivery 재확인·이미지에 적용합니다. 발생 당시 예산 cutoff 판정은 public_service의 명시 마커와 budget_occurrence_eligible이 담당합니다.

## AST 시그니처

```python
_unavailable()
budget_eligible(repository, ad, now)
get_public_policy()
```
