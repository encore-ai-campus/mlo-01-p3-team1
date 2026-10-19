# ad-server/backend/domains/ads/management/commands/apply_ads_public_schema.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../../../../../ad-server/backend/domains/ads/management/commands/apply_ads_public_schema.py)

공개 단계의 추가 다섯 컬렉션 manifest를 출력하고 선택 적용합니다. 기본 실행은 validator/index 목록만 출력하며 DB에 연결하지 않습니다. `--apply`는 기존 local_client/require_primary 경계를 통과한 loopback·개발 _dev DB·ads-rs primary에만 strict validator와 인덱스를 적용합니다.

관리 세 컬렉션과 별도 진입점이며 기존 컬렉션에는 collMod, 없는 컬렉션에는 create_collection을 사용합니다. partial unique index 옵션도 전달합니다. TTL 삭제·공유/운영 DB 설정·미정 수명/예산 기본값은 추가하지 않습니다.

## AST 시그니처

```python
class Command(BaseCommand)
Command.add_arguments(self, parser)
Command.handle(self, *args, **options)
```
