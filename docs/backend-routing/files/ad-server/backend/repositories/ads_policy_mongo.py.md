# ad-server/backend/repositories/ads_policy_mongo.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../../ad-server/backend/repositories/ads_policy_mongo.py)

공개 저장 어댑터를 상속한 예산/주기 집계 추가2컬렉션 저장소입니다. 모든 참조와 조회는 is_test 환경을 분리하고 쓰기는 snapshot 트랜잭션 안에서만 허용합니다. ad_budget_states의 키는 광고·불투명 예산 버전·YYYY-MM-DD 발생일·환경이며 revision CAS로 갱신합니다. 전체 cutoff는 같은 예산 버전의 모든 날짜에서 최초 시각을 읽어 자정에 잃지 않습니다.

usage_rows는 ESTIMATED 원장만 발생일KST/위치별 합산합니다. replace_daily_metrics는 해당 고유 행을 교체하여 재실행 중복 합산을 막고 원장/event를 변경하지 않습니다. 정수는 BSON Int64를 허용하고 bool·음수·중복 그룹은 거절합니다.

metrics_summary는 오늘/보관 범위 누적 수치·as_of·READY/PARTIAL/PENDING·광고/위치 coverage·coverage_from/through·is_stale를 반환합니다. 미연결 null과 실제0을 구분하고 보관 범위를 영구 누적으로 설명하지 않습니다. 현재 광고 잠금과 정책/집계 트랜잭션의 조율은 업무 서비스가 수행합니다. 실제 배포·PostgreSQL 로그 쓰기·TTL 삭제는 수행하지 않습니다.

현행 로그 구조와 이전 자료 보존은 [광고 로그 저장 계약](../../../../../development/ads/MongoDB_광고_로그_저장_계약.md)을 따릅니다.

## AST 시그니처

```python
_reference(value, field)
_day(value)
_integer(value, minimum=0)
class MongoAdsPolicyRepository(MongoPublicAdsRepository)
MongoAdsPolicyRepository.budget_state_id(self, ad_id: str, budget_version: str, metric_date_kst: str) -> str
MongoAdsPolicyRepository.list_policy_ads(self) -> list[Document]
MongoAdsPolicyRepository.usage_rows(self, ad_id: str) -> list[Document]
MongoAdsPolicyRepository.get_budget_state(self, ad_id: str, budget_version: str, metric_date_kst: str) -> Document | None
MongoAdsPolicyRepository.latest_budget_state(self, ad_id: str, budget_version: str) -> Document | None
MongoAdsPolicyRepository.total_budget_cutoff(self, ad_id: str, budget_version: str) -> datetime | None
MongoAdsPolicyRepository.save_budget_state(self, document: Document, expected_revision: int | None) -> None
MongoAdsPolicyRepository.replace_daily_metrics(self, ad_id: str, rows: list[Document], as_of: datetime) -> None
MongoAdsPolicyRepository.metrics_summary(self, now: datetime, ad_id: str | None=None) -> Document
_configured_policy_repository(uri: str, database: str, is_test: bool) -> MongoAdsPolicyRepository
get_ads_policy_repository() -> MongoAdsPolicyRepository
```
