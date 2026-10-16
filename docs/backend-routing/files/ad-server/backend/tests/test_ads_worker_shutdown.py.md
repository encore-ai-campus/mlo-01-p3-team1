# ad-server/backend/tests/test_ads_worker_shutdown.py

- 작성일: 2026-10-16
- 수정일: 2026-10-16
- [원본 코드](../../../../../../ad-server/backend/tests/test_ads_worker_shutdown.py)

watch의 SIGTERM 요청·KeyboardInterrupt·시작/종료 실패·핸들러 복원·비메인 스레드 경계를 검증합니다. 신호 등록/요청 대역을 사용하며 실제 Linux OS 신호 전송 시험은 아닙니다.

[실행/검증 범위](../../../../../runbook/광고_보관_점검과_배치_종료.md)

## AST 시그니처

```python
class AdsWorkerShutdownTests(SimpleTestCase)
AdsWorkerShutdownTests.command(self)
AdsWorkerShutdownTests.group(self)
AdsWorkerShutdownTests.test_sigterm_requests_stop_and_restores_previous_handler(self)
AdsWorkerShutdownTests.test_keyboard_interrupt_stops_group_and_restores_handler(self)
AdsWorkerShutdownTests.test_failed_shutdown_is_reported_and_handler_still_restored(self)
AdsWorkerShutdownTests.test_nonmain_thread_does_not_register_process_signal_handlers(self)
AdsWorkerShutdownTests.test_start_failure_still_stops_and_restores_handler(self)
```
