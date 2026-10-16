# backend/recommendation/tests/test_youtube_playback.py

- 작성일/수정일: 2026-10-16
- 담당: YouTube 자동 검색 백엔드
- 기준: feature/ad-logic / f22f974
- 소스: `backend/recommendation/tests/test_youtube_playback.py`

DB와 외부 네트워크를 사용하지 않는 SimpleTestCase 18건입니다. 엄격 입력, 기존 매핑/키 없음, 삽입·공개·한국·연령·생방송 제한, 원곡명/아티스트/버전/길이, 조회 캐시/중복 요청/분·일 한도/비밀값 비노출과 불변성을 확인합니다. 실제 Data API/iframe 재생 통과의 근거가 아닙니다.

최신 기본 경로가 KEYLESS로 바뀐 뒤 이 모듈에는 YOUTUBE_PLAYBACK_MODE=OPTIONAL_SEARCH override를 명시했습니다. 이전 검색 분기의 회귀 보존용이며 기본 모드에서 원문 매핑이나 Data API를 사용한다는 뜻이 아닙니다. 새 기본 경로 4건은 test_keyless_playback.py, 등록·검수 저장/API 18건은 별도 새 시험에서 검증합니다.

[계약 → 코드 → 실행·미실행 연결](../../../../../development/YouTube_자동검색_변경_라우팅.md)을 확인합니다.

## AST 시그니처

검사기 `analysis/youtube-resolver-routing-audit.json`의 구조화 symbols를 기록합니다.

```python
track(**changes)
video(video_id='abcdefghijk', **changes)
class YoutubePlaybackTests(SimpleTestCase)
YoutubePlaybackTests.setUp(self)
YoutubePlaybackTests.mapped_track(self)
YoutubePlaybackTests.search_payload(self, ids=('abcdefghijk',))
YoutubePlaybackTests.test_request_shape_rejects_urls_keys_unknown_fields_and_invalid_exclusions(self)
YoutubePlaybackTests.test_verified_mapping_works_without_key_and_never_calls_search(self)
YoutubePlaybackTests.test_unmapped_or_failed_mapping_without_key_is_explicitly_unavailable(self)
YoutubePlaybackTests.test_duration_parser_is_bounded_to_positive_iso_time(self)
YoutubePlaybackTests.test_api_search_uses_fixed_filters_and_keeps_automatic_match_as_candidate(self)
YoutubePlaybackTests.test_title_artist_version_and_duration_reject_false_matches(self)
YoutubePlaybackTests.test_public_embed_region_age_and_live_restrictions_are_enforced(self)
YoutubePlaybackTests.test_cached_candidates_are_shared_by_source_identity_and_filtered_without_new_api_calls(self)
YoutubePlaybackTests.test_changed_source_metadata_uses_new_cache_identity(self)
YoutubePlaybackTests.test_failed_verified_embed_uses_api_alternative_without_mutating_verified_mapping(self)
YoutubePlaybackTests.test_duplicate_ids_and_out_of_search_videos_are_not_returned(self)
YoutubePlaybackTests.test_no_match_is_not_a_claim_that_no_video_exists_on_youtube(self)
YoutubePlaybackTests.test_upstream_failure_is_short_cached_and_does_not_expose_secret(self)
YoutubePlaybackTests.test_owner_rate_limit_blocks_new_search_but_allows_cached_or_verified_candidates(self)
YoutubePlaybackTests.test_daily_limit_bounds_all_owners(self)
YoutubePlaybackTests.test_concurrent_source_lookup_does_not_issue_duplicate_network_requests(self)
YoutubePlaybackTests.test_http_errors_are_classified_without_echoing_server_error_or_api_key(self)
YoutubePlaybackTests.test_network_and_invalid_upstream_payload_are_handled(self)
```
