# scripts/check_routing.py 연결 라우팅

- 작성일: 2026-10-18
- 수정일: 2026-10-18
- 담당: Codex / 사용자 승인 통합 정합성 수정
- 브랜치/기준: develop / 160a66c
- [대응 코드](../../../../scripts/check_routing.py)
- [기준·변경 전후·검증·남은 연결](../../../development/통합_정합성_수정_변경_라우팅.md)

## 호출·저장·검증 경계

config/routing-scopes.json의 광고 전체/이번 통합 파일 범위를 위 AST 검사기로 검사합니다. 담당 밖 파일의 누락은 성공으로 둔갑시키지 않고 범위 밖으로 구분합니다. 선언한 소스가 없어도 실패하며 CI 종료코드로 연결합니다.

## AST 시그니처

```python
check(repo)
main()
```
