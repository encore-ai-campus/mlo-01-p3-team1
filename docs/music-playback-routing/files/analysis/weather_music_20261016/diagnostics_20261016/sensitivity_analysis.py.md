# analysis/weather_music_20261016/diagnostics_20261016/sensitivity_analysis.py 라우팅

- 작성일/수정일: 2026-10-16
- 담당: 로컬 음악 재생 통합팀. 기존 분석은 보존 의존성으로만 문서화합니다.
- 기준 브랜치/커밋: feature/ad-logic / f22f974
- 소스: [analysis/weather_music_20261016/diagnostics_20261016/sensitivity_analysis.py](../../../../../../analysis/weather_music_20261016/diagnostics_20261016/sensitivity_analysis.py)
- 범위/목적: 원래 정책을 보존하는 OAT 민감도 분석

## 기준과 입력

V2 원본/점수/패턴·임계값을 읽고 snapshot으로 입력 해시를 고정합니다. curve_component와 rank_top은 비교 시나리오를 계산합니다.

[최신 ON/OFF 후보 계약](../../../../../product/카페_음악_추천_서비스_3차_컬럼_기반_추천_로직_가이드.md)과 [시즌 분리·재생 가이드](../../../../../development/music/YouTube_로컬_재생_기획과_구현_가이드.md)를 연결하며 수령 원문과 기존 원본 음악 열은 바꾸지 않습니다.

## 실제 공급·소비와 검증

sensitivity_*.csv/summary·도표와 baseline_manifest 등 진단 파일을 생성합니다. 비교 곡선은 제안 실험이며 운영 점수에 자동 반영하지 않습니다.

validate_diagnostics.py가 baseline 보존과 계산을 검증합니다. 현재 GENERAL 사전 스크린은 이 실험과 독립입니다.

근거: [연결 문서/검증 자료](../../../../../../analysis/weather_music_20261016/diagnostics_20261016/sensitivity_summary.json). [정본 차이·남은 연결](../../../../../development/음악_재생_정본_변경_라우팅.md)와 [시즌 필터 검증](../../../../../development/음악_시즌필터_변경_라우팅.md)에서 실제 실행/미실행을 구분합니다.

## AST 심벌

시그니처는 routing-doc-auditor의 구조화 결과를 그대로 사용했습니다. 소스의 함수·클래스 이름/인자/기본값·annotation을 아래와 1:1 대조합니다.

- `digest`: function, 소스 34행
- `frac`: function, 소스 38행
- `snapshot`: function, 소스 42행
- `load`: function, 소스 49행
- `curve_component`: function, 소스 72행
- `rank_top`: function, 소스 82행
- `run`: function, 소스 92행
- `plot`: function, 소스 291행

```python
digest(path)
frac(value)
snapshot()
load()
curve_component(q, curve, parameter)
rank_top(ids, scores, mask, k=200)
run()
plot(frame, overview)
```
