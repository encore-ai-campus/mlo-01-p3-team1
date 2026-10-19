# backend/recommendation/tests/test_catalog_storage.py 연결 라우팅

- 작성일: 2026-10-18
- 수정일: 2026-10-18
- 담당: Codex / 사용자 승인 통합 정합성 수정
- 브랜치/기준: develop / 160a66c
- [대응 코드](../../../../../../backend/recommendation/tests/test_catalog_storage.py)
- [기준·변경 전후·검증·남은 연결](../../../../../development/통합_정합성_수정_변경_라우팅.md)

## 호출·저장·검증 경계

압축·SHA/복원 상한·기존 list reader 시험을 유지합니다. export mock도 판정/버전/출처를 제공해 현재 발행 계약을 따르며 압축 검증을 시즌 필터 우회로 사용하지 않습니다.

## AST 시그니처

```python
class CatalogStorageTests(TestCase)
CatalogStorageTests.test_large_published_catalog_keeps_exact_tracks_and_digest(self)
CatalogStorageTests.test_corrupt_compressed_catalog_fails_integrity_validation(self)
CatalogStorageTests.test_legacy_list_and_bounded_expansion(self)
```
