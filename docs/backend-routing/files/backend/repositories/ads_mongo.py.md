# backend/repositories/ads_mongo.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../backend/repositories/ads_mongo.py)

광고 3컬렉션의 실제 MongoDB 저장 어댑터입니다. API 설정의 replica set URI를 사용하며 로컬 점검 명령 전용 loopback 제한과 구분합니다. primary를 확인하고 test/운영 레코드의 is_test 범위를 분리합니다.

서비스 callback 하나를 snapshot read concern·majority write concern·primary 트랜잭션으로 실행합니다. 트랜잭션 밖의 쓰기는 차단하며 driver의 transient/unknown-commit 재시도를 보존합니다. 멱등 고유키 경합은 새 트랜잭션으로 재조회하고 다른 unique 오류는 성공으로 취급하지 않습니다.

수정은 expected version과 test 범위로 조건부 교체합니다. 동일 문서의 no-op도 실제 쓰기와 복원을 같은 트랜잭션에서 수행해 동시 수정 충돌을 검출하면서 최종 version/updated_at을 유지합니다. 조회는 분리된 사본, 목록은 updated_at/id 내림차순 커서와 has_more, 요약은 실제 상태별 개수를 반환합니다. 공개 배달·측정·집계 저장은 없습니다. 비연결/driver 실패는 DatabaseUnavailable로 전달합니다.

## AST 시그니처

```python
class DuplicateMutation(Exception)
_status_filter(status: str | None, now: datetime) -> Document
class MongoAdsRepository
MongoAdsRepository.__init__(self, client=None, database_name=None, *, is_test=None, session=None)
MongoAdsRepository._require_primary(self) -> None
MongoAdsRepository.database(self)
MongoAdsRepository.is_test(self) -> bool
MongoAdsRepository.run(self, callback: Callable[['MongoAdsRepository'], Result]) -> Result
MongoAdsRepository._read(self, operation: Callable[[], Result]) -> Result
MongoAdsRepository._require_transaction(self) -> None
MongoAdsRepository.get_mutation(self, identity_source: str, actor_account_id: str, operation: str, resource_scope: str, idempotency_key_hash: str) -> Document | None
MongoAdsRepository.get_ad(self, ad_id: str) -> Document | None
MongoAdsRepository.get_asset(self, asset_id: str) -> Document | None
MongoAdsRepository.insert_asset(self, document: Document) -> None
MongoAdsRepository.insert_ad(self, document: Document) -> None
MongoAdsRepository.replace_ad(self, ad_id: str, expected_version: int, document: Document) -> bool
MongoAdsRepository.insert_mutation(self, document: Document) -> None
MongoAdsRepository.list_ads(self, *, placement: str | None=None, status: str | None=None, now: datetime | None=None, limit: int=20, cursor: CursorPosition | None=None) -> tuple[list[Document], bool]
MongoAdsRepository.summary(self, now: datetime) -> dict[str, int]
_configured_repository(uri: str, database: str, is_test: bool) -> MongoAdsRepository
get_ads_repository() -> MongoAdsRepository
```
