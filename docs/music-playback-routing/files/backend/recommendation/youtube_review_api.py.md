# backend/recommendation/youtube_review_api.py 라우팅

- 작성일/수정일: 2026-10-16
- 담당: API 키 없는 YouTube 등록·검수 백엔드 / 통합팀
- 기준 브랜치/커밋: feature/ad-logic / f22f974
- 소스: `backend/recommendation/youtube_review_api.py`
- 통합 근거: docs/development/YouTube_키없는_등록과_검수_변경_라우팅.md

## 기준 → API → 저장

기존 Endpoint의 CSRF·request_id·no-store·도메인 오류 계약을 사용합니다. /status는 기능 여부와 로컬 접근코드 파일 경로만 공개하며 값을 반환하지 않습니다. 나머지 검수 read/write는 LOCAL_DEMO 및 X-Youtube-Review-Code를 확인합니다. 운영에서는 공유 ADMIN 어댑터 미연결을 503으로 반환합니다.

| 경로 | 입력·처리·결과 |
|---|---|
| GET /api/youtube-review/status | enabled,is_test,access_code_file. 비밀 코드값 없음. |
| GET /api/youtube-review/tracks | playlist_id가 있으면 본인 결과 items, 없으면 최신 일반 카탈로그. q·status ALL/UNMAPPED/PENDING/VERIFIED/BLOCKED·page·page_size(최대 100) 필터. items에 곡 정보·곡별 revision·대안 mappings·state, summary에 total/unmapped/pending/verified/blocked. |
| POST /api/youtube-review/mappings | track_id,video_url,expected_revision,note 선택. 실제 곡 존재 확인 후 registry.register_mappings. 등록은 CANDIDATE이며 검수 완료가 아닙니다. |
| POST /api/youtube-review/import | csv_text 및 선택 playlist_id. CSV/곡 존재 전체 검증 후 한 번에 적용, 실패 시 전부 보존. details.row_errors는 헤더를 1행으로 센 실제 행 번호입니다. |
| POST /api/youtube-review/verify | track_id,video_id,expected_revision,identity_confirmed=true,playback_observed=true,duration_seconds,note 선택. 당시 원본 길이와 보고 관측 검증 후 VERIFIED. |
| POST /api/youtube-review/block | track_id,video_id,expected_revision,reason. 운영자 명시 변경만 BLOCKED, 공개 이용자의 개별 iframe 오류는 자동 전역 차단하지 않습니다. |
| POST /api/youtube-review/native-verify | track_id,video_id,expected_revision,identity_confirmed=true,playback_observed=true,duration_seconds,note 선택,duration_difference_confirmed 선택 bool. 외부 실제 재생의 운영자 수동 보고이며 iframe 검수와 독립입니다. 표준 길이 초과는 명시 flag·비고·차이 60초 이내만 허용하고 원본 길이는 보존합니다. |
| POST /api/youtube-review/native-block | track_id,video_id,expected_revision,reason. native 승인만 철회하고 native_reason을 보존하며 iframe 상태는 유지합니다. |

_body/_positive_int는 입력 제한, _scope/_known_tracks는 일반 카탈로그 또는 본인 결과의 곡 확인, _state는 대안의 우선 상태, ReviewEndpoint.authorize는 코드 및 기존 익명 소유 문맥을 담당합니다. _state의 VERIFIED는 native_verified 또는 iframe VERIFIED 중 하나가 준비된 곡이며 상세 방식별 상태는 mapping 필드로 구분합니다. POST에는 선택 playlist_id를 사용할 수 있으며 결과 소유 검사를 우회하지 않습니다. 임의 곡 생성·음악 카탈로그 변경·LLM·외부 검색·media 다운로드를 수행하지 않습니다.

## 검증·인계

API 10건은 접근코드·CSRF·소유·원자 CSV·잘못된 따옴표 전체 거절·과거 본인 결과의 곡 등록과 타인 차단·동시 수정·상태 전환·외부/iframe 승인·철회 독립·업무 카탈로그 보존·운영 503을 확인했습니다. 로컬 접근코드 경계는 공유 ADMIN 완료 근거가 아닙니다. 실제 화면·iframe·청취 관찰은 통합 기록의 범위를 따릅니다.

## AST 시그니처

검사기 `.local-preview-logs/keyless-routing-audit.json`의 python_files[].symbols를 그대로 기록합니다.

```python
_body(body, allowed, required=())
_positive_int(value, default, maximum)
_scope(request, owner)
_known_tracks(request, owner, ids)
_state(mappings)
class ReviewEndpoint(Endpoint)
ReviewEndpoint.authorize(self, request)
class ReviewStatus(Endpoint)
ReviewStatus.get(self, request)
class ReviewTracks(ReviewEndpoint)
ReviewTracks.get(self, request)
class ReviewMappings(ReviewEndpoint)
ReviewMappings.post(self, request)
class ReviewImport(ReviewEndpoint)
ReviewImport.post(self, request)
class ReviewVerify(ReviewEndpoint)
ReviewVerify.post(self, request)
class ReviewBlock(ReviewEndpoint)
ReviewBlock.post(self, request)
class ReviewNativeVerify(ReviewEndpoint)
ReviewNativeVerify.post(self, request)
class ReviewNativeBlock(ReviewEndpoint)
ReviewNativeBlock.post(self, request)
```
