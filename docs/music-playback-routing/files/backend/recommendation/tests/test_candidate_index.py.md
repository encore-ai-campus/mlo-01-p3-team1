# backend/recommendation/tests/test_candidate_index.py 라우팅

- 작성일/수정일: 2026-10-19
- 담당: Codex, R-02/R-04 성능 연결 회귀검증
- 기준 브랜치/커밋: `develop` / `5cb467c893b8919c58f7e0c2a70b130afaaf4abd`
- 전체 변경 흐름: [추천 선곡 성능 개선 라우팅](../../../../development/추천_선곡_성능개선_변경_라우팅.md)

정책의 전체 순회와 비트 인덱스 결과를 ID·Fraction 점수·감사 집계 단위로 비교합니다. ON/OFF, 다섯 날씨와 MIXED, 사용자 태그와 다른 상속 장르/속도, 제외 ID, 보컬 선호, 무보컬 검수 우선, 누락/구버전/부분 score cache를 검사합니다. 새 점수식이나 mock scorer로 테스트하지 않습니다.

```python
track(index)
expected(rows, options, weather, allowed_genres, allowed_speeds, excluded)
class CandidateIndexTests
CandidateIndexTests.test_index_matches_policy_and_audit_for_inherited_filters(self)
CandidateIndexTests.test_all_selected_tags_and_no_preference_keep_candidate_contract(self)
CandidateIndexTests.test_masks_preserve_reviewed_instrumental_precedence(self)
```
