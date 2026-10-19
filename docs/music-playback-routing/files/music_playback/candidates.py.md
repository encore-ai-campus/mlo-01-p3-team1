# music_playback/candidates.py 라우팅

- 작성일/수정일: 2026-10-16
- 담당: 로컬 음악 재생 통합팀. 기존 분석은 보존 의존성으로만 문서화합니다.
- 기준 브랜치/커밋: feature/ad-logic / f22f974
- 소스: [music_playback/candidates.py](../../../../music_playback/candidates.py)
- 범위/목적: 일반 운영 후보와 3시간 예시 생성

## 기준과 입력

원본 SHA와 기존 V2 출처를 검사하고 source의 고유 곡을 스크린합니다. 기존 풀의 점수·패턴 등 모든 열을 그대로 읽습니다.

[최신 ON/OFF 후보 계약](../../../product/카페_음악_추천_서비스_3차_컬럼_기반_추천_로직_가이드.md)과 [시즌 분리·재생 가이드](../../../development/music/YouTube_로컬_재생_기획과_구현_가이드.md)를 연결하며 수령 원문과 기존 원본 음악 열은 바꾸지 않습니다.

## 실제 공급·소비와 검증

general/occasion_decisions.csv·occasion_review.csv·pools·examples·summary·manifest를 생성합니다. GENERAL만 남기고 정수 부분집합으로 176~184분을 탐색하며 보류 복귀/단축을 금지합니다.

YouTube PlaylistStore가 examples를 읽습니다. verify_general이 원래 열 문자열·점수·합집합/교집합과 해시를 독립 대조합니다.

근거: [연결 문서/검증 자료](../../../../analysis/weather_music_20261016/general/summary.json). [정본 차이·남은 연결](../../../development/음악_재생_정본_변경_라우팅.md)와 [시즌 필터 검증](../../../development/음악_시즌필터_변경_라우팅.md)에서 실제 실행/미실행을 구분합니다.

## AST 심벌

시그니처는 routing-doc-auditor의 구조화 결과를 그대로 사용했습니다. 소스의 함수·클래스 이름/인자/기본값·annotation을 아래와 1:1 대조합니다.

- `sha256`: function, 소스 21행
- `read_csv`: function, 소스 29행
- `write_csv`: function, 소스 37행
- `write_json`: function, 소스 45행
- `screen_source`: function, 소스 49행
- `filter_general`: function, 소스 67행
- `duration_stats`: function, 소스 84행
- `_reachable`: function, 소스 89행
- `_reconstruct`: function, 소스 103행
- `choose_playlist`: function, 소스 126행
- `build`: function, 소스 180행

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
