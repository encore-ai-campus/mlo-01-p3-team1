# tests/test_music_candidates.py 라우팅

- 작성일/수정일: 2026-10-16
- 담당: 음악 데이터·시즌 필터 에이전트
- 기준: feature/ad-logic / f22f974

기준·입출력·변경 이유·실제 검증은 [전체 변경 라우팅](../../../음악_시즌필터_변경_라우팅.md)을 확인합니다.

AST 시그니처:

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
