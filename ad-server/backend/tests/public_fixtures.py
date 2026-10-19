"""공개 광고의 원자성 검증 fixture입니다. 운영 정책·DB 연결을 제공하지 않습니다."""

from copy import deepcopy
from threading import RLock

from domains.ads.errors import DatabaseUnavailable
from domains.ads.public_policy import AdsPublicPolicy
from repositories.ads_mongo import DuplicateMutation
from tests.test_ads_domain import MemoryRepository


class MemoryPublicRepository(MemoryRepository):
    """8종 상태를 직렬 처리·되돌리는 테스트 저장소이며 실제 MongoDB가 아닙니다."""

    STATE_NAMES = (
        "ads",
        "assets",
        "mutations",
        "rotations",
        "deliveries",
        "events",
        "windows",
        "usage",
    )

    def __init__(self, *, is_test=False):
        super().__init__()
        self._is_test = is_test
        self.rotations = {}
        self.deliveries = {}
        self.events = {}
        self.windows = {}
        self.usage = {}
        self.fail_delivery = False
        self.fail_event = False
        self.fail_usage = False
        self._lock = RLock()

    @property
    def is_test(self):
        return self._is_test

    def snapshot(self):
        return deepcopy({name: getattr(self, name) for name in self.STATE_NAMES})

    def run(self, callback):
        with self._lock:
            before = self.snapshot()
            try:
                return callback(self)
            except Exception:
                for name, state in before.items():
                    setattr(self, name, state)
                raise

    def list_candidates(self, placement, now):
        return deepcopy(
            [
                ad
                for ad in self.ads.values()
                if ad["is_test"] is self._is_test
                and ad["placement"] == placement
                and not ad["paused"]
                and ad["starts_at"] <= now < ad["ends_at"]
            ]
        )

    def get_rotation(self, placement):
        return deepcopy(self.rotations.get(placement))

    def advance_rotation(self, placement, expected_revision, last_ad_id, now):
        current = self.rotations.get(placement)
        if (current["revision"] if current else None) != expected_revision:
            raise DuplicateMutation
        self.rotations[placement] = {
            "placement": placement,
            "last_ad_id": last_ad_id,
            "revision": (expected_revision or 0) + 1,
            "updated_at": now,
        }

    def get_delivery(self, delivery_id):
        return deepcopy(self.deliveries.get(delivery_id))

    def get_delivery_request(self, owner_guest_id, placement, key_hash):
        return next(
            (
                deepcopy(item)
                for item in self.deliveries.values()
                if (item["owner_guest_id"], item["placement"], item["request_key_hash"])
                == (owner_guest_id, placement, key_hash)
            ),
            None,
        )

    def insert_delivery(self, document):
        if self.fail_delivery:
            raise DatabaseUnavailable("배달 저장 실패 fixture")
        if document["_id"] in self.deliveries:
            raise DuplicateMutation
        if (
            document["request_key_hash"] is not None
            and self.get_delivery_request(
                document["owner_guest_id"], document["placement"], document["request_key_hash"]
            )
            is not None
        ):
            raise DuplicateMutation
        self.deliveries[document["_id"]] = deepcopy(document)

    def lock_ad(self, ad):
        current = self.ads.get(ad["_id"])
        if current is None or current["version"] != ad["version"]:
            raise DuplicateMutation

    def historical_ad(self, ad_id, occurred_at):
        records = [
            record
            for record in self.mutations.values()
            if record["ad_id"] == ad_id
            and record["operation"] in {"CREATE", "UPDATE", "STOP"}
            and record["occurred_at"] <= occurred_at
        ]
        if not records:
            return None
        latest = max(records, key=lambda item: (item["occurred_at"], item["version_after"]))
        return deepcopy(latest["after_snapshot"])

    def get_event(self, event_id):
        return deepcopy(self.events.get(event_id))

    def insert_event(self, document):
        if self.fail_event:
            raise DatabaseUnavailable("판정 저장 실패 fixture")
        if document["_id"] in self.events:
            raise DuplicateMutation
        self.events[document["_id"]] = deepcopy(document)

    def get_repeat_window(self, owner, ad_id, placement, event_type):
        return deepcopy(self.windows.get((owner, ad_id, placement, event_type)))

    def advance_repeat_window(
        self, owner, ad_id, placement, event_type, expected_revision, accepted_at
    ):
        key = owner, ad_id, placement, event_type
        current = self.windows.get(key)
        if (current["revision"] if current else None) != expected_revision:
            raise DuplicateMutation
        self.windows[key] = {
            "owner_guest_id": owner,
            "ad_id": ad_id,
            "placement": placement,
            "event_type": event_type,
            "revision": (expected_revision or 0) + 1,
            "accepted_at": accepted_at,
        }

    def claim_delivery_type(self, delivery_id, event_type, event_id, result, processed_at):
        claims = self.deliveries[delivery_id]["claims"]
        if event_type in claims:
            raise DuplicateMutation
        claims[event_type] = {"event_id": event_id, "result": result, "processed_at": processed_at}

    def touch_delivery(self, delivery_id, received_at=None, *, used_at=None):
        current = self.deliveries[delivery_id]
        for field, value in (("last_received_at", received_at), ("last_used_at", used_at)):
            if value is not None and (current[field] is None or current[field] < value):
                current[field] = value

    def insert_usage_entry(self, document):
        if self.fail_usage:
            raise DatabaseUnavailable("예상 원장 저장 실패 fixture")
        if document["_id"] in self.usage:
            raise DuplicateMutation
        self.usage[document["_id"]] = deepcopy(document)


def fixture_public_policy(*, budget_eligible=None):
    """900초·소재 일치는 이 테스트의 선택값이며 운영 결정으로 사용하지 않습니다."""
    return AdsPublicPolicy(
        version="FIXTURE/public/v1",
        delivery_ttl_seconds=900,
        budget_eligible=budget_eligible or (lambda repository, ad, now: True),
        open_delivery_eligible=lambda delivery, current_ad, now: (
            delivery["creative_version"] == current_ad["creative_version"]
        ),
        occurrence_eligible=lambda delivery, historical_ad, occurred_at: (
            delivery["creative_version"] == historical_ad["creative_version"]
        ),
    )
