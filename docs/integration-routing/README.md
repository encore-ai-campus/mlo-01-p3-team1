# 통합 정합성 코드 인계 색인

- 작성일: 2026-10-18
- 수정일: 2026-10-19
- 담당: Codex, B 통합 조율 범위의 사용자 승인 수정
- 기준: develop / 160a66c5ca0a19d4fd22cedd2538dad2d63f5f71
- 기준 → 코드·저장 → 검증: [통합 정합성 수정 라우팅](../development/통합_정합성_수정_변경_라우팅.md)

이 색인은 이번에 수정한 통합 코드의 별도 인계 문서입니다. 수령 원문과 다른 작업자의 라우팅 본문은 보존합니다. 광고의 기존 코드와 신규 브리지/준비 명령은 [광고 색인](../backend-routing/README.md)을 사용합니다.

검사 범위는 [routing-scopes.json](../../config/routing-scopes.json)에 명시합니다. `python scripts/check_routing.py`가 광고 전체와 아래 통합 파일을 AST 시그니처로 검사합니다. 전체 저장소의 모든 코드에 짝 문서가 있다는 뜻은 아닙니다. 새 범위는 대응 문서와 이 색인·scope를 함께 추가합니다.

| 소스 | 함수·클래스 연결 |
|---|---|
| `backend/music/catalog.py` | [짝 문서](files/backend/music/catalog.py.md) |
| `backend/music/test_occasion_publication.py` | [짝 문서](files/backend/music/test_occasion_publication.py.md) |
| `backend/recommendation/models.py` | [짝 문서](files/backend/recommendation/models.py.md) |
| `backend/recommendation/policy.py` | [짝 문서](files/backend/recommendation/policy.py.md) |
| `backend/recommendation/occasion.py` | [짝 문서](files/backend/recommendation/occasion.py.md) |
| `backend/recommendation/service.py` | [짝 문서](files/backend/recommendation/service.py.md) |
| `backend/recommendation/management/commands/seed_c_demo.py` | [짝 문서](files/backend/recommendation/management/commands/seed_c_demo.py.md) |
| `backend/recommendation/migrations/0005_catalog_publication.py` | [짝 문서](files/backend/recommendation/migrations/0005_catalog_publication.py.md) |
| `backend/recommendation/tests/test_api.py` | [짝 문서](files/backend/recommendation/tests/test_api.py.md) |
| `backend/recommendation/tests/test_catalog_publication.py` | [짝 문서](files/backend/recommendation/tests/test_catalog_publication.py.md) |
| `backend/recommendation/tests/test_catalog_storage.py` | [짝 문서](files/backend/recommendation/tests/test_catalog_storage.py.md) |
| `backend/common/history_api.py` | [짝 문서](files/backend/common/history_api.py.md) |
| `backend/common/music_api.py` | [짝 문서](files/backend/common/music_api.py.md) |
| `backend/common/test_exclusion_history.py` | [짝 문서](files/backend/common/test_exclusion_history.py.md) |
| `tests/run_browser_integration.py` | [짝 문서](files/tests/run_browser_integration.py.md) |
| `scripts/audit_routing.py` | [짝 문서](files/scripts/audit_routing.py.md) |
| `scripts/check_routing.py` | [짝 문서](files/scripts/check_routing.py.md) |

## 2026-10-19 공통 관리자 연결 추가

| 소스 | 함수·클래스 연결 |
|---|---|
| `backend/cafe/urls.py` | [짝 문서](files/backend/cafe/urls.py.md) |
| `backend/common/api.py` | [짝 문서](files/backend/common/api.py.md) |
| `backend/common/test_youtube_admin.py` | [짝 문서](files/backend/common/test_youtube_admin.py.md) |
| `backend/common/tests.py` | [짝 문서](files/backend/common/tests.py.md) |
| `backend/common/youtube_review.py` | [짝 문서](files/backend/common/youtube_review.py.md) |
