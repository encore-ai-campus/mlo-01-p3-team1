# backend/recommendation/occasion.py 연결 라우팅

- 작성일: 2026-10-18
- 수정일: 2026-10-18
- 담당: Codex / 사용자 승인 통합 정합성 수정
- 브랜치/기준: develop / 160a66c
- [대응 코드](../../../../../backend/recommendation/occasion.py)
- [기준·변경 전후·검증·남은 연결](../../../../development/통합_정합성_수정_변경_라우팅.md)

## 호출·저장·검증 경계

기존 로컬 판정 manifest/CSV 해시 검증을 유지합니다. 새 general_eligible은 발행과 공통 후보의 동일 판정 경계이며 GENERAL·출처·비어 있지 않은 두 버전을 검사합니다. 수령 자료/과거 snapshot은 수정하지 않습니다.

## AST 시그니처

```python
general_eligible(track)
load_occasion_decisions(directory, source_sha256)
```
