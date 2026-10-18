# backend/common/history_api.py 연결 라우팅

- 작성일: 2026-10-18
- 수정일: 2026-10-18
- 담당: Codex / 사용자 승인 통합 정합성 수정
- 브랜치/기준: develop / 160a66c
- [대응 코드](../../../../../backend/common/history_api.py)
- [기준·변경 전후·검증·남은 연결](../../../../development/통합_정합성_수정_변경_라우팅.md)

## 호출·저장·검증 경계

관리 권한/기간/as_of·페이지 커서는 유지합니다. 목록의 latest_action과 상세 현재 상태는 payload.revision 우선으로 계산하고 시각/UUID를 동점키로 사용합니다. 원래 사건 목록 순서·불변 이벤트/outbox를 바꾸지 않습니다.

## AST 시그니처

```python
view(event, latest=None)
class History(Endpoint)
History.get(self, request)
class HistoryDetail(Endpoint)
HistoryDetail.get(self, request, event_id)
class Metrics(Endpoint)
Metrics.get(self, request)
```
