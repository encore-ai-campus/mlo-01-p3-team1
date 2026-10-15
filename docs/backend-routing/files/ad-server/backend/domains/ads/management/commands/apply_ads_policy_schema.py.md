# ad-server/backend/domains/ads/management/commands/apply_ads_policy_schema.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../../../../../ad-server/backend/domains/ads/management/commands/apply_ads_policy_schema.py)

policy_manifest.json의 ad_budget_states/ad_daily_metrics 두 컬렉션 validator와 인덱스를 확인합니다. 기본 실행은 출력만 하고 --apply에서 기존 local_client/require_primary의 loopback·_dev·ads-rs primary 경계를 통과한 로컬 DB에 strict/error validator와 인덱스를 적용합니다.

관리3개/공개5개 manifest와 분리한 추가 정책 상태입니다. 외부 공유/운영 DB를 생성하거나 TTL·삭제·실제 예산값을 설정하지 않습니다. 스키마 적용은 DB 운영/복구 검증과 구분합니다.

## AST 시그니처

```python
load_policy_manifest()
class Command(BaseCommand)
Command.add_arguments(self, parser)
Command.handle(self, *args, **options)
```
