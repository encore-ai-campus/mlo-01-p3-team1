# analysis/weather_music_20261016/diagnostics_20261016/validate_diagnostics.py 라우팅

- 작성일/수정일: 2026-10-16
- 담당: 로컬 음악 재생 통합팀. 기존 분석은 보존 의존성으로만 문서화합니다.
- 기준 브랜치/커밋: feature/ad-logic / f22f974
- 소스: [analysis/weather_music_20261016/diagnostics_20261016/validate_diagnostics.py](../../../../../../analysis/weather_music_20261016/diagnostics_20261016/validate_diagnostics.py)
- 범위/목적: 통계 진단의 독립 원본·계산 대조

## 기준과 입력

baseline/profile/sensitivity manifest와 원본 CSV·V2 풀을 다시 읽어 분포·상관·VIF·IQR/MAD·경계 계산을 검산합니다.

[최신 ON/OFF 후보 계약](../../../../../product/카페_음악_추천_서비스_3차_컬럼_기반_추천_로직_가이드.md)과 [시즌 분리·재생 가이드](../../../../../development/music/YouTube_로컬_재생_기획과_구현_가이드.md)를 연결하며 수령 원문과 기존 원본 음악 열은 바꾸지 않습니다.

## 실제 공급·소비와 검증

기존 진단 verification.json과 결과 검증 자료를 남깁니다. 최상위 코드가 실행되므로 서버 의존성으로 import하지 않습니다.

이는 기존 통계 진단 검증입니다. 새 시즌 필터의 검증은 music_playback/verify.py와 general/verification.json으로 따로 구분합니다.

근거: [연결 문서/검증 자료](../../../../../../analysis/weather_music_20261016/diagnostics_20261016/verification.json). [정본 차이·남은 연결](../../../../../development/음악_재생_정본_변경_라우팅.md)와 [시즌 필터 검증](../../../../../development/음악_시즌필터_변경_라우팅.md)에서 실제 실행/미실행을 구분합니다.

## AST 심벌

시그니처는 routing-doc-auditor의 구조화 결과를 그대로 사용했습니다. 소스의 함수·클래스 이름/인자/기본값·annotation을 아래와 1:1 대조합니다.

- `sha`: function, 소스 11행
- `read`: function, 소스 12행
- `component`: function, 소스 50행 / decorator lru_cache(None)

```python
sha(p)
read(p)
component(pid, name, x)
```
