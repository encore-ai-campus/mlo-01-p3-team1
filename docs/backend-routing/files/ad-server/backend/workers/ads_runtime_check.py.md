# ad-server/backend/workers/ads_runtime_check.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../../ad-server/backend/workers/ads_runtime_check.py)

설정과 MongoDB10컬렉션 validator/인덱스·내장 로그를 읽기 점검합니다. 자동 보정이나 공유 인증 성공을 주장하지 않습니다.

현행 로그 구조와 이전 자료 보존은 [광고 로그 저장 계약](../../../../../development/ads/MongoDB_광고_로그_저장_계약.md)을 따릅니다.

## AST 시그니처

```python
_callable_setting(name)
check_configuration()
expected_collections()
schema_issues(database)
inspect_runtime(*, check_database=False, repository=None, now=None)
```
