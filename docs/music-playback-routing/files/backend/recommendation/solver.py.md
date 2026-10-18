# backend/recommendation/solver.py 라우팅

- 작성일: 2026-10-16
- 수정일: 2026-10-18
- 담당: C 공개 대시보드·추천/음악 통합
- 범위: 일반 추천 후보와 고정 재생 시험 카탈로그 분리·오류 진단 후속
- 기준 브랜치/커밋: feature/ad-logic / f22f974
- 소스: [backend/recommendation/solver.py](../../../../../backend/recommendation/solver.py)

## 기준과 공급·소비

작업자가 공통 필터·모드별 점수까지 통과한 곡 배열과 선택 장르·모드·부모 track_id를 공급합니다. `choose`는 일반 규칙 추천의 창 확장·정수 시간 최적화이며, `choose_preview`는 로컬 미검수 CSV 프리뷰의 유효 조합 탐색입니다. 이 함수는 DB·외부 모델·YouTube 계정을 호출하지 않습니다.

기준은 목표 180분·허용 176~184분·자동 단축 없음입니다. 선택 장르는 서로 다른 곡으로 대표되어야 하며, OFF 장르 선택은 100% 단계 후 80% 단계 순서입니다. 재설정은 부모 고유 곡 수 기준 20% 내림·최소 1곡의 신규 track_id를 요구합니다.

## 이번 변경과 오류 계약

`choose_preview`는 전체 적격 후보의 총길이·선택 장르별 수·서로 다른 대표 가능 여부·신규 곡 수·OFF 선택 장르 최소 재생시간을 먼저 검사합니다. 전역 필요조건 부족이나 전체 범위 CP-SAT INFEASIBLE로 구성 불가가 입증되면 CANDIDATE_SHORTAGE/422입니다. 신규 곡 수 부족은 NO_MEANINGFUL_CHANGE/422로 부모를 유지합니다. 제한 창 실패·greedy 실패·UNKNOWN/시간 초과는 SEARCH_INCOMPLETE/503이며 후보 부족으로 단정하지 않습니다.

오류 details에는 candidate_count/total_ms/min_duration_ms/target_duration_ms/max_duration_ms, 선택·누락 장르와 장르별 수, distinct_genre_representatives_possible, 부모·필요·가용 신규곡 수, checked_full_candidate_pool과 reason을 제공합니다. 해당하는 경우 solver_windows·장르 비중 단계·필요 선택 장르 시간도 보존합니다. 이 진단은 추천 점수·시간 기준을 완화하지 않습니다.

## 검증

필터 후 후보 부족과 제한 탐색 미완료를 구분하는 신규 회귀 및 실제 요청 결과는 수용 기록을 확인합니다. 전체 CSV 후보 부족은 전체 적격 후보의 근거가 있을 때만 보고합니다. 모델 학습·청취 정합성·3시간 재생 완주 검증은 이 AST 검사 범위에 포함하지 않습니다.

[정책·화면·저장 연결 라우팅](../../../../development/기존_대시보드_YouTube_연결_라우팅.md)과 [일반 추천/재생 시험 분리 수용 기록](../../../../acceptance/일반_추천_후보와_재생시험_분리_검증_20261016.md)을 함께 확인합니다. 수령 원문과 기존 backend-routing 문서는 수정하지 않습니다.

## AST 시그니처

검사 JSON의 python_files[].symbols를 정본으로 기록합니다.

```python
representatives(tracks, genres)
_solve_window(candidates, deadline, selected_genres=(), min_selected_share=0, seed='')
choose(candidates, max_candidates, seconds, mode='ON', selected_genres=(), seed='', diagnostics=None)
choose_preview(candidates, mode='ON', selected_genres=(), seed='', parent_ids=())
```

## 2026-10-18 develop 동기화 보완

develop의 동일 점수 subset-sum 빠른 경로를 보존하며, YouTube 브랜치의 전체 후보 부족/탐색 미완료 진단도 유지합니다. 목표/허용 시간과 동점 규칙은 변경하지 않습니다.

```python
_equal_score_window(candidates, deadline, selected_genres)
```

기준 develop `8bdad88`·기존 feature/ad-logic `0a0cc82`의 대조와 실제 재검증은 [통합 기록](../../../../development/feature_전체_동기화_변경_라우팅_20261018.md)을 따릅니다.
