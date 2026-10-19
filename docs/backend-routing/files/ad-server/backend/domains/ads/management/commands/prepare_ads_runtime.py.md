# ad-server/backend/domains/ads/management/commands/prepare_ads_runtime.py 연결 라우팅

- 작성일: 2026-10-18
- 수정일: 2026-10-18
- 담당: Codex / 사용자 승인 통합 정합성 수정
- 브랜치/기준: develop / 160a66c
- [대응 코드](../../../../../../../../../ad-server/backend/domains/ads/management/commands/prepare_ads_runtime.py)
- [기준·변경 전후·검증·남은 연결](../../../../../../../../development/통합_정합성_수정_변경_라우팅.md)

## 호출·저장·검증 경계

기본은 초기화 계획만 출력합니다. --apply에서 명시 Mongo URI/논리 DB·writable replica primary를 확인하고 누락 컬렉션/인덱스를 준비합니다. 기존 validator 충돌을 덮지 않고 실제 운영 적용은 운영자 절차로 남깁니다.

## AST 시그니처

```python
prepare(database, definitions)
class Command(BaseCommand)
Command.add_arguments(self, parser)
Command.handle(self, *args, **options)
```
