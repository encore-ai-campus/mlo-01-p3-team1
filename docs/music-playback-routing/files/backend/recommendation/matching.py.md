# backend/recommendation/matching.py 라우팅

- 작성일/수정일: 2026-10-19
- 담당: Codex, R-02/R-04 성능 연결
- 기준 브랜치/커밋: `develop` / `5cb467c893b8919c58f7e0c2a70b130afaaf4abd`
- 전체 변경 흐름: [추천 선곡 성능 개선 라우팅](../../../../development/추천_선곡_성능개선_변경_라우팅.md)

기존 solver의 결정적 augmenting-path genre 대표 매칭 함수를 공통 모듈로 이동했습니다. 기존 장르 순서·곡 순서·서로 다른 대표 조건을 유지하며 DB나 score를 읽거나 쓰지 않습니다. `solver`와 `exact_search`가 같은 함수 정의를 가져다 씁니다.

```python
representatives(tracks, genres)
```
