"""공개 측정 서비스가 사용하는 순수 판정 규칙입니다.

호출자는 guest 소유, 당시 광고/소재 자격, delivery 유효성 및 해당 반복 키의 상태를
서버에서 확인합니다. 판정/claim/반복 창/예상 항목의 원자 저장은 공개 서비스와 저장소가
담당하며 이 모듈은 DB 쓰기·로그 전달·결제를 수행하지 않습니다.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from .errors import IdempotencyConflict, NotFound, ValidationError
from .service import canonical_hash
from .validation import utc_datetime, utc_string, validate_fields

ADS_POLICY_VERSION = "phase3-ads-20261014.1"
EVENT_TYPES = frozenset({"VIEWABLE_IMPRESSION", "CLICK"})
EVENT_FIELDS = frozenset({"event_id", "delivery_id", "event_type", "occurred_at"})
REPEAT_WINDOWS = {
    "VIEWABLE_IMPRESSION": timedelta(seconds=60),
    "CLICK": timedelta(seconds=300),
}
MAX_RECEIVE_DELAY = timedelta(seconds=300)
KST = timezone(timedelta(hours=9))


def _reference(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(fields={field: "비어 있지 않은 서버 참조 ID가 필요합니다."})


def _event_type(value):
    if not isinstance(value, str) or value not in EVENT_TYPES:
        raise ValidationError(fields={"event_type": "VIEWABLE_IMPRESSION 또는 CLICK이 필요합니다."})


def _placement(value):
    if not isinstance(value, str) or value not in {"top", "bottom"}:
        raise ValidationError(fields={"placement": "top 또는 bottom이 필요합니다."})


def _flag(value, field):
    if type(value) is not bool:
        raise ValidationError(fields={field: "서버에서 검증한 bool 판정이 필요합니다."})


@dataclass(frozen=True, slots=True)
class MeasurementEvent:
    event_id: str
    delivery_id: str
    event_type: str
    occurred_at: datetime

    def __post_init__(self):
        _reference(self.event_id, "event_id")
        _reference(self.delivery_id, "delivery_id")
        _event_type(self.event_type)
        object.__setattr__(self, "occurred_at", utc_datetime(self.occurred_at))

    @property
    def request_hash(self) -> str:
        return canonical_hash(
            {
                "event_id": self.event_id,
                "delivery_id": self.delivery_id,
                "event_type": self.event_type,
                "occurred_at": self.occurred_at,
            }
        )


def validate_event_input(data: dict) -> MeasurementEvent:
    """광고/guest/단가/인정 여부 등 서버 필드를 요청 본문으로 받지 않습니다."""
    validate_fields(data, EVENT_FIELDS)
    return MeasurementEvent(**data)


@dataclass(frozen=True, slots=True)
class DeliveryContext:
    """서버가 읽은 불변 배달과 당시 유효 구간입니다. 수명에 기본값은 없습니다.

    starts_at/ends_at/stopped_at은 해당 발생 시각의 이력에서 확인한 값이어야 합니다.
    현재 편집값으로 당시 구간을 대체하지 않습니다. 소재 변경 정책 등 추가 자격은
    judge_event의 occurrence_eligible에 명시적으로 전달합니다. display_expires_at은
    신규 배달의 발생 허용 상한이며 생략한 기존 문맥은 delivery_valid 검사와 호환됩니다.
    """

    delivery_id: str
    owner_guest_id: str | None
    ad_id: str
    creative_version: str
    placement: str
    issued_at: datetime
    starts_at: datetime
    ends_at: datetime
    stopped_at: datetime | None
    is_test: bool
    display_expires_at: datetime | None = None

    def __post_init__(self):
        for field in ("delivery_id", "ad_id", "creative_version"):
            _reference(getattr(self, field), field)
        if self.owner_guest_id is not None:
            _reference(self.owner_guest_id, "owner_guest_id")
        _placement(self.placement)
        _flag(self.is_test, "is_test")
        for field in ("issued_at", "starts_at", "ends_at"):
            object.__setattr__(self, field, utc_datetime(getattr(self, field)))
        if self.stopped_at is not None:
            object.__setattr__(self, "stopped_at", utc_datetime(self.stopped_at))
        if self.starts_at >= self.ends_at:
            raise ValidationError(fields={"ends_at": "당시 시작 시각보다 이후여야 합니다."})
        if self.display_expires_at is not None:
            object.__setattr__(self, "display_expires_at", utc_datetime(self.display_expires_at))
            if self.display_expires_at <= self.issued_at:
                raise ValidationError(
                    fields={"display_expires_at": "배달 발급 시각보다 이후여야 합니다."}
                )


@dataclass(frozen=True, slots=True)
class MeasurementDecision:
    event_id: str
    delivery_id: str
    event_type: str
    result: str
    counted: bool
    occurred_at: datetime
    received_at: datetime
    processed_at: datetime
    accepted_at: datetime | None
    metric_date_kst: date | None
    estimated_tokens: int
    ads_policy_version: str

    def as_response(self) -> dict:
        """ADS01의 정상 판정 응답 필드만 직렬화합니다. HTTP를 등록하지 않습니다."""
        return {
            "event_id": self.event_id,
            "delivery_id": self.delivery_id,
            "event_type": self.event_type,
            "result": self.result,
            "counted": self.counted,
            "occurred_at": utc_string(self.occurred_at),
            "received_at": utc_string(self.received_at),
            "processed_at": utc_string(self.processed_at),
            "ads_policy_version": self.ads_policy_version,
        }


@dataclass(frozen=True, slots=True)
class RecordedEvent:
    """소유별 조회를 마친 최초 판정입니다. 재전송에서 당시 결과를 유지합니다."""

    event: MeasurementEvent
    owner_guest_id: str | None
    decision: MeasurementDecision

    def __post_init__(self):
        if self.owner_guest_id is not None:
            _reference(self.owner_guest_id, "owner_guest_id")
        if not isinstance(self.event, MeasurementEvent) or not isinstance(
            self.decision, MeasurementDecision
        ):
            raise ValidationError("최초 요청과 판정의 서버 기록이 필요합니다.")
        if any(
            getattr(self.event, field) != getattr(self.decision, field)
            for field in ("event_id", "delivery_id", "event_type", "occurred_at")
        ):
            raise ValidationError("최초 요청과 판정 참조가 일치하지 않습니다.")


@dataclass(frozen=True, slots=True)
class MeasurementOutcome:
    """불변 응답과 이번 처리의 상태 변경 지시를 분리합니다.

    재전송은 같은 decision을 반환하되 claim/창을 다시 적용하지 않습니다.
    consume_delivery_type=True와 new_accepted_at의 원자 저장은 호출자 책임입니다.
    """

    decision: MeasurementDecision
    replayed: bool
    consume_delivery_type: bool
    new_accepted_at: datetime | None


def repeat_key(delivery: DeliveryContext, event_type: str) -> tuple[str, str, str, str]:
    """소재 버전이나 delivery 변경은 같은 광고의 반복 창을 초기화하지 않습니다."""
    if not isinstance(delivery, DeliveryContext):
        raise ValidationError("서버 delivery 문맥이 필요합니다.")
    _reference(delivery.owner_guest_id, "owner_guest_id")
    _event_type(event_type)
    return delivery.owner_guest_id, delivery.ad_id, delivery.placement, event_type


def estimate_tokens(placement: str, event_type: str, *, counted: bool) -> int:
    _placement(placement)
    _event_type(event_type)
    _flag(counted, "counted")
    if not counted:
        return 0
    if event_type == "CLICK":
        return 15
    return 8 if placement == "top" else 5


def judge_event(
    event: MeasurementEvent,
    *,
    delivery: DeliveryContext,
    owner_guest_id: str | None,
    received_at: datetime,
    processed_at: datetime,
    delivery_valid: bool,
    occurrence_eligible: bool,
    measurement_available: bool,
    delivery_type_consumed: bool,
    last_accepted_at: datetime | None,
    recorded_event: RecordedEvent | None = None,
    ads_policy_version: str = ADS_POLICY_VERSION,
) -> MeasurementOutcome:
    """최초 요청 재반환 → 문맥/시간/당시 자격 → claim → 반복 제한을 판정합니다.

    delivery_valid는 별도 보고 기한/서명 검사 결과입니다. display_expires_at이 있으면
    발생 시각은 해당 상한 미만이어야 하며 수신 시각이 표시 상한을 넘었다는 이유만으로
    당시 유효 이벤트를 제외하지 않습니다. 3초 재확인·300초 지연·보관 기한과 구분합니다.
    last_accepted_at은 repeat_key(delivery, event.event_type)의 서버 상태여야 합니다.
    타 소유/타 배달은404, 같은 event_id의 다른 정규 본문은409입니다. COUNTED 및
    REPEAT_SUPPRESSED만 해당 delivery/type을 처음 소비합니다. 유효 노출 조건/실제
    사용자 클릭은 브라우저 연결과 검증 경계이며 이 함수가 직접 관측하지 않습니다.
    """
    if not isinstance(event, MeasurementEvent) or not isinstance(delivery, DeliveryContext):
        raise ValidationError("검증된 측정 요청과 서버 delivery 문맥이 필요합니다.")
    if owner_guest_id is not None:
        _reference(owner_guest_id, "owner_guest_id")
    _reference(ads_policy_version, "ads_policy_version")
    for name, value in (
        ("delivery_valid", delivery_valid),
        ("occurrence_eligible", occurrence_eligible),
        ("measurement_available", measurement_available),
        ("delivery_type_consumed", delivery_type_consumed),
    ):
        _flag(value, name)

    # 원래 판정은 재전송 당시의 시간·중단·소재/단가로 재계산하지 않습니다.
    if recorded_event is not None:
        if not isinstance(recorded_event, RecordedEvent):
            raise ValidationError("서버 최초 판정 기록이 필요합니다.")
        if recorded_event.owner_guest_id != owner_guest_id:
            raise NotFound("광고 배달 자료를 찾을 수 없습니다.")
        if recorded_event.event.event_id != event.event_id:
            raise ValidationError("조회한 최초 event_id가 요청과 다릅니다.")
        if recorded_event.event.request_hash != event.request_hash:
            raise IdempotencyConflict()
        return MeasurementOutcome(recorded_event.decision, True, False, None)

    if measurement_available and (owner_guest_id is None or delivery.owner_guest_id is None):
        raise ValidationError("운영 측정에는 공유 서비스의 검증된 guest 참조가 필요합니다.")
    if delivery.delivery_id != event.delivery_id or (
        delivery.owner_guest_id is not None
        and owner_guest_id is not None
        and delivery.owner_guest_id != owner_guest_id
    ):
        raise NotFound("광고 배달 자료를 찾을 수 없습니다.")
    received_at = utc_datetime(received_at)
    processed_at = utc_datetime(processed_at)
    if processed_at < received_at:
        raise ValidationError("처리 시각은 수신 시각보다 이전일 수 없습니다.")
    if last_accepted_at is not None:
        last_accepted_at = utc_datetime(last_accepted_at)
        if last_accepted_at > processed_at:
            raise ValidationError("반복 창의 인정 시각이 서버 처리 시각보다 이후입니다.")

    if not measurement_available or delivery.is_test:
        result = "MEASUREMENT_UNAVAILABLE"
    elif event.occurred_at > received_at:
        result = "DELIVERY_INVALID"
    elif received_at - event.occurred_at > MAX_RECEIVE_DELAY:
        result = "LATE_EVENT"
    elif (
        not delivery_valid
        or not occurrence_eligible
        or event.occurred_at < delivery.issued_at
        or (
            delivery.display_expires_at is not None
            and event.occurred_at >= delivery.display_expires_at
        )
        or not delivery.starts_at <= event.occurred_at < delivery.ends_at
        or (delivery.stopped_at is not None and event.occurred_at >= delivery.stopped_at)
    ):
        result = "DELIVERY_INVALID"
    elif delivery_type_consumed:
        result = "DELIVERY_DUPLICATE"
    elif (
        last_accepted_at is not None
        and processed_at - last_accepted_at < REPEAT_WINDOWS[event.event_type]
    ):
        result = "REPEAT_SUPPRESSED"
    else:
        result = "COUNTED"

    counted = result == "COUNTED"
    accepted_at = processed_at if counted else None
    try:
        metric_date_kst = event.occurred_at.astimezone(KST).date()
    except OverflowError as exc:
        # UTC 최대 날짜의 미래 보고는 제외 응답을 유지하며 집계일을 만들지 않습니다.
        # 실제 인정 항목은 표현 가능한 KST 집계일 없이 저장할 수 없습니다.
        if counted:
            raise ValidationError(
                fields={"occurred_at": "KST 집계일 표현 범위를 벗어났습니다."}
            ) from exc
        metric_date_kst = None
    decision = MeasurementDecision(
        event_id=event.event_id,
        delivery_id=event.delivery_id,
        event_type=event.event_type,
        result=result,
        counted=counted,
        occurred_at=event.occurred_at,
        received_at=received_at,
        processed_at=processed_at,
        accepted_at=accepted_at,
        metric_date_kst=metric_date_kst,
        estimated_tokens=estimate_tokens(delivery.placement, event.event_type, counted=counted),
        ads_policy_version=ads_policy_version,
    )
    return MeasurementOutcome(
        decision,
        False,
        result in {"COUNTED", "REPEAT_SUPPRESSED"},
        accepted_at,
    )
