# analysis/weather_music_20261016/analyze.py 라우팅

- 작성일/수정일: 2026-10-16
- 담당: 로컬 음악 재생 통합팀. 기존 분석은 보존 의존성으로만 문서화합니다.
- 기준 브랜치/커밋: feature/ad-logic / f22f974
- 소스: [analysis/weather_music_20261016/analyze.py](../../../../../analysis/weather_music_20261016/analyze.py)
- 범위/목적: V2 날씨 점수·전체 풀·3시간 분석의 원래 재현 코드

## 기준과 입력

원본 CSV, policy.json, 수령 장르 매핑 사전을 읽습니다. 같은 패턴의 정확 Fraction 점수·핵심 게이트·75점 경계와 5 SUPPORT 영역의 커버리지를 계산합니다.

[최신 ON/OFF 후보 계약](../../../../product/카페_음악_추천_서비스_3차_컬럼_기반_추천_로직_가이드.md)과 [시즌 분리·재생 가이드](../../../../development/music/YouTube_로컬_재생_기획과_구현_가이드.md)를 연결하며 수령 원문과 기존 원본 음악 열은 바꾸지 않습니다.

## 실제 공급·소비와 검증

pools/*.csv, examples/*_180min.csv, summary.json을 생성하는 기존 코드입니다. 이번 시즌 필터는 이 코드와 산출물을 입력으로만 사용하며 재실행해 덮어쓰지 않았습니다.

music_playback/candidates.py가 기존 풀의 모든 열 문자열을 복사합니다. diagnostics의 profile/sensitivity가 원래 점수를 읽고, verify.py가 원래 풀과 일반 풀을 전수 대조합니다.

근거: [연결 문서/검증 자료](../../../../../analysis/weather_music_20261016/summary.json). [정본 차이·남은 연결](../../../../development/음악_재생_정본_변경_라우팅.md)와 [시즌 필터 검증](../../../../development/음악_시즌필터_변경_라우팅.md)에서 실제 실행/미실행을 구분합니다.

## AST 심벌

시그니처는 routing-doc-auditor의 구조화 결과를 그대로 사용했습니다. 소스의 함수·클래스 이름/인자/기본값·annotation을 아래와 1:1 대조합니다.

- `sha256`: function, 소스 24행
- `fraction`: function, 소스 28행
- `component_exact`: function, 소스 32행
- `pattern_params`: function, 소스 38행
- `score_exact`: function, 소스 42행
- `select_exact`: function, 소스 52행
- `score_vector`: function, 소스 70행
- `speed`: function, 소스 81행
- `mapping`: function, 소스 89행
- `stats`: function, 소스 100행
- `exact_subset`: function, 소스 104행
- `make_example`: function, 소스 136행
- `build_pattern`: function, 소스 157행
- `analytic_coverage_checks`: function, 소스 187행
- `fixed_anchor_checks`: function, 소스 209행
- `main`: function, 소스 237행

```python
sha256(path)
fraction(value)
component_exact(value, parameters)
pattern_params(weather, pattern)
score_exact(row, params)
select_exact(row, weather, threshold, core_min)
score_vector(frame, params)
speed(tempo, signature)
mapping()
stats(frame)
exact_subset(durations, target, block=32)
make_example(pool, weather, policy)
build_pattern(base, raw, weather, pattern, thresholds, core_min)
analytic_coverage_checks(policy)
fixed_anchor_checks(policy)
main()
```
