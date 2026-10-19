# backend/recommendation/tests/test_youtube_registry.py 라우팅

## 2026-10-19 수집 URL 공개 연결 — 현행

- 담당: Codex root / U-01·M-06·Q-02 연결 수정
- 브랜치/기준: feature/youtube-url-connection / develop a7dfafb
- 작성/수정: 2026-10-19. 기존 수령 원문은 보존합니다. 아래 앞 단계 서술은 당시 구현 이력이며 이번 절이 현행입니다.
- 계약·전체 검증: [수집 URL 연결 변경 라우팅](../../../../../development/수집_URL_공개화면_연결_변경_라우팅.md).

로컬 batch 조회와 기존 단일 곡 조회가 revision·대안·검수 값을 동일하게 반환하며 미등록 ID 조회가 DB에 새 곡을 삽입하지 않는 회귀를 추가합니다.

### AST 시그니처 — 검사 결과

```python
class YoutubeRegistryTests(SimpleTestCase)
YoutubeRegistryTests.setUp(self)
YoutubeRegistryTests.register(self, video='testVideo01', revision=0, track_id='track-one', **extra)
YoutubeRegistryTests.test_url_allowlist_never_fetches_and_rejects_confusable_or_credential_urls(self)
YoutubeRegistryTests.test_registration_pending_then_operator_playing_and_identity_required(self)
YoutubeRegistryTests.test_large_duration_mismatch_nan_and_bool_never_verify(self)
YoutubeRegistryTests.test_revisions_prevent_overwriting_another_operator(self)
YoutubeRegistryTests.test_blocked_mapping_is_not_revived_by_same_url_or_legacy_seed(self)
YoutubeRegistryTests.test_legacy_verified_metadata_only_seeds_pending(self)
YoutubeRegistryTests.test_csv_bom_formula_note_and_same_track_alternatives_preserved(self)
YoutubeRegistryTests.test_invalid_csv_or_stale_later_row_rolls_back_all_rows(self)
YoutubeRegistryTests.test_csv_headers_row_limit_and_bad_revision_rejected(self)
YoutubeRegistryTests.test_code_is_persistent_rotatable_and_never_printed(self)
YoutubeRegistryTests.test_production_never_accepts_local_secret(self)
YoutubeRegistryTests.test_native_operator_review_is_independent_of_blocked_iframe(self)
YoutubeRegistryTests.test_native_legacy_seed_requires_exact_reviewed_identity_and_preserves_iframe(self)
YoutubeRegistryTests.test_existing_registry_additive_native_schema_upgrade_is_idempotent(self)
YoutubeRegistryTests.test_native_duration_difference_requires_explicit_noted_acknowledgment(self)
YoutubeRegistryTests.test_native_duration_acknowledgment_is_bounded_and_does_not_change_iframe_rules(self)
YoutubeRegistryTests.test_batch_read_matches_local_single_track_registry_without_inserting_unknown_tracks(self)
```

## 앞 단계 기록

- 작성일/수정일: 2026-10-16
- 담당: API 키 없는 YouTube 등록·검수 백엔드 / 통합팀
- 기준 브랜치/커밋: feature/ad-logic / f22f974
- 소스: `backend/recommendation/tests/test_youtube_registry.py`
- 통합 근거: docs/development/YouTube_키없는_등록과_검수_변경_라우팅.md

## 기준 → 저장 회귀 검증

16개 SimpleTestCase가 workspace 아래 임시 SQLite·접근코드 파일에 대해 실행됩니다. 실제 매핑·카탈로그·외부 네트워크를 변경하지 않습니다.

URL 허용/credential·호스트·포트·control 문자 거절, CANDIDATE와 VERIFIED 구분, 원곡/PLAYING 모두 필수, 길이 불일치·NaN·bool 거절, 곡별 revision과 다중 대안, 차단의 등록/seed 우회 방지, legacy VERIFIED의 자동 승격 금지, BOM CSV·수식문자 비실행·같은 곡 대안 허용, 중복/stale 후 전체 rollback, header/500행/revision 제한, secret 비출력/회전/운영 거절을 확인합니다.

외부/iframe 승인 독립·수동 외부 PLAYING 보고·기존 native 메타데이터의 엄격 승계·외부 철회 후 seed 우회 방지·재승인 사유 해제·기존 SQLite native 컬럼 추가의 멱등성도 검증합니다. 외부 길이 차이의 명시 flag+비고+60초 한도, 감사 action, 잘못된 타입/초과 거절과 iframe 기준 불변을 별도 2건으로 확인합니다.

2026-10-16 이 모듈 16건과 API 10건을 포함한 백엔드 전체 136건이 통합 담당 실행에서 통과했습니다. 합성 PLAYING 보고는 실제 iframe/외부 탭 관측·청취나 삽입 허용 보증을 대신하지 않습니다.

## AST 시그니처

검사기 `.local-preview-logs/keyless-routing-audit.json`의 python_files[].symbols를 그대로 기록합니다.

```python
class YoutubeRegistryTests(SimpleTestCase)
YoutubeRegistryTests.setUp(self)
YoutubeRegistryTests.register(self, video='testVideo01', revision=0, track_id='track-one', **extra)
YoutubeRegistryTests.test_url_allowlist_never_fetches_and_rejects_confusable_or_credential_urls(self)
YoutubeRegistryTests.test_registration_pending_then_operator_playing_and_identity_required(self)
YoutubeRegistryTests.test_large_duration_mismatch_nan_and_bool_never_verify(self)
YoutubeRegistryTests.test_revisions_prevent_overwriting_another_operator(self)
YoutubeRegistryTests.test_blocked_mapping_is_not_revived_by_same_url_or_legacy_seed(self)
YoutubeRegistryTests.test_legacy_verified_metadata_only_seeds_pending(self)
YoutubeRegistryTests.test_csv_bom_formula_note_and_same_track_alternatives_preserved(self)
YoutubeRegistryTests.test_invalid_csv_or_stale_later_row_rolls_back_all_rows(self)
YoutubeRegistryTests.test_csv_headers_row_limit_and_bad_revision_rejected(self)
YoutubeRegistryTests.test_code_is_persistent_rotatable_and_never_printed(self)
YoutubeRegistryTests.test_production_never_accepts_local_secret(self)
YoutubeRegistryTests.test_native_operator_review_is_independent_of_blocked_iframe(self)
YoutubeRegistryTests.test_native_legacy_seed_requires_exact_reviewed_identity_and_preserves_iframe(self)
YoutubeRegistryTests.test_existing_registry_additive_native_schema_upgrade_is_idempotent(self)
YoutubeRegistryTests.test_native_duration_difference_requires_explicit_noted_acknowledgment(self)
YoutubeRegistryTests.test_native_duration_acknowledgment_is_bounded_and_does_not_change_iframe_rules(self)
```
