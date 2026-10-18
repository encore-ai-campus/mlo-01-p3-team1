# backend/recommendation/tests/test_keyless_playback.py 라우팅

- 작성일/수정일: 2026-10-16
- 담당: API 키 없는 YouTube 등록·검수 백엔드 / 통합팀
- 기준 브랜치/커밋: feature/ad-logic / f22f974
- 소스: `backend/recommendation/tests/test_keyless_playback.py`
- 통합 근거: docs/development/YouTube_키없는_등록과_검수_변경_라우팅.md

## 기준 → 회귀 검증

KEYLESS를 기본 경로로 채택한 공개 resolver의 4개 오프라인 회귀입니다. workspace 아래 임시 SQLite에만 등록하고 외부 _api_json과 과거 _catalog_candidate는 호출 시 즉시 실패하도록 막습니다.

미등록 UNMAPPED/기존 매핑 PENDING에서 원문 snapshot·Data API로 넘어가지 않음, 검수 완료 대안 재사용·요청 제외/운영자 차단 후 재노출 방지, 저장소 장애의 SEARCH_UNAVAILABLE/REGISTRY_UNAVAILABLE 정지, 운영의 REGISTRY_NOT_CONFIGURED와 로컬 저장소 미접근을 확인합니다.

PLAYING은 시험의 명시 입력이며 실제 YouTube 영상/Chrome/Premium/완청이나 전체 3시간을 검증한 것이 아닙니다. 기존 공식 검색 18건·API 6건은 OPTIONAL_SEARCH 분기를 별도 override해서 보존합니다.

## AST 시그니처

검사기 `.local-preview-logs/keyless-routing-audit.json`의 python_files[].symbols를 그대로 기록합니다.

```python
class KeylessPlaybackTests(SimpleTestCase)
KeylessPlaybackTests.setUp(self)
KeylessPlaybackTests.resolve(self, excluded=())
KeylessPlaybackTests.register(self, video_id, revision)
KeylessPlaybackTests.test_unmapped_and_legacy_pending_never_fall_through_to_remote_or_snapshot(self)
KeylessPlaybackTests.test_reviewed_alternatives_are_reused_and_blocked_video_never_reappears(self)
KeylessPlaybackTests.test_storage_failure_holds_instead_of_silently_skipping_whole_queue(self)
KeylessPlaybackTests.test_production_never_reads_unconfigured_local_registry(self)
```
