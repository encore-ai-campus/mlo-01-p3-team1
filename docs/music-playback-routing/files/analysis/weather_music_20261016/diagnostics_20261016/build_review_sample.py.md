# analysis/weather_music_20261016/diagnostics_20261016/build_review_sample.py 라우팅

- 작성일/수정일: 2026-10-16
- 담당: 로컬 음악 재생 통합팀. 기존 분석은 보존 의존성으로만 문서화합니다.
- 기준 브랜치/커밋: feature/ad-logic / f22f974
- 소스: [analysis/weather_music_20261016/diagnostics_20261016/build_review_sample.py](../../../../../../analysis/weather_music_20261016/diagnostics_20261016/build_review_sample.py)
- 범위/목적: LLM/사람 검수 대상 500곡의 결정적 표본 생성

## 기준과 입력

원본 CSV와 V2/진단 플래그를 읽고 저장된 seed 기반 order_hash로 층별 검토 대상을 선택합니다.

[최신 ON/OFF 후보 계약](../../../../../product/카페_음악_추천_서비스_3차_컬럼_기반_추천_로직_가이드.md)과 [시즌 분리·재생 가이드](../../../../../development/music/YouTube_로컬_재생_기획과_구현_가이드.md)를 연결하며 수령 원문과 기존 원본 음악 열은 바꾸지 않습니다.

## 실제 공급·소비와 검증

llm_review_sample.csv와 review_sample_summary.json만 생성하는 기존 코드입니다. LLM 제안/사람 검수 칸은 빈 입력 칸이며 API를 호출하지 않습니다.

PL 또는 향후 별도 검수 작업이 표본을 소비합니다. 이 표본을 행사 분류의 정답으로 사용하거나 source의 mood/genre를 자동 승인하지 않습니다.

근거: [연결 문서/검증 자료](../../../../../../analysis/weather_music_20261016/diagnostics_20261016/review_sample_summary.json). [정본 차이·남은 연결](../../../../../development/음악_재생_정본_변경_라우팅.md)와 [시즌 필터 검증](../../../../../development/음악_시즌필터_변경_라우팅.md)에서 실제 실행/미실행을 구분합니다.

## AST 심벌

시그니처는 routing-doc-auditor의 구조화 결과를 그대로 사용했습니다. 소스의 함수·클래스 이름/인자/기본값·annotation을 아래와 1:1 대조합니다.

- `sha256`: function, 소스 40행
- `order_hash`: function, 소스 44행
- `js`: function, 소스 48행
- `true`: function, 소스 52행
- `main`: function, 소스 57행

```python
sha256(path: Path) -> str
order_hash(namespace: str, value: str) -> str
js(value) -> str
true(value) -> bool
main() -> None
```
