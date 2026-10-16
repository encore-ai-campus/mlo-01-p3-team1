# ad-server/backend/tests/public_fixtures.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../../ad-server/backend/tests/public_fixtures.py)

공개 도메인 검증용 메모리 저장소와 명시 fixture 정책입니다. 관리/소재/감사·순환/배달/판정/반복/원장의8종 상태를 잠금으로 직렬 처리하고 실패 시 전체 snapshot으로 되돌립니다. 실제 MongoDB 트랜잭션/validator 검증을 대신하지 않습니다.

fixture_public_policy의900초·예산 허용·소재 버전 일치는 테스트 선택값입니다. 운영 정책 provider나 기본값으로 연결하지 않습니다. 저장 실패·고유키/CAS 경합·최초 응답 불변성을 재현하는 데만 사용합니다.

## AST 시그니처

```python
class MemoryPublicRepository(MemoryRepository)
MemoryPublicRepository.__init__(self, *, is_test=False)
MemoryPublicRepository.is_test(self)
MemoryPublicRepository.snapshot(self)
MemoryPublicRepository.run(self, callback)
MemoryPublicRepository.list_candidates(self, placement, now)
MemoryPublicRepository.get_rotation(self, placement)
MemoryPublicRepository.advance_rotation(self, placement, expected_revision, last_ad_id, now)
MemoryPublicRepository.get_delivery(self, delivery_id)
MemoryPublicRepository.get_delivery_request(self, owner_guest_id, placement, key_hash)
MemoryPublicRepository.insert_delivery(self, document)
MemoryPublicRepository.lock_ad(self, ad)
MemoryPublicRepository.historical_ad(self, ad_id, occurred_at)
MemoryPublicRepository.get_event(self, event_id)
MemoryPublicRepository.insert_event(self, document)
MemoryPublicRepository.get_repeat_window(self, owner, ad_id, placement, event_type)
MemoryPublicRepository.advance_repeat_window(self, owner, ad_id, placement, event_type, expected_revision, accepted_at)
MemoryPublicRepository.claim_delivery_type(self, delivery_id, event_type, event_id, result, processed_at)
MemoryPublicRepository.touch_delivery(self, delivery_id, received_at=None, *, used_at=None)
MemoryPublicRepository.insert_usage_entry(self, document)
fixture_public_policy(*, budget_eligible=None)
```
