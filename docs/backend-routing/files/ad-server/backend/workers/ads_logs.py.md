# ad-server/backend/workers/ads_logs.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../../ad-server/backend/workers/ads_logs.py)

광고 MongoDB 내장 로그의 환경별 신규/기존/누락 건수와 제한 표본의 payload/hash를 읽기 점검합니다. 문서/로그/업무 상태를 변경하지 않습니다.

현행 로그 구조와 이전 자료 보존은 [광고 로그 저장 계약](../../../../../development/ads/MongoDB_광고_로그_저장_계약.md)을 따릅니다.

## AST 시그니처

```python
inspect_logs(database, *, is_test, limit=20)
```
