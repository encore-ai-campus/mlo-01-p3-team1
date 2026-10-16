# backend/recommendation/api.py 라우팅

- 작성일/수정일: 2026-10-16
- 담당: C 공개 대시보드·YouTube 재생 통합
- 범위: 기존 중앙 iframe 재생·LLM 없는 공식 검색·API 연결 후속
- 기준 브랜치/커밋: feature/ad-logic / f22f974
- 소스: [backend/recommendation/api.py](../../../../../backend/recommendation/api.py)

## 기준과 공급·소비

기존 Endpoint가 요청 식별자·CSRF·익명 소유자·공통 오류 형식을 제공하고, 추천/제외/승인/평가 API는 기존 service 경로를 유지합니다. 이번 추가 `YoutubePlayback.post`는 선곡표의 불변 항목을 영상 검색 resolver에 공급하는 공개 대시보드 재생 조회 경로입니다.

`POST /api/playlists/{playlist_id}/youtube-playback` 입력은 `track_id`와 선택 `excluded_video_ids`입니다. 소유자가 일치하는 Playlist를 읽은 뒤 입력을 검증하고 당시 제외 목록과 현재 Family 제외 목록이 다르면 EXCLUSIONS_NOT_APPLIED/409로 보류합니다. 결과 안에 없는 곡과 다른 소유자의 결과는 NOT_FOUND/404입니다. 임의 URL·검색어·키·비밀번호·무제한 제외 ID 입력은 거절합니다.

## 이번 변경과 저장 경계

검증된 결과 항목 → `resolve_playback_candidates(track, excluded_video_ids, owner_id)` → READY/SEARCH_UNAVAILABLE/MAPPING_REQUIRED 등의 상태와 후보를 응답합니다. 최신 기본 KEYLESS에서는 별도 registry의 원곡 확인·실제 iframe PLAYING 보고를 마친 VERIFIED만 사용하고 과거 snapshot VERIFIED·공식 검색으로 우회하지 않습니다. 미연결/검수 전/차단은 MAPPING_REQUIRED와 reason UNMAPPED/PENDING/BLOCKED, 운영/저장 장애는 SEARCH_UNAVAILABLE입니다. 메타데이터는 클라이언트가 덮어쓰지 못하며 당시 곡 snapshot을 보존하고 LLM을 호출하지 않습니다.

기존 공식 검색 CANDIDATE/NO_MATCH/API_KEY_MISSING 분기는 OPTIONAL_SEARCH에서만 보존합니다. 운영자 URL·CSV 입력은 별도 보호된 youtube_review_api의 경로이며 이 공개 조회는 URL·검색어를 받지 않습니다. [키 없는 통합 라우팅](../../../../development/YouTube_키없는_등록과_검수_변경_라우팅.md)을 따릅니다.

이 POST는 Job/Playlist/Family·추천 점수·승인·평가·행사 판정을 변경하지 않습니다. resolver의 분리 캐시·검색 보호 카운터는 사용할 수 있으므로 모든 내부 상태가 불변이라는 뜻은 아닙니다. 재생 실패 후 video_id 제외는 이 조회의 시도 범위이며 음악 곡 제외 이벤트와 구분합니다.

## 검증

신규 API 회귀 6건과 resolver의 단위 검증을 포함한 백엔드 전체 101건이 통과했습니다. 실제 공식 Data API 호출·자동재생 허용·물리적 소리·전곡 완료는 별도이며, 화면 이벤트/실제 재생 관찰은 수용 기록을 따릅니다.

[대시보드 연결 가이드](../../../../development/music/YouTube_로컬_재생_기획과_구현_가이드.md)·[자동 검색 변경 라우팅](../../../../development/YouTube_자동검색_변경_라우팅.md)·[중앙 iframe 수용 기록](../../../../acceptance/대시보드_중앙_YouTube_iframe_검증_20261016.md)을 함께 확인합니다. 수령 원문과 기존 backend-routing은 수정하지 않습니다.

## AST 시그니처

검사 JSON의 python_files[].symbols를 정본으로 기록합니다.

```python
csrf_failure(request, reason='')
exception_handler(exc, context)
class Endpoint(APIView)
Endpoint.initial(self, request, *args, **kwargs)
Endpoint.finalize_response(self, request, response, *args, **kwargs)
Endpoint.owner(self, request)
Endpoint.key(self, request)
class Options(Endpoint)
Options.get(self, request)
class DemoContext(Endpoint)
DemoContext.get(self, request)
class Weather(Endpoint)
Weather.get(self, request)
class Jobs(Endpoint)
Jobs.post(self, request)
class JobDetail(Endpoint)
JobDetail.get(self, request, pk)
class PlaylistDetail(Endpoint)
PlaylistDetail.get(self, request, pk)
class YoutubePlayback(Endpoint)
YoutubePlayback.post(self, request, pk)
class Exclusions(Endpoint)
Exclusions.get(self, request, pk)
Exclusions.put(self, request, pk)
class Regenerate(Endpoint)
Regenerate.post(self, request, pk)
class Approve(Endpoint)
Approve.post(self, request, pk)
class Feedback(Endpoint)
Feedback.get(self, request, pk)
class TrackReaction(Endpoint)
TrackReaction.put(self, request, pk, track_id)
class PlaylistRating(Endpoint)
PlaylistRating.put(self, request, pk)
```
