# backend/recommendation/tests/test_catalog_publication.py 연결 라우팅

- 작성일: 2026-10-18
- 수정일: 2026-10-19
- 담당: Codex / 사용자 승인 통합 정합성 수정
- 브랜치/기준: develop / 160a66c
- [대응 코드](../../../../../../backend/recommendation/tests/test_catalog_publication.py)
- [기준·변경 전후·검증·남은 연결](../../../../../development/통합_정합성_수정_변경_라우팅.md)

## 호출·저장·검증 경계

같은 시각/반대 버전 이름·시계 역행·기존 갱신에 따른 선택을 검증합니다. MigrationExecutor로 이전 스키마→순번 backfill 후 기존 JSON/SHA 보존과 최신 선택을 확인하고 최신 스키마로 복구합니다.

## AST 시그니처

```python
class CatalogPublicationTests(TestCase)
CatalogPublicationTests.create(self, version, **extra)
CatalogPublicationTests.test_equal_times_and_reverse_version_names_follow_registration_order(self)
CatalogPublicationTests.test_clock_rollback_and_updates_do_not_change_registration_order(self)
class CatalogPublicationMigrationTests(TransactionTestCase)
CatalogPublicationMigrationTests.test_existing_snapshots_are_preserved_and_backfilled(self)
```

## 2026-10-19 추천 분산 실행 연결

이번 큐·worker·provider 예약·설정/검증 변경은 별도 `docs/development/추천_분산처리_변경_라우팅.md`와 `docs/runbook/추천_분산처리_인프라_인계.md`에서 관리합니다. 기존 담당 기록과 수령 원문은 보존합니다.
