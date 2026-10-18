# analysis/weather_music_20261016/diagnostics_20261016/build_diagnostics_notebook.py 라우팅

- 작성일/수정일: 2026-10-16
- 담당: 로컬 음악 재생 통합팀. 기존 분석은 보존 의존성으로만 문서화합니다.
- 기준 브랜치/커밋: feature/ad-logic / f22f974
- 소스: [analysis/weather_music_20261016/diagnostics_20261016/build_diagnostics_notebook.py](../../../../../../analysis/weather_music_20261016/diagnostics_20261016/build_diagnostics_notebook.py)
- 범위/목적: 통계 진단 노트북 생성·실행 보조

## 기준과 입력

기존 profile_summary/sensitivity_summary와 V2 summary·원본 CSV를 읽는 notebook 셀을 만듭니다. md/code는 셀 생성 함수입니다.

[최신 ON/OFF 후보 계약](../../../../../product/카페_음악_추천_서비스_3차_컬럼_기반_추천_로직_가이드.md)과 [시즌 분리·재생 가이드](../../../../../development/music/YouTube_로컬_재생_기획과_구현_가이드.md)를 연결하며 수령 원문과 기존 원본 음악 열은 바꾸지 않습니다.

## 실제 공급·소비와 검증

weather_diagnostics.ipynb와 도표 등 진단 자료를 생성하는 기존 오프라인 스크립트입니다. 모듈 최상위 실행이 있어 재생 서버에서 import하지 않습니다.

기획·검수자가 분포/상관/민감도를 검토합니다. 추천 정확도·청취 정답·회귀 학습의 증거로 사용하지 않습니다.

근거: [연결 문서/검증 자료](../../../../../../analysis/weather_music_20261016/diagnostics_20261016/weather_diagnostics.ipynb). [정본 차이·남은 연결](../../../../../development/음악_재생_정본_변경_라우팅.md)와 [시즌 필터 검증](../../../../../development/음악_시즌필터_변경_라우팅.md)에서 실제 실행/미실행을 구분합니다.

## AST 심벌

시그니처는 routing-doc-auditor의 구조화 결과를 그대로 사용했습니다. 소스의 함수·클래스 이름/인자/기본값·annotation을 아래와 1:1 대조합니다.

- `md`: function, 소스 11행
- `code`: function, 소스 13행

```python
md(text)
code(text)
```
