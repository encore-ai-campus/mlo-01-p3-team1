# tests/test_music_seasonality.py 라우팅

- 작성일/수정일: 2026-10-16
- 담당: 로컬 음악 재생 통합팀. 기존 분석은 보존 의존성으로만 문서화합니다.
- 기준 브랜치/커밋: feature/ad-logic / f22f974
- 소스: [tests/test_music_seasonality.py](../../../../tests/test_music_seasonality.py)
- 범위/목적: 행사 판정과 오탐 방지의 단위 검증

## 기준과 입력

명백 행사 제목·앨범 단독·다의 캐럴·인명/일반 겨울 표현·누락·명시 검수 고정 예시를 사용합니다.

[최신 ON/OFF 후보 계약](../../../product/카페_음악_추천_서비스_3차_컬럼_기반_추천_로직_가이드.md)과 [시즌 분리·재생 가이드](../../../development/music/YouTube_로컬_재생_기획과_구현_가이드.md)를 연결하며 수령 원문과 기존 원본 음악 열은 바꾸지 않습니다.

## 실제 공급·소비와 검증

명백 신호와 보류 구분, Snow/Winter/Holiday 인명 오탐 방지, source SHA가 맞는 명시 검수 우선과 판정 버전 재현성을 검사합니다.

단위 검증 통과는 메타데이터 규칙의 동작 검증입니다. 누락 행사성 전수 발견이나 인간 청취 정확도를 주장하지 않습니다.

근거: [연결 문서/검증 자료](../../../development/음악_시즌필터_변경_라우팅.md). [정본 차이·남은 연결](../../../development/음악_재생_정본_변경_라우팅.md)와 [시즌 필터 검증](../../../development/음악_시즌필터_변경_라우팅.md)에서 실제 실행/미실행을 구분합니다.

## AST 심벌

시그니처는 routing-doc-auditor의 구조화 결과를 그대로 사용했습니다. 소스의 함수·클래스 이름/인자/기본값·annotation을 아래와 1:1 대조합니다.

- `track`: function, 소스 6행
- `OccasionScreenTests`: class, 소스 10행 / base unittest.TestCase
- `OccasionScreenTests.test_explicit_title_excludes_and_preserves_source`: method, 소스 11행
- `OccasionScreenTests.test_compilation_album_only_holds_rather_than_labels_song`: method, 소스 19행
- `OccasionScreenTests.test_ambiguous_carol_title_is_not_automatically_approved`: method, 소스 24행
- `OccasionScreenTests.test_snow_winter_holiday_and_artist_names_do_not_exclude`: method, 소스 28행
- `OccasionScreenTests.test_word_boundaries_and_unicode`: method, 소스 36행
- `OccasionScreenTests.test_missing_metadata_is_unscreened_not_general`: method, 소스 41행
- `OccasionScreenTests.test_human_override_requires_matching_source_and_evidence`: method, 소스 44행
- `OccasionScreenTests.test_decision_versions_are_reproducible_and_capture_changes`: method, 소스 53행

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
