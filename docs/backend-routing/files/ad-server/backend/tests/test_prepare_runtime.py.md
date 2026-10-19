# ad-server/backend/tests/test_prepare_runtime.py 연결 라우팅

- 작성일: 2026-10-18
- 수정일: 2026-10-18
- 담당: Codex / 사용자 승인 통합 정합성 수정
- 브랜치/기준: develop / 160a66c
- [대응 코드](../../../../../../ad-server/backend/tests/test_prepare_runtime.py)
- [기준·변경 전후·검증·남은 연결](../../../../../development/통합_정합성_수정_변경_라우팅.md)

## 호출·저장·검증 경계

모의 Mongo 저장소로 명시 초기화·기존 설정 보존·스키마 불일치 차단과 안전한 준비 상태를 검증합니다. 실환경 초기화나 권한 부여를 수행하지 않습니다.

## AST 시그니처

```python
class PrepareRuntimeTests(SimpleTestCase)
PrepareRuntimeTests.test_configuration_check_never_connects(self)
PrepareRuntimeTests.test_dry_run_does_not_connect(self)
PrepareRuntimeTests.test_conflicting_validator_is_not_modified(self)
PrepareRuntimeTests.test_remote_replica_name_is_configurable(self)
```
