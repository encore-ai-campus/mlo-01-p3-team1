# backend/music/catalog.py 연결 라우팅

- 작성일: 2026-10-18
- 수정일: 2026-10-18
- 담당: Codex / 사용자 승인 통합 정합성 수정
- 브랜치/기준: develop / 160a66c
- [대응 코드](../../../../../backend/music/catalog.py)
- [기준·변경 전후·검증·남은 연결](../../../../development/통합_정합성_수정_변경_라우팅.md)

## 호출·저장·검증 경계

승인된 RDB 곡과 활성 승인 태그 → 기존 시즌 판정/출처/버전 → GENERAL만 사전 점수·불변 Catalog. 미판정·행사곡 보류, 같은 버전 덮어쓰기 금지. 원본18개·원점수·기존 결과를 유지합니다.

## AST 시그니처

```python
export_tracks(approved_only=False, source_sha256=None)
publish(version, source_ref, source_sha256, is_test=False)
```
