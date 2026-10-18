# backend/music/test_occasion_publication.py 연결 라우팅

- 작성일: 2026-10-18
- 수정일: 2026-10-18
- 담당: Codex / 사용자 승인 통합 정합성 수정
- 브랜치/기준: develop / 160a66c
- [대응 코드](../../../../../backend/music/test_occasion_publication.py)
- [기준·변경 전후·검증·남은 연결](../../../../development/통합_정합성_수정_변경_라우팅.md)

## 호출·저장·검증 경계

격리 DB에서 운영 분기 발행과 작업자를 실행합니다. GENERAL3곡/행사1곡/애매1곡 구분, 판정 누락 차단, 일반곡0 발행 실패·이전 snapshot 보존을 검증합니다.

## AST 시그니처

```python
class OccasionPublicationTests(TestCase)
OccasionPublicationTests.setUp(self)
OccasionPublicationTests.test_operating_publication_and_worker_use_general_only(self)
OccasionPublicationTests.test_missing_or_non_general_decision_is_not_eligible_in_either_mode(self)
OccasionPublicationTests.test_no_general_source_cannot_publish_or_mutate_old_snapshots(self)
```
