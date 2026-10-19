# ad-server/backend/domains/ads/management/commands/check_ads_configuration.py 연결 라우팅

- 작성일: 2026-10-18
- 수정일: 2026-10-18
- 담당: Codex / 사용자 승인 통합 정합성 수정
- 브랜치/기준: develop / 160a66c
- [대응 코드](../../../../../../../../../ad-server/backend/domains/ads/management/commands/check_ads_configuration.py)
- [기준·변경 전후·검증·남은 연결](../../../../../../../../development/통합_정합성_수정_변경_라우팅.md)

## 호출·저장·검증 경계

운영 준비에 필요한 광고 설정을 외부 접속 없이 점검합니다. 실제 DB/공유 인증 연결 완료와 구분하며 비밀값을 출력하지 않습니다. 세부 입력·결과는 대응 코드와 통합 실행 runbook을 따릅니다.

## AST 시그니처

```python
class Command(BaseCommand)
Command.handle(self, *args, **options)
```
