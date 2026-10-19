# ad-server/backend/domains/ads/public_policy.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../../../ad-server/backend/domains/ads/public_policy.py)

미정 운영 계약을 서버의 명시 정책으로 전달하는 불변 객체입니다. version·양의 정수 delivery_ttl_seconds와 budget_eligible/open_delivery_eligible/occurrence_eligible 세 callable을 요구합니다. 잘못된 구성은 ADS_POLICY_UNAVAILABLE/503입니다.

`split_deadlines: bool = False`는 표시/보고 마감 분리의 명시 선택입니다. strict bool만 허용하고 생략하면 기존 단일 만료 경로를 유지합니다. True인 경우 delivery_policy.py helper로 표시 마감을 계산하고 기존 event_expires_at은 표시 마감+300초의 보고 기한으로 저장합니다. cap_at_midnight: bool = False도 strict bool이며 True는 split_deadlines=True에서만 허용합니다. 배달 자정 단축은 기본 미적용입니다. check_budget_history: bool = False도 strict bool이며 이전 provider와 호환합니다. 기본 runtime provider는 split_deadlines/check_budget_history를True로 명시하고 저장된5분 검증 결과와 당시 cutoff를 연결합니다.

예산 자격 callback은 저장소/광고/검사 시각을, 열린 delivery와 발생 당시 자격 callback은 delivery/해당 광고 snapshot/시각을 받습니다. 예산 금액은 광고별 명시 입력이며 이 객체가 임의 기본액을 만들지 않습니다. 실제 반복 프로세스·공유 인증/서명/주소·배포 연결은 별도입니다. 트랜잭션 안에서 호출되므로 callback은 외부 네트워크 부작용 없이 재시도 가능한 판정을 제공해야 합니다.

## AST 시그니처

```python
class AdsPublicPolicy
AdsPublicPolicy.__post_init__(self)
```
