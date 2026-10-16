# ad-server/backend/tests/test_ads_logs.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../../ad-server/backend/tests/test_ads_logs.py)

내장 광고 로그의 hash/ID/시각·기존 기록 호환·환경 분리·읽기 전용·명령 실패/비밀값 비노출과 외부 relay 제거를 검사합니다.

현행 로그 구조와 이전 자료 보존은 [광고 로그 저장 계약](../../../../../development/ads/MongoDB_광고_로그_저장_계약.md)을 따릅니다.

## AST 시그니처

```python
local_record()
log_database(documents)
class AdsLogsTests(SimpleTestCase)
AdsLogsTests.test_valid_local_records_are_read_only_and_environment_scoped(self)
AdsLogsTests.test_legacy_pending_is_preserved_without_fake_sent_ack(self)
AdsLogsTests.test_corrupt_hash_id_and_timestamp_are_reported_without_payload(self)
AdsLogsTests.test_invalid_configuration_is_rejected_before_database_access(self)
AdsLogsTests.test_command_uses_only_mongo_and_retired_relay_commands_are_absent(self)
AdsLogsTests.test_command_failure_redacts_database_credentials(self)
AdsLogsTests.test_command_reports_missing_log_with_nonzero_exit(self)
```
