# backend/common/test_exclusion_history.py 연결 라우팅

- 작성일: 2026-10-18
- 수정일: 2026-10-18
- 담당: Codex / 사용자 승인 통합 정합성 수정
- 브랜치/기준: develop / 160a66c
- [대응 코드](../../../../../backend/common/test_exclusion_history.py)
- [기준·변경 전후·검증·남은 연결](../../../../development/통합_정합성_수정_변경_라우팅.md)

## 호출·저장·검증 경계

서로 반대 UUID·같은 시각의 제외 revision1/취소2에서 목록/상세/상태 필터를 검증합니다. 시계 역행에도 높은 revision이 우선하며 as_of 밖의 사건은 과거 조회에 들어가지 않습니다.

## AST 시그니처

```python
class ExclusionHistoryRevisionTests(TestCase)
ExclusionHistoryRevisionTests.setUp(self)
ExclusionHistoryRevisionTests.event(self, event_id, kind, revision, at)
ExclusionHistoryRevisionTests.test_equal_timestamps_show_cancellation_and_filter_by_revision(self)
ExclusionHistoryRevisionTests.test_current_revision_wins_over_clock_order_and_as_of_preserves_history(self)
```
