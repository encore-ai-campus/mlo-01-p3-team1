# ad-server/backend/domains/ads/sandbox_runtime.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../../../ad-server/backend/domains/ads/sandbox_runtime.py)

현재 로컬 도구 프로세스의5분 예산/통계 작업과 상태 조회입니다. `require_sandbox`는 sandbox 플래그·is_test=True·정확한 `ads_sandbox_dev` DB명을 검사하고 MongoDB URI의 모든 노드가 loopback인지 확인합니다. 운영 DB·공유 인증이나 별도 durable scheduler를 구현하는 모듈이 아닙니다.

`refresh_policy`는 비차단 batch 잠금으로 같은 프로세스의 중복 갱신을409/SANDBOX_BUSY로 거부하고 기존 `AdsBudgetService.run_once`를 호출합니다. 시작/성공 UTC Z 시각과 실패 클래스명만 기록하며, 예외 메시지/URI/proof는 상태에 보관하지 않습니다. 성공·실패 모두 잠금을 해제합니다.

`start_worker`는 이미 실행 중이면 추가 thread를 만들지 않고 최초1회 검증 후 daemon 작업을 시작합니다. `_loop`는 monotonic 기준300초 간격으로 실행하고 실패 뒤 다음 주기에 재시도합니다. `stop_worker`는 종료 이벤트와 제한 join으로 대기 중인 thread를 중단합니다.

`worker_status`의 running/interval_seconds/last_started_at/last_succeeded_at/last_error는 이 프로세스의 상태입니다. 프로세스 재시작 뒤의 영구 운영 이력이나 PostgreSQL 로그 전달 상태를 대신하지 않습니다.

## AST 시그니처

```python
_stamp()
require_sandbox()
worker_status()
refresh_policy()
_loop()
start_worker()
stop_worker()
```
