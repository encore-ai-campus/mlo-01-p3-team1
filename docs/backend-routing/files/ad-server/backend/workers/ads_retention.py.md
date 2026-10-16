# ad-server/backend/workers/ads_retention.py

- 작성일: 2026-10-16
- 수정일: 2026-10-16
- [원본 코드](../../../../../../ad-server/backend/workers/ads_retention.py)

확정된90/365일 보관 기산점과 참조를 읽기 점검합니다. 기간 도래는 REVIEW_DUE 재검토 대상이며 삭제 허용이 아닙니다. UTC/KST 날짜·잘못된 기준·미정 무변경/asset/예산 이력·표본 한계와 환경을 구분합니다. payload·이미지·사용자/접속 원문을 읽어 출력하지 않으며 데이터와 인덱스에 쓰지 않습니다.

[실행/검증 범위](../../../../../runbook/광고_보관_점검과_배치_종료.md)

## AST 시그니처

```python
retention_state(collection, document, *, now)
reference_observations(database, collection, document, *, is_test, now)
inspect_retention(database, *, is_test, limit=100, now=None)
```
