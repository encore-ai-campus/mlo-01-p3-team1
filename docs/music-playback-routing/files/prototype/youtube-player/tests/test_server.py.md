# prototype/youtube-player/tests/test_server.py 라우팅

- 작성일/수정일: 2026-10-16
- 담당: 로컬 음악 재생 통합팀. 기존 분석은 보존 의존성으로만 문서화합니다.
- 기준 브랜치/커밋: feature/ad-logic / f22f974
- 소스: [prototype/youtube-player/tests/test_server.py](../../../../../../prototype/youtube-player/tests/test_server.py)
- 범위/목적: 로컬 HTTP·매핑·선택 검색의 오프라인 회귀검증

## 기준과 입력

임시 고정 CSV와 매핑을 만들고 포트0 loopback 서버를 띄웁니다. 검색 테스트는 요청을 대체하여 실제 YouTube API를 호출하지 않습니다.

[최신 ON/OFF 후보 계약](../../../../../product/카페_음악_추천_서비스_3차_컬럼_기반_추천_로직_가이드.md)과 [시즌 분리·재생 가이드](../../../../../development/music/YouTube_로컬_재생_기획과_구현_가이드.md)를 연결하며 수령 원문과 기존 원본 음악 열은 바꾸지 않습니다.

## 실제 공급·소비와 검증

원본 행 보존·GENERAL 게이트·검증 증빙/길이·배치 원자성·stale/idempotency·nonce/Origin·정적 파일/Host·검색 필터/캐시를 검사합니다.

실행 결과는 로컬 계약 검증이며 크롬의 실제 음성/연속 재생 3시간 완료와 구분합니다. 임시 폴더는 소유한 tests/.test-tmp 하위임을 확인하고 정리합니다.

근거: [연결 문서/검증 자료](../../../../../development/music/YouTube_로컬_재생_기획과_구현_가이드.md). [정본 차이·남은 연결](../../../../../development/음악_재생_정본_변경_라우팅.md)와 [시즌 필터 검증](../../../../../development/음악_시즌필터_변경_라우팅.md)에서 실제 실행/미실행을 구분합니다.

## AST 심벌

시그니처는 routing-doc-auditor의 구조화 결과를 그대로 사용했습니다. 소스의 함수·클래스 이름/인자/기본값·annotation을 아래와 1:1 대조합니다.

- `LocalPlaybackTests`: class, 소스 18행 / base unittest.TestCase
- `LocalPlaybackTests.setUp`: method, 소스 19행
- `LocalPlaybackTests.tearDown`: method, 소스 33행
- `LocalPlaybackTests.write_source`: method, 소스 41행
- `LocalPlaybackTests.mapping`: method, 소스 47행
- `LocalPlaybackTests.call`: method, 소스 50행
- `LocalPlaybackTests.protected_headers`: method, 소스 63행
- `LocalPlaybackTests.import_payload`: method, 소스 66행
- `LocalPlaybackTests.test_source_roundtrip_and_general_mapping_gate`: method, 소스 69행
- `LocalPlaybackTests.test_missing_or_seasonal_status_never_becomes_playable`: method, 소스 80행
- `LocalPlaybackTests.test_verified_requires_length_evidence_and_real_shape`: method, 소스 86행
- `LocalPlaybackTests.test_batch_is_atomic_and_stale_revision_is_conflict`: method, 소스 92행
- `LocalPlaybackTests.test_idempotent_same_mapping_keeps_version_and_source_change_holds`: method, 소스 102행
- `LocalPlaybackTests.test_http_nonce_and_origin_gate`: method, 소스 110행
- `LocalPlaybackTests.test_get_search_accepts_browser_same_origin_without_origin_header`: method, 소스 117행
- `LocalPlaybackTests.test_static_allowlist_rebinding_and_headers`: method, 소스 124행
- `LocalPlaybackTests.test_optional_search_filters_and_cache_without_real_network`: method, 소스 133행

```python
class LocalPlaybackTests(unittest.TestCase)
LocalPlaybackTests.setUp(self)
LocalPlaybackTests.tearDown(self)
LocalPlaybackTests.write_source(self, row)
LocalPlaybackTests.mapping(self)
LocalPlaybackTests.call(self, method, path, value=None, headers=None)
LocalPlaybackTests.protected_headers(self)
LocalPlaybackTests.import_payload(self, mapping=None)
LocalPlaybackTests.test_source_roundtrip_and_general_mapping_gate(self)
LocalPlaybackTests.test_missing_or_seasonal_status_never_becomes_playable(self)
LocalPlaybackTests.test_verified_requires_length_evidence_and_real_shape(self)
LocalPlaybackTests.test_batch_is_atomic_and_stale_revision_is_conflict(self)
LocalPlaybackTests.test_idempotent_same_mapping_keeps_version_and_source_change_holds(self)
LocalPlaybackTests.test_http_nonce_and_origin_gate(self)
LocalPlaybackTests.test_get_search_accepts_browser_same_origin_without_origin_header(self)
LocalPlaybackTests.test_static_allowlist_rebinding_and_headers(self)
LocalPlaybackTests.test_optional_search_filters_and_cache_without_real_network(self)
```
