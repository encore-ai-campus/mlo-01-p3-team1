# music_playback/seasonality.py 라우팅

- 작성일/수정일: 2026-10-16
- 담당: 로컬 음악 재생 통합팀. 기존 분석은 보존 의존성으로만 문서화합니다.
- 기준 브랜치/커밋: feature/ad-logic / f22f974
- 소스: [music_playback/seasonality.py](../../../../music_playback/seasonality.py)
- 범위/목적: 별도 행사 상태·근거·버전 판정

## 기준과 입력

track_id와 곡명/앨범명/아티스트를 읽습니다. 명백한 행사 구절·고정 제목+아티스트 규칙, 다의 캐럴/앨범 단독, 누락/충돌을 구분합니다.

[최신 ON/OFF 후보 계약](../../../product/카페_음악_추천_서비스_3차_컬럼_기반_추천_로직_가이드.md)과 [시즌 분리·재생 가이드](../../../development/music/YouTube_로컬_재생_기획과_구현_가이드.md)를 연결하며 수령 원문과 기존 원본 음악 열은 바꾸지 않습니다.

## 실제 공급·소비와 검증

OccasionDecision이 GENERAL/SEASONAL_EVENT/REVIEW_REQUIRED/UNSCREENED와 출처/근거/정책·판정 SHA를 제공합니다. Snow/Winter/Holiday·인명 단독은 제외하지 않습니다.

candidates가 GENERAL만 통과시키며 재생 서버는 이 상태를 보존합니다. GENERAL RULE_SCREEN은 사람 청취·운영 READY 확정이 아닙니다.

근거: [연결 문서/검증 자료](../../../development/음악_시즌필터_변경_라우팅.md). [정본 차이·남은 연결](../../../development/음악_재생_정본_변경_라우팅.md)와 [시즌 필터 검증](../../../development/음악_시즌필터_변경_라우팅.md)에서 실제 실행/미실행을 구분합니다.

## AST 심벌

시그니처는 routing-doc-auditor의 구조화 결과를 그대로 사용했습니다. 소스의 함수·클래스 이름/인자/기본값·annotation을 아래와 1:1 대조합니다.

- `normalize`: function, 소스 42행
- `event_codes`: function, 소스 48행
- `title_key`: function, 소스 53행
- `carol_matches`: function, 소스 59행
- `OccasionDecision`: class, 소스 66행 / decorator dataclass(frozen=True)
- `OccasionDecision.as_row`: method, 소스 76행
- `_decision`: function, 소스 86행
- `screen_track`: function, 소스 93행
- `policy_document`: function, 소스 136행

```python
normalize(value: object) -> str
event_codes(text: str) -> list[str]
title_key(title: str) -> str
carol_matches(title: str) -> list[str]
class OccasionDecision
OccasionDecision.as_row(self) -> dict[str, str]
_decision(track_id: str, status: str, source: str, codes=(), reasons=(), evidence=()) -> OccasionDecision
screen_track(track: Mapping[str, object], override: Mapping[str, object] | None=None, source_sha256: str | None=None) -> OccasionDecision
policy_document() -> dict
```
