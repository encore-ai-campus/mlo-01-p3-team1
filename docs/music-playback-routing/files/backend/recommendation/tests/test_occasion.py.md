# backend/recommendation/tests/test_occasion.py 라우팅

- 작성일/수정일: 2026-10-16
- 담당: 음악 데이터·기존 대시보드 CSV 추천 연결
- 기준 브랜치/커밋: feature/ad-logic / f22f974
- 소스: [backend/recommendation/tests/test_occasion.py](../../../../../../backend/recommendation/tests/test_occasion.py)

## 기준과 공급·소비

기존 대시보드 API·행사 판정·영상 snapshot 통합 검증입니다. 저장소 tests/.test-tmp 하위의 고정 CSV/판정/가상 영상 파일과 메모리 시험 DB로 테스트합니다. 임의 fixture 영상 ID를 실제 성공이라고 보고하지 않습니다.

GENERAL만 추천 결과에 포함, 해시/판정 누락 차단, 카탈로그 보존/중복 등록, 영상 snapshot 불변·BLOCKED_EMBED 보존·근거/원곡 불일치 차단을 확인합니다. 전체 backend57건 통과 중 행사/선택11건입니다.

[정책→코드→실행·미실행 연결](../../../../../development/음악_시즌필터_변경_라우팅.md)의 후속 절과 [YouTube 이동 기획](../../../../../development/music/YouTube_로컬_재생_기획과_구현_가이드.md)를 함께 읽습니다. 수령 원문·원본18개/원본CSV·기존Spotify play_url은 보존합니다.

## 검증

루트 .venv Python3.12.13에서 C_LOCAL_DEMO=1로 backend.music/backend.recommendation.tests 전체61건 통과. 메모리 시험 DB만 사용하며 외부 YouTube 호출·계정·운영DB 변경은 수행하지 않았습니다. source/schema 불일치는 저장 전에 실패하고 기존 결과를 보존합니다.

## AST 시그니처

검사기의 구조화 symbols 값을 그대로 기록합니다.

```python
class OccasionPreviewTests(TestCase)
OccasionPreviewTests.setUp(self)
OccasionPreviewTests.write_manifest(self, source_sha=None)
OccasionPreviewTests.seed(self, **extra)
OccasionPreviewTests.test_main_csv_preview_and_existing_playlist_api_are_general_only(self)
OccasionPreviewTests.test_changed_source_or_artifact_fails_before_catalog_write(self)
OccasionPreviewTests.test_same_snapshot_is_idempotent_and_old_catalog_is_preserved(self)
OccasionPreviewTests.test_missing_decision_never_falls_back_to_unscreened_source(self)
OccasionPreviewTests.mapping_file(self, **changes)
OccasionPreviewTests.test_verified_mapping_is_snapshotted_without_changing_spotify_url(self)
OccasionPreviewTests.test_blocked_embed_is_preserved_and_never_promoted(self)
OccasionPreviewTests.test_stale_original_or_missing_evidence_mapping_rejects_before_write(self)
OccasionPreviewTests.selection_inputs(self, **selection_changes)
OccasionPreviewTests.test_explicit_playback_selection_preserves_order_and_existing_catalog(self)
OccasionPreviewTests.test_invalid_or_non_general_selection_never_writes_catalog(self)
OccasionPreviewTests.test_selection_requires_every_selected_mapping_verified(self)
OccasionPreviewTests.test_playback_selection_is_local_only_and_requires_mapping_file(self)
```

명시 재생 선택 후속: --playback-selection은 GENERAL 원본의 고유 ID와 전곡 VERIFIED 매핑을 검사하고 선택파일 SHA/버전/입력순서를 새 test Catalog에 보존합니다. 기존 worker 정렬·기존 Catalog·운영 경계는 유지합니다. 의미 검증4건 추가 후 백엔드 전체61건이 통과했습니다.
