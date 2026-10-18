# music_playback/verify.py 라우팅

- 작성일/수정일: 2026-10-16
- 담당: 음악 데이터·시즌 필터 에이전트
- 기준: feature/ad-logic / f22f974

기준·입출력·변경 이유·실제 검증은 [전체 변경 라우팅](../../../음악_시즌필터_변경_라우팅.md)을 확인합니다.

AST 시그니처:

```python
verify_general(source: Path, analysis_dir: Path, output: Path | None=None) -> dict
```
