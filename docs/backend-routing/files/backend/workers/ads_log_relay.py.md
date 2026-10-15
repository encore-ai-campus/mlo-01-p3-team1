# backend/workers/ads_log_relay.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../backend/workers/ads_log_relay.py)

`ad_admin_changes.log_relay`의 불변 payload를 공통 PostgreSQL sink에 한 batch 전달합니다. 입력 sink의 호출 형태는 log_event_id/payload/payload_hash이며 True는 durable commit 또는 동일 ID·동일 payload 확인을 의미합니다. 실제 PostgreSQL 테이블/DDL·계정 저장소를 이 모듈이 만들지 않습니다.

`get_log_sink`는 서버 설정 `ADS_LOG_SINK`가 callable인지 먼저 확인합니다. 미설정이면 MongoDB claim 전 LOG_SINK_UNAVAILABLE(503)로 차단합니다. `AdsLogRelay`는 PENDING의 next_retry_at을 claim 기한으로 사용하고 attempt_count를 포함한 조건부 완료로 늦은 worker의 ack를 배제합니다.

실패는 PENDING과 불변 payload/응답을 보존하고 예외 타입만 기록해 재시도합니다. PostgreSQL commit 뒤 MongoDB ack 실패 시 같은 event ID를 다시 전달하므로 sink의 멱등 저장 계약이 필요합니다. 출력은 claimed/sent/failed/stale 개수입니다. claim/retry 기본 간격은 구현 설정이며 운영 주기·보관 정책을 확정한 값이 아닙니다.

## AST 시그니처

```python
class LogSinkRejected(Exception)
get_log_sink()
class AdsLogRelay
AdsLogRelay.__init__(self, collection, sink, *, is_test=True, claim_seconds=30, retry_seconds=30, clock=None)
AdsLogRelay._now(self)
AdsLogRelay._claim(self)
AdsLogRelay._finish(self, document, error=None)
AdsLogRelay.run_once(self, limit=20)
run_configured_relay(limit=20)
```
