# backend/recommendation/management/commands/check_recommendations.py 라우팅

- 작성일/수정일: 2026-10-19
- 담당: Codex / 추천 요청 분산 실행
- 범위: R-05·Q-02, develop@c7917ce 이후 변경
- 상세 기준→실제 호출/저장→검증·인계: `docs/development/추천_분산처리_변경_라우팅.md`
- 실제 실행 설정·권한·종료/복구: `docs/runbook/추천_분산처리_인프라_인계.md`

## AST 시그니처

```python
snapshot()
class Command(BaseCommand)
Command.add_arguments(self, parser)
Command.handle(self, *args, **options)
```
