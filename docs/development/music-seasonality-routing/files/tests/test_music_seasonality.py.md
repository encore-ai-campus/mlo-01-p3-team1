# tests/test_music_seasonality.py 라우팅

- 작성일/수정일: 2026-10-16
- 담당: 음악 데이터·시즌 필터 에이전트
- 기준: feature/ad-logic / f22f974

기준·입출력·변경 이유·실제 검증은 [전체 변경 라우팅](../../../음악_시즌필터_변경_라우팅.md)을 확인합니다.

AST 시그니처:

```python
track(title, album='Studio Album', artist='Example Artist', track_id='one')
class OccasionScreenTests(unittest.TestCase)
OccasionScreenTests.test_explicit_title_excludes_and_preserves_source(self)
OccasionScreenTests.test_compilation_album_only_holds_rather_than_labels_song(self)
OccasionScreenTests.test_ambiguous_carol_title_is_not_automatically_approved(self)
OccasionScreenTests.test_snow_winter_holiday_and_artist_names_do_not_exclude(self)
OccasionScreenTests.test_word_boundaries_and_unicode(self)
OccasionScreenTests.test_missing_metadata_is_unscreened_not_general(self)
OccasionScreenTests.test_human_override_requires_matching_source_and_evidence(self)
OccasionScreenTests.test_decision_versions_are_reproducible_and_capture_changes(self)
```
