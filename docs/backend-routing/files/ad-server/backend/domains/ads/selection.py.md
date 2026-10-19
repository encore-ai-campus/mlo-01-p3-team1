# 광고 선정과 표시 상한

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- 원본: [ad-server/backend/domains/ads/selection.py](../../../../../../../ad-server/backend/domains/ads/selection.py)

서버가 검증한 후보의 위치·기간·중단·소재·예산·환경을 검사한 뒤 최고 priority와 위치별 ID 순환을 계산합니다. 예산 bool과 이벤트 만료 시각은 명시 입력이며 운영 기본값이 없습니다. 커서/delivery 원자 저장·재확인·중단 경합은 공개 서비스/저장소가 연결합니다. 브라우저3초 숨김은 C의 별도 검증입니다. cursor_changed는 ID 값의 변경만 뜻하며 단일 후보의 새 delivery에서도 원자적 커서/배달 저장은 필요합니다.

시그니처는 `.cache/routing-next-ads-rules.json`의 Python AST 결과를 사용했습니다.

## AST 시그니처

- `_validate_placement(value)`
- `_validate_id(value, field)`
- `_validate_flag(value, field)`
- `class AdCandidate`
- `AdCandidate.__post_init__(self)`
- `class RotationCursor`
- `RotationCursor.__post_init__(self)`
- `class SelectionDecision`
- `select_ad(candidates: Iterable[AdCandidate], *, placement: str, now: datetime, cursor: RotationCursor, is_test: bool, advance_cursor: bool=True) -> SelectionDecision`
- `display_valid_until(evaluated_at: datetime, ends_at: datetime, *, event_expires_at: datetime) -> datetime | None`

이 파일은 순수 함수·DTO 또는 그 검증 경계를 유지합니다. HTTP/원자 저장은 public_service.py·ads_public_mongo.py가 연결하며 광고 라우팅 색인과 해당 짝 문서를 따릅니다.
