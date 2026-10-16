# 광고 측정 판정과 예상 토큰

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- 원본: [ad-server/backend/domains/ads/measurement.py](../../../../../../../ad-server/backend/domains/ads/measurement.py)

서버 delivery 문맥·당시 자격·기존 claim/반복 창을 받아 최초 판정 또는 불변 재전송을 계산합니다. 수명/서명은 delivery_valid, 당시 소재/게시 자격은 occurrence_eligible의 필수 서버 판정입니다. 클라이언트 본문에는 서버 참조/인정 여부/토큰을 허용하지 않습니다. 응답은 decision, 이번 claim/반복 창 변경은 outcome으로 분리하여 재전송에서 상태를 다시 적용하지 않습니다. metric_date_kst는 일반적으로 발생일이며 KST로 표현할 수 없는 제외 보고만 None입니다. POST /api/ad-events와 MongoDB 판정/claim/예상 항목 원자 저장은 public_service.py가 연결하며 일별 배치 집계는 별도 budget_service.py가 담당합니다.

시그니처는 `.cache/routing-budget-policy.json`의 Python AST 결과를 사용했습니다. 쿠키 불가 문맥의 owner_guest_id=None을 허용하되 운영 측정은 MEASUREMENT_UNAVAILABLE로 제외합니다.

DeliveryContext의 선택 필드 `display_expires_at: datetime | None = None`은 UTC밀리초·발급 이후로 검증합니다. 값이 있으면 발생 시각이 표시 마감과 같거나 이후인 보고를 DELIVERY_INVALID로 제외하고, 그 이전 발생은 별도 수신 지연300초와 보고 수명을 검사합니다. 생략한 기존 문맥에30분 마감을 소급 적용하지 않습니다. 같은 event_id의 저장된 최초 판정은 표시 마감 변경 후에도 먼저 재반환합니다.

judge_event의 선택 ads_policy_version 인자는 명시한 배달 당시 정책 버전을 최초 응답에 보존합니다. 기존 호출의 기본 버전은 ADS_POLICY_VERSION으로 유지합니다.

## AST 시그니처

```python
_reference(value, field)
_event_type(value)
_placement(value)
_flag(value, field)
class MeasurementEvent
MeasurementEvent.__post_init__(self)
MeasurementEvent.request_hash(self) -> str
validate_event_input(data: dict) -> MeasurementEvent
class DeliveryContext
DeliveryContext.__post_init__(self)
class MeasurementDecision
MeasurementDecision.as_response(self) -> dict
class RecordedEvent
RecordedEvent.__post_init__(self)
class MeasurementOutcome
repeat_key(delivery: DeliveryContext, event_type: str) -> tuple[str, str, str, str]
estimate_tokens(placement: str, event_type: str, *, counted: bool) -> int
judge_event(event: MeasurementEvent, *, delivery: DeliveryContext, owner_guest_id: str | None, received_at: datetime, processed_at: datetime, delivery_valid: bool, occurrence_eligible: bool, measurement_available: bool, delivery_type_consumed: bool, last_accepted_at: datetime | None, recorded_event: RecordedEvent | None=None, ads_policy_version: str=ADS_POLICY_VERSION) -> MeasurementOutcome
```
