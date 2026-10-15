# ad-server/backend/tests/test_ads_policy_api.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../../ad-server/backend/tests/test_ads_policy_api.py)

DRF 실제 요청에 런타임 정책·실제 도메인 서비스·메모리 정책 저장소를 연결합니다. 소진 검증 뒤 광고 숨김·예산 종료 이유·차단 전 보고·최초 응답 재전송과 관리 요약의 주기 물리 집계 연결을 확인합니다.

공통 guest/ADMIN과 로그 sink는 시험 대역입니다. 실제 MongoDB/브라우저 배너와 구분하며 관리자 화면은 구현하지 않습니다.

## AST 시그니처

```python
class AdsPolicyApiTests(SimpleTestCase)
AdsPolicyApiTests.setUp(self)
AdsPolicyApiTests.issue(self)
AdsPolicyApiTests.report(self, ad, kind, occurred_at=None, event_id=None)
AdsPolicyApiTests.test_runtime_http_hides_verified_exhaustion_and_replays_first_response(self)
AdsPolicyApiTests.test_admin_summary_returns_materialized_metrics_without_recalculating_source(self)
```
