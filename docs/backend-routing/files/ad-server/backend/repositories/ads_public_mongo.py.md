# ad-server/backend/repositories/ads_public_mongo.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../../ad-server/backend/repositories/ads_public_mongo.py)

기존 MongoAdsRepository의 snapshot/majority/primary 트랜잭션을 상속하여 공개 추가 다섯 컬렉션을 연결합니다. 모든 조회는 is_test 범위를 적용하고 공개 쓰기는 run 콜백에서만 허용합니다.

신규 delivery는 위치별 순환 revision CAS와 함께 기록합니다. 광고 자체의 실제 쓰기/복원을 이용한 lock_ad로 관리 변경과 공개 제공/측정의 경합을 직렬화합니다. historical_ad는 관리 감사 occurred_at·version_after 역순의 after_snapshot에서 당시 게시 상태를 읽습니다.

delivery/type claim은 미소비 조건부 갱신이며 인정/반복 억제만 소비합니다. 반복 창은 검증된 owner/ad/placement/type와 환경별 키를 해시하고 revision을 비교합니다. 이벤트·예상 원장 고유키와 상태 초기화 경합은 새 트랜잭션에서 재조회하며 driver의 transient/commit 재시도 라벨은 보존합니다. 사용/수신 시각은 $max로 역행을 막습니다.

이 저장소는 사용자 마스터·일별 통계·예산 금액·TTL 정리·외부 PostgreSQL 쓰기를 구현하지 않습니다. manifest 적용은 별도 로컬 명령이며 실제 운영 연결을 의미하지 않습니다.

현행 로그 구조와 이전 자료 보존은 [광고 로그 저장 계약](../../../../../development/ads/MongoDB_광고_로그_저장_계약.md)을 따릅니다.

## AST 시그니처

```python
_state_id(*parts) -> str
_event_type(event_type: str) -> None
class MongoPublicAdsRepository(MongoAdsRepository)
MongoPublicAdsRepository.list_candidates(self, placement: str, now: datetime) -> list[Document]
MongoPublicAdsRepository.get_rotation(self, placement: str) -> Document | None
MongoPublicAdsRepository.advance_rotation(self, placement: str, expected_revision: int | None, last_ad_id: str, now: datetime) -> None
MongoPublicAdsRepository.get_delivery(self, delivery_id: str) -> Document | None
MongoPublicAdsRepository.get_delivery_request(self, owner_guest_id: str | None, placement: str, key_hash: str) -> Document | None
MongoPublicAdsRepository.insert_delivery(self, document: Document) -> None
MongoPublicAdsRepository.lock_ad(self, ad: Document) -> None
MongoPublicAdsRepository.historical_ad(self, ad_id: str, occurred_at: datetime) -> Document | None
MongoPublicAdsRepository.get_event(self, event_id: str) -> Document | None
MongoPublicAdsRepository.insert_event(self, document: Document) -> None
MongoPublicAdsRepository.get_repeat_window(self, owner_guest_id: str, ad_id: str, placement: str, event_type: str) -> Document | None
MongoPublicAdsRepository.advance_repeat_window(self, owner_guest_id: str, ad_id: str, placement: str, event_type: str, expected_revision: int | None, accepted_at: datetime) -> None
MongoPublicAdsRepository.claim_delivery_type(self, delivery_id: str, event_type: str, event_id: str, result: str, processed_at: datetime) -> None
MongoPublicAdsRepository.touch_delivery(self, delivery_id: str, received_at: datetime | None, *, used_at: datetime | None=None) -> None
MongoPublicAdsRepository.insert_usage_entry(self, document: Document) -> None
MongoPublicAdsRepository._get(self, collection: str, query: Document) -> Document | None
MongoPublicAdsRepository._insert(self, collection: str, document: Document) -> None
MongoPublicAdsRepository._advance_state(self, collection: str, identity: Document, expected_revision: int | None, values: Document) -> None
_configured_public_repository(uri: str, database: str, is_test: bool) -> MongoPublicAdsRepository
get_public_ads_repository() -> MongoPublicAdsRepository
```
