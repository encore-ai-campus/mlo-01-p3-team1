# backend/recommendation/youtube_playback.py

- 작성일/수정일: 2026-10-16
- 담당: YouTube 자동 검색 백엔드
- 기준: feature/ad-logic / f22f974
- 소스: `backend/recommendation/youtube_playback.py`

소유 확인을 마친 결과 항목의 메타데이터로만 재생 후보를 제공합니다. 최신 사용자 결정으로 기본 YOUTUBE_PLAYBACK_MODE=KEYLESS는 별도 registry의 검수 완료 대안만 반환하며 기존 snapshot VERIFIED와 공식 검색으로 우회하지 않습니다. LLM 호출과 원본 카탈로그/선곡표 변경이 없습니다. 아래 공식 Data API 검색은 명시 OPTIONAL_SEARCH 분기로 보존합니다.

## 키 없는 기본 경로

resolve_playback_candidates → _keyless_candidates → youtube_registry.track_registry로 연결합니다. LOCAL_DEMO=False는 로컬 저장소에 접근하지 않고 SEARCH_UNAVAILABLE/REGISTRY_NOT_CONFIGURED, 기술 장애는 SEARCH_UNAVAILABLE/REGISTRY_UNAVAILABLE로 멈춥니다. VERIFIED·identity_confirmed·playback_observed·양수 duration을 모두 가진 영상만 READY 후보에 들어가며 source=MAPPING_REGISTRY, match_status=VERIFIED, title/channel은 당시 곡명/아티스트입니다. 요청의 제외 video_id는 다시 반환하지 않습니다.

검수 전/미연결/차단으로 적격 후보가 없으면 status=MAPPING_REQUIRED와 reason=UNMAPPED/PENDING/BLOCKED 및 곡별 mapping_revision을 반환합니다. 공개 플레이어는 이 상태를 건너뛴 곡으로 남기며 전역 매핑 상태를 임의 차단하지 않습니다. 후보 86,485곡·점수·결과·승인 상태는 보존합니다. 운영자 URL/CSV 등록·iframe 검수 경로는 [키 없는 통합 라우팅](../../../../development/YouTube_키없는_등록과_검수_변경_라우팅.md)을 확인합니다.

## 선택 공식 검색 분기

OPTIONAL_SEARCH에서만 기존 메타데이터 VERIFIED 또는 공식 검색 CANDIDATE를 사용합니다. 고정 HTTPS API·한국/삽입/공개/라이브·길이/제목/아티스트/버전 검사, 후보 TTL 캐시·동시 잠금·분/일 검색 보호 한도와 고정 오류는 이 선택 경로에 적용합니다.

[계약 → 코드 → 실행·미실행 연결](../../../../development/YouTube_자동검색_변경_라우팅.md)을 확인합니다.

## AST 시그니처

검사기 `analysis/youtube-resolver-routing-audit.json`의 구조화 symbols를 기록합니다.

```python
class SearchFailure(Exception)
SearchFailure.__init__(self, reason)
class NoRedirect(HTTPRedirectHandler)
NoRedirect.redirect_request(self, request, response, code, message, headers, new_url)
validate_playback_request(body)
_text(value)
_tokens(value)
_duration(value)
_catalog_candidate(track)
_api_json(resource, parameters, api_key)
_match_candidate(track, video)
_search(track, api_key)
_reserve_search(owner_id)
_lookup(track, owner_id, api_key)
resolve_playback_candidates(track, excluded_video_ids=(), owner_id='')
_keyless_candidates(track, excluded_video_ids)
```
