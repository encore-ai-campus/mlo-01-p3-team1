# analysis/weather_music_20261016/archive/v1/analyze.py 라우팅

- 작성일/수정일: 2026-10-16
- 담당: 로컬 음악 재생 통합팀. 기존 분석은 보존 의존성으로만 문서화합니다.
- 기준 브랜치/커밋: feature/ad-logic / f22f974
- 소스: [analysis/weather_music_20261016/archive/v1/analyze.py](../../../../../../../analysis/weather_music_20261016/archive/v1/analyze.py)
- 범위/목적: V1 단일 패턴 분석의 보존 이력

## 기준과 입력

과거 policy.json과 원본 CSV·수령 장르 매핑을 가정한 코드입니다. V1과 V2의 차이를 설명하는 이력이며 일반 운영 후보의 실행 입력으로 사용하지 않습니다.

[최신 ON/OFF 후보 계약](../../../../../../product/카페_음악_추천_서비스_3차_컬럼_기반_추천_로직_가이드.md)과 [시즌 분리·재생 가이드](../../../../../../development/music/YouTube_로컬_재생_기획과_구현_가이드.md)를 연결하며 수령 원문과 기존 원본 음악 열은 바꾸지 않습니다.

## 실제 공급·소비와 검증

이전 분석 재현 의도와 당시 함수 시그니처를 보존합니다. archive 이동으로 상대 ROOT/매핑 경로가 당시와 다를 수 있으므로 현재 위치에서 바로 실행 가능한 코드로 보고하지 않습니다.

현행 V2의 비교 수량은 보관 summary.json을 읽습니다. 이 스크립트를 로컬 서버나 시즌 필터에서 import하지 않습니다.

근거: [연결 문서/검증 자료](../../../../../../../analysis/weather_music_20261016/archive/v1/README.md). [정본 차이·남은 연결](../../../../../../development/음악_재생_정본_변경_라우팅.md)와 [시즌 필터 검증](../../../../../../development/음악_시즌필터_변경_라우팅.md)에서 실제 실행/미실행을 구분합니다.

## AST 심벌

시그니처는 routing-doc-auditor의 구조화 결과를 그대로 사용했습니다. 소스의 함수·클래스 이름/인자/기본값·annotation을 아래와 1:1 대조합니다.

- `sha256`: function, 소스 24행
- `fraction`: function, 소스 28행
- `component_exact`: function, 소스 32행
- `score_exact`: function, 소스 39행
- `score_vector`: function, 소스 46행
- `speed`: function, 소스 58행
- `mapping`: function, 소스 66행
- `stats`: function, 소스 79행
- `exact_subset`: function, 소스 83행
- `example`: function, 소스 120행
- `main`: function, 소스 145행

```python
sha256(path: Path) -> str
fraction(value) -> Fraction
component_exact(value, params) -> Fraction
score_exact(row, params)
score_vector(frame, params)
speed(tempo, signature)
mapping()
stats(frame)
exact_subset(durations, target, block=32)
example(pool, params, policy)
main()
```
