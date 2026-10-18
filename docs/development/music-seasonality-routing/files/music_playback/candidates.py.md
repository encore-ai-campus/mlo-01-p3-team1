# music_playback/candidates.py 라우팅

- 작성일/수정일: 2026-10-16
- 담당: 음악 데이터·시즌 필터 에이전트
- 기준: feature/ad-logic / f22f974

기준·입출력·변경 이유·실제 검증은 [전체 변경 라우팅](../../../음악_시즌필터_변경_라우팅.md)을 확인합니다.

AST 시그니처:

```python
sha256(path: Path) -> str
read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]
write_csv(path: Path, fields: list[str], rows: Iterable[dict]) -> None
write_json(path: Path, value) -> None
screen_source(source: Path, source_hash: str, overrides: dict | None=None)
filter_general(rows: list[dict], decisions: dict[str, OccasionDecision]) -> list[dict]
duration_stats(rows: list[dict]) -> dict
_reachable(durations: list[int], limit: int, target: int, block: int=32)
_reconstruct(durations, checkpoints, processed, chosen_total, limit, block=32)
choose_playlist(rows: list[dict], allowed_speeds: list[str], score_field='weather_score_exact', target=TARGET, minimum=MINIMUM, maximum=MAXIMUM)
build(source: Path, analysis_dir: Path, output: Path | None=None, overrides_path: Path | None=None)
```
