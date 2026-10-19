# backend/recommendation/policy.py 연결 라우팅

- 작성일: 2026-10-18
- 수정일: 2026-10-18
- 담당: Codex / 사용자 승인 통합 정합성 수정
- 브랜치/기준: develop / 160a66c
- [대응 코드](../../../../../backend/recommendation/policy.py)
- [기준·변경 전후·검증·남은 연결](../../../../development/통합_정합성_수정_변경_라우팅.md)

## 호출·저장·검증 경계

기존 ON/OFF 점수식·장르/speed·보컬·제외 검사 앞에 general_eligible을 적용합니다. GENERAL·유효 출처·판정/정책 버전이 없으면 두 모드와 규칙/Gemini 모두 후보에서 보류합니다. 점수와 시간 우선순위는 바꾸지 않습니다.

## AST 시그니처

```python
groups(raw_genres)
profile(pty, sky)
initial_speeds(tempo, weather)
eligible(track, options, allowed_genres, allowed_speeds, excluded)
unit(value)
_unit_text(text)
component(value, interval, width)
_component_exact(value, low, high, width)
weather_fit(track, weather)
off_preference_details(track, options)
off_preference(track, options)
_stored_score(track, kind, code, version)
theme_affinity(track, theme)
precompute_scores(track)
score(track, options, weather=None)
```
