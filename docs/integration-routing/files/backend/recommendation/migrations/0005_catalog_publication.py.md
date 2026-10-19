# backend/recommendation/migrations/0005_catalog_publication.py 연결 라우팅

- 작성일: 2026-10-18
- 수정일: 2026-10-18
- 담당: Codex / 사용자 승인 통합 정합성 수정
- 브랜치/기준: develop / 160a66c
- [대응 코드](../../../../../../backend/recommendation/migrations/0005_catalog_publication.py)
- [기준·변경 전후·검증·남은 연결](../../../../../development/통합_정합성_수정_변경_라우팅.md)

## 호출·저장·검증 경계

카탈로그 등록 순번 테이블을 추가하고 기존 Catalog를 created_at/version 순으로 연결합니다. tracks/SHA/기존 결과를 바꾸지 않으며 과거 동시각의 실제 순서는 복원 불가입니다. 새 코드 기동 전 적용하고 롤백은 작업자 중지 후 진행합니다.

## AST 시그니처

```python
backfill_publications(apps, schema_editor)
class Migration(migrations.Migration)
```
