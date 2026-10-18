# music_playback/verify.py 라우팅

- 작성일/수정일: 2026-10-16
- 담당: 로컬 음악 재생 통합팀. 기존 분석은 보존 의존성으로만 문서화합니다.
- 기준 브랜치/커밋: feature/ad-logic / f22f974
- 소스: [music_playback/verify.py](../../../../music_playback/verify.py)
- 범위/목적: 저장된 일반 후보의 독립 검증

## 기준과 입력

원본 SHA·manifest 입력/출력 SHA와 원래/일반 풀·판정표·예시를 새로 읽습니다.

[최신 ON/OFF 후보 계약](../../../product/카페_음악_추천_서비스_3차_컬럼_기반_추천_로직_가이드.md)과 [시즌 분리·재생 가이드](../../../development/music/YouTube_로컬_재생_기획과_구현_가이드.md)를 연결하며 수령 원문과 기존 원본 음악 열은 바꾸지 않습니다.

## 실제 공급·소비와 검증

일반6풀 전체 열 문자열/정렬/판정·5풀 합집합·비눈 교집합·예시 speed/중복/시간/품질 합계를 확인해 general/verification.json에 결과를 씁니다.

CLI verify가 호출합니다. PASS는 분석 CSV의 검산이며 실제 YouTube 재생/청취 검증을 뜻하지 않습니다.

근거: [연결 문서/검증 자료](../../../../analysis/weather_music_20261016/general/verification.json). [정본 차이·남은 연결](../../../development/음악_재생_정본_변경_라우팅.md)와 [시즌 필터 검증](../../../development/음악_시즌필터_변경_라우팅.md)에서 실제 실행/미실행을 구분합니다.

## AST 심벌

시그니처는 routing-doc-auditor의 구조화 결과를 그대로 사용했습니다. 소스의 함수·클래스 이름/인자/기본값·annotation을 아래와 1:1 대조합니다.

- `verify_general`: function, 소스 11행

```python
verify_general(source: Path, analysis_dir: Path, output: Path | None=None) -> dict
```
