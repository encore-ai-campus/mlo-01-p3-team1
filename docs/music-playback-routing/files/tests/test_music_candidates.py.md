# tests/test_music_candidates.py 라우팅

- 작성일/수정일: 2026-10-16
- 담당: 로컬 음악 재생 통합팀. 기존 분석은 보존 의존성으로만 문서화합니다.
- 기준 브랜치/커밋: feature/ad-logic / f22f974
- 소스: [tests/test_music_candidates.py](../../../../tests/test_music_candidates.py)
- 범위/목적: 일반 후보·시간 탐색의 단위 검증

## 기준과 입력

작은 정수 길이/정확 Fraction 점수의 고정 곡과 행사 판정을 사용합니다.

[최신 ON/OFF 후보 계약](../../../product/카페_음악_추천_서비스_3차_컬럼_기반_추천_로직_가이드.md)과 [시즌 분리·재생 가이드](../../../development/music/YouTube_로컬_재생_기획과_구현_가이드.md)를 연결하며 수령 원문과 기존 원본 음악 열은 바꾸지 않습니다.

## 실제 공급·소비와 검증

정확180 우선·초과 우선·허용 경계·보류곡 복귀 금지·누락 판정/중복·speed·점수 문자열/품질 한계를 검증합니다.

python -m unittest discover -s tests -p test_music_*.py로 실행합니다. 실제 CSV 전수 대조는 verify.py에 별도로 있습니다.

근거: [연결 문서/검증 자료](../../../../analysis/weather_music_20261016/general/verification.json). [정본 차이·남은 연결](../../../development/음악_재생_정본_변경_라우팅.md)와 [시즌 필터 검증](../../../development/음악_시즌필터_변경_라우팅.md)에서 실제 실행/미실행을 구분합니다.

## AST 심벌

시그니처는 routing-doc-auditor의 구조화 결과를 그대로 사용했습니다. 소스의 함수·클래스 이름/인자/기본값·annotation을 아래와 1:1 대조합니다.

- `candidate`: function, 소스 8행
- `GeneralCandidateTests`: class, 소스 13행 / base unittest.TestCase
- `GeneralCandidateTests.choose`: method, 소스 14행
- `GeneralCandidateTests.test_exact_time_has_priority_over_earlier_feasible`: method, 소스 17행
- `GeneralCandidateTests.test_above_target_has_priority_over_below`: method, 소스 22행
- `GeneralCandidateTests.test_boundaries_accepted_and_outside_is_shortage`: method, 소스 26행
- `GeneralCandidateTests.test_held_track_never_reenters_to_fill_duration`: method, 소스 36행
- `GeneralCandidateTests.test_missing_decision_and_duplicate_ids_fail_closed`: method, 소스 45행
- `GeneralCandidateTests.test_speed_and_exact_score_values_preserved`: method, 소스 53행
- `GeneralCandidateTests.test_non_general_cannot_be_passed_directly_to_solver`: method, 소스 60행

```python
candidate(key, duration, score='100', speed='slow')
class GeneralCandidateTests(unittest.TestCase)
GeneralCandidateTests.choose(self, rows, **kwargs)
GeneralCandidateTests.test_exact_time_has_priority_over_earlier_feasible(self)
GeneralCandidateTests.test_above_target_has_priority_over_below(self)
GeneralCandidateTests.test_boundaries_accepted_and_outside_is_shortage(self)
GeneralCandidateTests.test_held_track_never_reenters_to_fill_duration(self)
GeneralCandidateTests.test_missing_decision_and_duplicate_ids_fail_closed(self)
GeneralCandidateTests.test_speed_and_exact_score_values_preserved(self)
GeneralCandidateTests.test_non_general_cannot_be_passed_directly_to_solver(self)
```
