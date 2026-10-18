# backend/recommendation/tests/test_youtube_playback_api.py 라우팅

- 작성일: 2026-10-16
- 수정일: 2026-10-18
- 담당: C 공개 대시보드·YouTube 재생 통합
- 범위: 기존 중앙 iframe 재생·LLM 없는 공식 검색·API 연결 후속
- 기준 브랜치/커밋: feature/ad-logic / f22f974
- 소스: [backend/recommendation/tests/test_youtube_playback_api.py](../../../../../../backend/recommendation/tests/test_youtube_playback_api.py)

## 기준과 공급·소비

Django TransactionTestCase가 메모리 시험 DB의 합성 추천 결과·익명 세션·기존 VERIFIED 영상 ID를 공급하고 `POST /api/playlists/{playlist_id}/youtube-playback`의 응답과 음악 업무 상태를 확인합니다. 서버 API 키는 비어 있는 시험 설정이며 실제 외부 검색·음원·LLM을 호출하지 않습니다.

최신 사용자 결정 이후 이 모듈은 YOUTUBE_PLAYBACK_MODE=OPTIONAL_SEARCH를 명시해 이전 선택 분기의 6건을 보존합니다. 현재 기본 KEYLESS의 검수 registry·과거 snapshot 우회 금지·운영/기술 장애는 test_keyless_playback.py의 별도 4건과 등록·검수 18건을 따릅니다. 아래 API_KEY_MISSING/기존 VERIFIED 직접 반환은 현재 기본 모드의 동작을 뜻하지 않습니다.

## 이번 변경과 검증

6건은 키 없는 기존 VERIFIED 후보 조회와 음악 snapshot/Job/승인/outbox 보존, 미매핑 시 API_KEY_MISSING, 외부 소유자/결과 밖 곡의 resolver 진입 전 차단, 제외 미반영 409와 부모 보존, 임의 URL/검색어/비밀번호·잘못된 제외 ID/과다 목록 거절, CSRF 필수를 확인합니다. 가짜 영상 ID는 오프라인 계약 시험에만 쓰며 실제 재생 확인으로 보고하지 않습니다.

이 모듈을 포함한 백엔드 전체 101건이 통과했습니다. 브라우저 중앙 iframe·자동재생·종료 다음 곡·150/153 처리·실제 키 등록과 공식 검색 성공 여부는 별도 수용 기록의 관찰 범위를 따릅니다.

[대시보드 연결 가이드](../../../../../development/music/YouTube_로컬_재생_기획과_구현_가이드.md)·[자동 검색 변경 라우팅](../../../../../development/YouTube_자동검색_변경_라우팅.md)·[중앙 iframe 수용 기록](../../../../../acceptance/대시보드_중앙_YouTube_iframe_검증_20261016.md)을 함께 확인합니다. 수령 원문과 기존 backend-routing은 수정하지 않습니다.

## AST 시그니처

검사 JSON의 python_files[].symbols를 정본으로 기록합니다.

```python
class YoutubePlaybackApiTests(TransactionTestCase)
YoutubePlaybackApiTests.setUp(self)
YoutubePlaybackApiTests.post(self, body, client=None)
YoutubePlaybackApiTests.test_catalog_candidate_works_without_key_and_preserves_music_state(self)
YoutubePlaybackApiTests.test_unmapped_track_reports_missing_search_connection_without_an_llm(self)
YoutubePlaybackApiTests.test_foreign_owner_and_track_outside_result_never_reach_resolver(self)
YoutubePlaybackApiTests.test_unapplied_exclusions_hold_playback_without_mutating_parent(self)
YoutubePlaybackApiTests.test_client_cannot_submit_a_url_query_password_or_unbounded_exclusions(self)
YoutubePlaybackApiTests.test_csrf_is_required_before_playback_lookup(self)
```

## 2026-10-18 develop 동기화 보완

합성 demo-region의 WEATHER_PROVIDER를 명시해 실제 로컬 날씨 캐시와 분리합니다. 소유·CSRF·제외·키 없는 영상 조회 검증은 유지합니다.

기준 develop `8bdad88`·기존 feature/ad-logic `0a0cc82`의 대조와 실제 재검증은 [통합 기록](../../../../../development/feature_전체_동기화_변경_라우팅_20261018.md)을 따릅니다.
