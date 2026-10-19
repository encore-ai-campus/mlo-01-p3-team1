# backend/recommendation/youtube_queue_api.py 라우팅

## 2026-10-19 수집 URL 공개 연결 — 현행

- 담당: Codex root / U-01·M-06·Q-02 연결 수정
- 브랜치/기준: feature/youtube-url-connection / develop a7dfafb
- 작성/수정: 2026-10-19. 기존 수령 원문은 보존합니다. 아래 앞 단계 서술은 당시 구현 이력이며 이번 절이 현행입니다.
- 계약·전체 검증: [수집 URL 연결 변경 라우팅](../../../../development/수집_URL_공개화면_연결_변경_라우팅.md).

native_queue는 현재 registry를 일괄 조회하고, 외부 승인 영상 우선·미검수 수집 대안 순으로 곡당 영상 하나를 연결합니다. 명시 차단/외부 철회는 제외하되 iframe BLOCKED와 외부 승인이 함께 있으면 외부 승인을 따릅니다. 중복 video_id는 다른 수집 대안으로 대체하거나 DUPLICATE_VIDEO로 표시하며 미수집/차단만 남은 곡은 MAPPING_REQUIRED입니다. 응답에 track_links[{track_id,revision,candidates[{video_id,native_verified}]}]·tracks[].native_verified·unreviewed_count를 추가합니다. 관리자 note/reason/actor와 URL 임의 값은 공개하지 않습니다. 소유/제외 검사를 통과한 본인 결과의 순서를 유지합니다. 검수 상태·불변 추천 결과·카탈로그를 쓰지 않습니다.

### AST 시그니처 — 검사 결과

```python
native_queue(playlist_id, tracks)
class YoutubeQueue(Endpoint)
YoutubeQueue.get(self, request, pk)
```

## 앞 단계 기록

- 작성일/수정일: 2026-10-16
- 담당: 키 없는 음악 통합팀 / 외부 YouTube 큐
- 기준 브랜치/커밋: feature/ad-logic / f22f974
- 소스: `backend/recommendation/youtube_queue_api.py`
- 통합 근거: docs/development/YouTube_키없는_등록과_검수_변경_라우팅.md

## 기준 → 소유 조회 → 외부 임시 큐

최신 사용자 결정으로 기존 대시보드의 기본 음악 재생은 외부 YouTube이며 iframe은 접이식 보조입니다. GET /api/playlists/{playlist_id}/youtube-queue는 기존 익명 소유 문맥으로 본인 결과를 확인하고 LOCAL_DEMO·제외 반영을 검증한 뒤 불변 items 순서와 보조 registry의 native_verified를 연결합니다.

native_queue는 native_verified=true인 대안 중 아직 사용하지 않은 엄격한 11자리 video_id를 선택합니다. iframe status=VERIFIED를 대신 쓰지 않으며 iframe BLOCKED여도 별도 외부 검수 승인이 있으면 사용합니다. 같은 video_id가 두 track에 연결되면 조용히 제거하여 전체 성공으로 표시하지 않고 DUPLICATE_VIDEO로 누락 목록에 남깁니다. 미검수는 NATIVE_REVIEW_REQUIRED입니다.

응답은 playlist_id,tracks[{track_id,video_id,source}],missing[{track_id,track_name,reason}],total_count,ready_count,is_complete,url,queue_kind=TEMPORARY_NATIVE_QUEUE,account_saved=false입니다. url은 준비된 ID의 원래 순서로 만든 https://www.youtube.com/watch_videos?video_ids=...이며 준비된 곡이 없으면 null입니다. 부분 큐는 is_complete=false이고 이용자가 준비된 곡만 별도로 열 수 있도록 화면이 구분합니다.

공식 계정 API·로그인정보·재생목록 저장·검색·스크래핑·LLM·다운로드를 사용하지 않습니다. Job/Playlist·카탈로그/점수·승인·피드백은 보존합니다. 공유 운영 registry/ADMIN·외부 탭의 현재 곡/완료/소리 관측은 별도이며 Django 단위검증을 실제 전곡 3시간 완료로 보고하지 않습니다.

## 검증·인계

오프라인 HTTP 회귀 5건은 순서·불변/검색 없음·계정 저장 아님, 부분/중복의 명시, iframe 검수로 외부 검수 대체 금지, 소유/제외 선검사, 운영 로컬 fallback 금지를 확인합니다. 실제 native 큐 열기·음악/광고·계정/Premium 및 전체 실행 범위는 통합 수용 기록을 따릅니다.

## AST 시그니처

검사기 `.local-preview-logs/keyless-routing-audit.json`의 python_files[].symbols를 기록합니다.

```python
native_queue(playlist_id, tracks)
class YoutubeQueue(Endpoint)
YoutubeQueue.get(self, request, pk)
```
