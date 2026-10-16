# analysis/weather_music_20261016/diagnostics_20261016/profile_analysis.py 라우팅

- 작성일/수정일: 2026-10-16
- 담당: 로컬 음악 재생 통합팀. 기존 분석은 보존 의존성으로만 문서화합니다.
- 기준 브랜치/커밋: feature/ad-logic / f22f974
- 소스: [analysis/weather_music_20261016/diagnostics_20261016/profile_analysis.py](../../../../../../analysis/weather_music_20261016/diagnostics_20261016/profile_analysis.py)
- 범위/목적: 음악 특성의 분포·상관·동점·검토 플래그 진단

## 기준과 입력

원본 CSV와 V2 analyze.py/정책·풀을 읽습니다. describe는 분포, collinearity는 공선성, review_flags는 IQR/MAD 검토 플래그를 계산합니다.

[최신 ON/OFF 후보 계약](../../../../../product/카페_음악_추천_서비스_3차_컬럼_기반_추천_로직_가이드.md)과 [시즌 분리·재생 가이드](../../../../../development/music/YouTube_로컬_재생_기획과_구현_가이드.md)를 연결하며 수령 원문과 기존 원본 음악 열은 바꾸지 않습니다.

## 실제 공급·소비와 검증

기존 profile_*.csv와 profile_summary.json을 생성합니다. flag는 오류 확률이나 자동 삭제·행사곡 확정 조건이 아닙니다.

노트북·표본 생성·기획 보완이 읽습니다. 시즌 필터는 날씨 가중치나 V2 점수를 이 진단으로 바꾸지 않습니다.

근거: [연결 문서/검증 자료](../../../../../../analysis/weather_music_20261016/diagnostics_20261016/profile_summary.json). [정본 차이·남은 연결](../../../../../development/음악_재생_정본_변경_라우팅.md)와 [시즌 필터 검증](../../../../../development/음악_시즌필터_변경_라우팅.md)에서 실제 실행/미실행을 구분합니다.

## AST 심벌

시그니처는 routing-doc-auditor의 구조화 결과를 그대로 사용했습니다. 소스의 함수·클래스 이름/인자/기본값·annotation을 아래와 1:1 대조합니다.

- `digest`: function, 소스 29행
- `dump_csv`: function, 소스 33행
- `describe`: function, 소스 37행
- `collinearity`: function, 소스 46행
- `review_flags`: function, 소스 68행
- `main`: function, 소스 89행

```python
digest(path)
dump_csv(name, frame)
describe(cohort, name, values, categorical=False)
collinearity(cohort, frame)
review_flags(base)
main()
```
