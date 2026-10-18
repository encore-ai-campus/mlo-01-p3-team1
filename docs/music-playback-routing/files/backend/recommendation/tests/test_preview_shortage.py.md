# backend/recommendation/tests/test_preview_shortage.py 라우팅

- 작성일/수정일: 2026-10-16
- 담당: C 추천/로컬 CSV 프리뷰 검증
- 범위: 후보 부족·신규곡 부족·탐색 미완료 오류 구분 회귀
- 기준 브랜치/커밋: feature/ad-logic / f22f974
- 소스: [backend/recommendation/tests/test_preview_shortage.py](../../../../../../backend/recommendation/tests/test_preview_shortage.py)

## 기준과 공급·소비

합성 candidate 배열과 Fraction 점수를 만들어 `solver.choose_preview`에 공급합니다. 직접 함수 검증이며 DB·외부 모델·YouTube 계정·음원은 호출하지 않습니다. 실패의 DomainError.code/status/details와 성공 총길이를 소비해 시간·필터 조건을 검증합니다.

11건은 전체 후보 총시간 부족·장르 누락과 한국어 설명·다중 장르 한 곡의 대표 중복 금지·부모 전체 곡 수 기준 신규곡 부족·전체 정수 조합 INFEASIBLE·UNKNOWN·800곡을 넘는 전체 범위 미완료·OFF 100% 단계 UNKNOWN에서 80% 임의 전환 금지·OFF 선택 장르 최소 시간 부족·100% 불가 입증 후 80% 성공·기존 유효 시간 성공을 확인합니다.

## 이번 변경과 검증

확실한 부족은 CANDIDATE_SHORTAGE/422, 가용 신규곡 부족은 NO_MEANINGFUL_CHANGE/422, 미완료는 SEARCH_INCOMPLETE/503으로 구분합니다. 실패한 제한 창·greedy·시간 초과를 전체 후보 부족으로 잘못 보고하지 않도록 기대값을 고정합니다. 목표 180분·허용 176~184분과 기존 결과 보존 조건은 변경하지 않습니다.

이 신규 모듈의 독립 표적 실행 11건이 통과했습니다. 실제 CSV·브라우저 및 전체 백엔드 통합 수치는 [분리 수용 기록](../../../../../acceptance/일반_추천_후보와_재생시험_분리_검증_20261016.md)에서 확인합니다. 합성 자료 통과는 전곡 청취·운영 연결 완료를 뜻하지 않습니다.

## AST 시그니처

검사 JSON의 python_files[].symbols를 정본으로 기록합니다.

```python
candidate(key, duration=240000, genres=('JAZZ',))
class PreviewShortageTests(TestCase)
PreviewShortageTests.failure(self, candidates, **options)
PreviewShortageTests.test_complete_three_song_duration_proves_shortage_and_explains_time(self)
PreviewShortageTests.test_missing_genre_has_korean_label_and_full_candidate_counts(self)
PreviewShortageTests.test_one_multigenre_song_cannot_represent_two_selected_genres(self)
PreviewShortageTests.test_regeneration_uses_original_parent_count_for_proven_new_track_shortage(self)
PreviewShortageTests.test_full_integer_combination_infeasible_is_proven_shortage(self)
PreviewShortageTests.test_unknown_is_incomplete_even_when_no_greedy_solution_was_found(self)
PreviewShortageTests.test_full_pool_larger_than_solver_limit_is_not_proven_by_smaller_windows(self)
PreviewShortageTests.test_off_does_not_open_80_percent_after_unknown_in_100_percent_stage(self)
PreviewShortageTests.test_off_selected_genre_duration_must_be_able_to_reach_80_percent(self)
PreviewShortageTests.test_off_can_open_80_percent_after_full_100_percent_duration_proof(self)
PreviewShortageTests.test_feasible_preview_keeps_original_valid_time(self)
```
