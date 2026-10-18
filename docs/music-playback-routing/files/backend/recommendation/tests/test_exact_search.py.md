# backend/recommendation/tests/test_exact_search.py 라우팅

- 작성일/수정일: 2026-10-19
- 담당: Codex, R-02/R-04 성능 연결 회귀검증
- 기준 브랜치/커밋: `develop` / `5cb467c893b8919c58f7e0c2a70b130afaaf4abd`
- 전체 변경 흐름: [추천 선곡 성능 개선 라우팅](../../../../development/추천_선곡_성능개선_변경_라우팅.md)

선택 장르 하나의 80% 보완, 둘 이상의 대표를 갖는 100% 구성, 모든 점수가 같은 deterministic seed 동점을 확인합니다. 전문 exact 경로를 같은 입력의 CP-SAT 대체 경로와 비교하고 시간 범위와 장르 비율을 검사합니다.

```python
pool(jazz_count, pop_count, *, dual_count=0, equal_scores=False)
class ExactSearchTests
ExactSearchTests.assert_same_solution(self, candidates, genres, share, seed='fixed-seed')
ExactSearchTests.test_single_genre_share_uses_same_exact_solution_as_cp_sat_fallback(self)
ExactSearchTests.test_two_genres_keep_distinct_representatives_and_full_share(self)
ExactSearchTests.test_equal_score_genre_pool_keeps_deterministic_seed_ties(self)
```
