# backend/recommendation/exact_search.py 라우팅

- 작성일/수정일: 2026-10-19
- 담당: Codex, R-02/R-04 성능 연결
- 기준 브랜치/커밋: `develop` / `5cb467c893b8919c58f7e0c2a70b130afaaf4abd`
- 전체 변경 흐름: [추천 선곡 성능 개선 라우팅](../../../../development/추천_선곡_성능개선_변경_라우팅.md)

## 계약

이 모듈은 요청 후보 창의 정확 정수 duration_ms·Fraction 점수·서로 다른 장르 대표·선택 장르 재생시간 조건에서 증명 가능한 결과만 반환합니다. 시간·상태 예산 또는 안전 한도 안에서 증명할 수 없으면 `solve_window`가 기존 CP-SAT fallback으로 넘깁니다. 모든 내부 단계는 요청에서 고정한 단일 deadline을 공유합니다. 추가 저장, 카탈로그 변경, 외부 호출은 없습니다.

`pivot_fill`, `solve_core`는 점수/시간 목적에 대한 인증 가능한 최적 결과를 찾습니다. `genre_bound_fill`, `genre_branch_core`는 장르의 서로 다른 대표·100%/80% 단계 조건을 유지하며, 보조 bound/DP·matching은 결과를 증명하지 못하면 거절하여 더 일반적인 단계나 CP-SAT으로 계속합니다. 알고리즘이 후보 전체에 대한 전역 최적성을 뜻하지 않으며, 기존 창/상태 계약은 그대로입니다.

## AST 시그니처

```python
_finish_reduced_cp(candidates, scores, pivot, upper, lower, forced_in, free, hint, target, deadline, stats)
solve_core(candidates, target, deadline, stats=None, max_free=44)
exact_bits(tracks, target, deadline, stats=None)
pivot_fill(ordered, target, deadline, stats)
exchange_witness(ordered, target, pivot, upper, current, deadline, stats)
numpy_subset(tracks, coefficients, target, deadline, max_free=44)
class SumOracle
SumOracle.__init__(self, tracks, maximum, deadline)
SumOracle.possible(self, target)
SumOracle.subset(self, target)
SumOracle.suffix_at(self, index)
SumOracle.possible_from(self, index, target)
SumOracle.subset_from(self, index, target)
class CountSumOracle
CountSumOracle.__init__(self, tracks, maximum, deadline, groups, needed)
CountSumOracle.add(self, value, index, thresholds)
CountSumOracle.suffix_at(self, index, needed=0)
finish_pivot_core_dfs(candidates, scores, pivot, upper, lower, forced_in, free, hint, target, deadline, stats)
finish_pivot_core(candidates, scores, pivot, upper, lower, forced_in, free, hint, target, deadline, stats)
plateau_reduced_exact(candidates, scores, pivot, upper, lower, forced_in, free, hint, target, deadline, stats)
budget_items(candidates, scores, pivot, free, gap)
budget_count(items, budget, deadline, cap=1500000)
finish_bounded_core(candidates, scores, pivot, upper, lower, forced_in, free, hint, target, deadline, stats)
finish_optimal_face(candidates, scores, pivot, upper, optimum_loss, forced_in, free, hint, target, deadline, stats)
modular_reduce(candidates, scores, pivot, upper, lower, forced_in, free, hint, target, deadline, stats)
strong_modular_reduce(candidates, scores, pivot, upper, lower, forced_in, free, hint, target, deadline, stats, modulus=1000000)
improve_incumbent(candidates, scores, pivot, upper, lower, forced_in, free, hint, target, deadline, stats)
necessary_genre_tracks(ordered, genres, representatives)
deficient_genres(chosen, genres)
lex_genre_partition(ordered, target, genres, deadline, representatives, stats, initial_forced=())
lex_genre_dfs(ordered, target, genres, deadline, representatives, stats, initial_forced=())
prefix_witness(ordered, target, genres, forced, deadline, representatives)
lex_genre_subset_single(ordered, target, genres, deadline, representatives, stats, initial_forced=(), rare_cap=22)
class MultiCountSumOracle
MultiCountSumOracle.__init__(self, tracks, maximum, deadline, cuts, maxima)
MultiCountSumOracle.add(self, value, index, thresholds)
MultiCountSumOracle.suffix_at(self, index, needed=0)
class SparseHallOracle
SparseHallOracle.__init__(self, tracks, maximum, cuts, initial, deadline, stats)
SparseHallOracle.add(self, value, index, thresholds)
SparseHallOracle.build(self, start, stop, tail)
SparseHallOracle.visit(self, start, stop, tail, callback)
sparse_joint_walk(rest, rare, common, states, durations, residual, cuts, requirements, deadline, stats)
duration_genre_subset(rest, target, first, genres, deadline, stats)
contract_fixed_genres(first, genres, representatives)
eager_hall_cuts(first, rare, common, genres, states, deadline, stats)
lex_genre_subset(ordered, target, genres, deadline, representatives, stats, initial_forced=(), rare_cap=22, score_costs=None, score_budget=0, hint_positive=())
genre_bound_fill(ordered, target, genres, deadline, representatives, stats)
early_reduced_exact(candidates, scores, pivot, upper, lower, forced_in, free, hint, target, deadline, stats)
class CoreDeclined
genre_dual_bound(ordered, target, genres, deadline, stats)
improve_genre_witness(ordered, target, genres, share, dual, witness, deadline, representatives, stats)
genre_initial_witness(ordered, target, genres, share, dual, deadline, representatives, stats)
solve_above_cutoff(ordered, target, cutoff, deadline, stats)
additional_matching_cost(available, forced, genres, costs)
class SharedDPDeclined
shared_genre_dp(ordered, target, genres, dual, witness, deadline, stats)
genre_branch_core(ordered, target, genres, share, deadline, engine, representatives, stats)
finish_reduced_cp(*args)
class _CoreEngine
_reduced_or_fallback(candidates, deadline, selected_genres, min_selected_share, seed, fallback)
solve_window(candidates, deadline, selected_genres=(), min_selected_share=0, seed='', *, fallback)
```
