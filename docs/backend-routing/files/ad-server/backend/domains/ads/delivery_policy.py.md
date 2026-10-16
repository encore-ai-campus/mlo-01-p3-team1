# ad-server/backend/domains/ads/delivery_policy.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../../../ad-server/backend/domains/ads/delivery_policy.py)

채택한30분 표시 수명과 보고 분리를 연결하기 위한 순수 helper입니다. 기본1800초와 광고 종료 중 이른 시각을 display_expires_at으로, 표시 마감+300초를 보고 마감으로 반환합니다. 시간대 있는 입력을 UTC밀리초로 정규화하고 종료<=발급·bool/비정수/비양수 TTL·표현 범위 초과는 ValidationError입니다. 반환된30분은 delivery 수명이며 캠페인의 ends_at을 변경하지 않습니다.

open_delivery_eligible은 현재 광고, occurrence_eligible은 발생 당시 광고 snapshot과 creative_version·placement가 같은지만 검사합니다. paused/기간·서명·guest·수신 지연·예산은 호출자가 검사해야 합니다. 자료를 변경하거나 DB에 접근하지 않습니다.

cap_at_midnight=False가 기본이며 KST 자정 cap은 True를 명시한 경우에만 적용하는 구현 후보입니다. strict bool만 허용합니다. 기본 runtime provider는 split_deadlines=True/cap_at_midnight=False를 명시하여30분 표시/보고 분리를 사용하고 자정에는 배달을 자동 종료하지 않습니다. AdsPublicPolicy 자체의False 기본값과 기존 배달/서명은 호환성을 위해 유지합니다. 재확인/자동 재발급·실제 배너는 이 helper가 구현하지 않습니다.

## AST 시그니처

```python
delivery_deadlines(issued_at, ends_at, ttl_seconds=DELIVERY_TTL_SECONDS, *, cap_at_midnight=False) -> tuple[datetime, datetime]
_same_creative(delivery, ad)
open_delivery_eligible(delivery, current_ad, now)
occurrence_eligible(delivery, historical_ad, occurred_at)
```
