# ad-server/backend/domains/ads/public_schema.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../../../ad-server/backend/domains/ads/public_schema.py)

현재 파일의 schemas/public_manifest.json을 읽는 진입점입니다. management_manifest.json의 관리 세 컬렉션과 분리한 추가 공개 상태만 반환합니다.

추가 상태는 ad_rotation_state/ad_deliveries/ad_events/ad_repeat_windows/ad_estimated_usage_ledger입니다. strict 형식과 고유키·조회 인덱스를 기술하며 운영 수명·예산 숫자·자동 TTL 삭제를 확정하지 않습니다. DB 적용은 apply_ads_public_schema 명령의 별도 경계를 따릅니다.

선택 경로의 display_expires_at은 기존 배달과 호환되도록 필수 목록 밖의 date 필드입니다. 존재하면 issued_at보다 이후이고 event_expires_at보다 이전인지 검사합니다. 새 보고 마감은 기존 event_expires_at을 사용하며 과거 배달 필드를 자동 생성하지 않습니다. 선택 budget_policy_version도 새 배달의 당시 예산 판정/서명 마커로 허용하며 기존 필수 필드로 소급하지 않습니다.

## AST 시그니처

```python
load_public_manifest() -> dict
```
