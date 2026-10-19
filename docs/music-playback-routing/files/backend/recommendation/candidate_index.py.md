# backend/recommendation/candidate_index.py 라우팅

- 작성일/수정일: 2026-10-19
- 담당: Codex, R-02/R-04 성능 연결
- 범위: 검증된 카탈로그의 고정 속성/사전 점수 비트 인덱스
- 기준 브랜치/커밋: `develop` / `5cb467c893b8919c58f7e0c2a70b130afaaf4abd`
- 전체 변경 흐름: [추천 선곡 성능 개선 라우팅](../../../../development/추천_선곡_성능개선_변경_라우팅.md)

## 입력·필터·출력

`CandidateIndex(rows)`는 이미 무결성 검증된 불변 카탈로그 행을 받아 공통 적격, 승인 장르, 빠르기, 검수 우선 순위가 반영된 instrumental, 현재 weather score cache의 NULL 게이트를 정수 비트 마스크로 저장합니다. row와 track_id→index 참조는 해당 작업자 프로세스에서만 유지합니다.

`candidates(options, weather, allowed_genres, allowed_speeds, excluded)`는 사용자 옵션과 저장된 family 조건을 구분합니다. ON에서는 전달받은 상속 장르/속도 집합을 그대로 하드 필터로 적용합니다. OFF는 `eligible` 정책처럼 장르·속도를 후보 하드 필터로 쓰지 않습니다. vocal과 제외 목록, 현재 캐시 버전의 날씨 탈락을 더한 다음 기존 `policy.score`를 호출합니다. 없는/오래된 score cache는 후보를 조기에 제거하지 않아 기존 원본 값 fallback과 같은 결과를 냅니다. 결과 감사에는 전체/공통 후보·시간·날씨 탈락·OFF 선호 누락 수를 포함합니다.

`common_count`는 같은 공통 필터를 적용한 후보 수만 빠르게 계산합니다. worker는 이 수가 선택 기준보다 충분히 작을 때에만 ON 후보를 인덱스로 열거하고, 넓은 풀 및 모든 OFF 요청은 기존 전체 순회를 사용합니다.

## 캐시 키와 제약

인덱스 자체는 `(catalog.pk, catalog.sha256, POLICY, MAPPING, WEATHER_SCORE_VERSION, OFF_SCORE_VERSION)`을 키로 한 worker 프로세스 단일 캐시입니다. 카탈로그 해시/정책 버전이 바뀌면 다시 만들며 DB 쓰기나 schema migration이 없습니다. `MappingProxyType`으로 bitmask/id map을 읽기 전용으로 노출합니다. bitset 저장량은 86,485곡 테스트에서 324,330바이트였으며 Python id map/원본 참조 메모리는 별도입니다.

## AST 시그니처

```python
class CandidateIndex
CandidateIndex.__init__(self, rows)
CandidateIndex._indices(mask)
CandidateIndex._common_mask(self, options, allowed_genres, allowed_speeds, excluded)
CandidateIndex.common_count(self, options, allowed_genres, allowed_speeds, excluded)
CandidateIndex.candidates(self, options, weather, allowed_genres, allowed_speeds, excluded)
```
