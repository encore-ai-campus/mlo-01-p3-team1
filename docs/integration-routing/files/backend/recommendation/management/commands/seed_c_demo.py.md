# backend/recommendation/management/commands/seed_c_demo.py 연결 라우팅

- 작성일: 2026-10-18
- 수정일: 2026-10-18
- 담당: Codex / 사용자 승인 통합 정합성 수정
- 브랜치/기준: develop / 160a66c
- [대응 코드](../../../../../../../backend/recommendation/management/commands/seed_c_demo.py)
- [기준·변경 전후·검증·남은 연결](../../../../../../development/통합_정합성_수정_변경_라우팅.md)

## 호출·저장·검증 경계

LOCAL_DEMO에서만 기존 판정기를 적용한 합성64곡을 새 불변 c-demo-v3로 생성합니다. v2와 실제 음악 자료는 덮어쓰지 않습니다. 기존버전 내용 충돌은 CommandError입니다.

## AST 시그니처

```python
class Command(BaseCommand)
Command.handle(self, *args, **options)
```
