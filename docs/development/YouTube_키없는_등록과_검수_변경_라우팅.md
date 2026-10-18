# API 키 없는 영상 등록·검수와 외부 연속 재생 변경 라우팅

- 작성일/수정일: 2026-10-16
- 담당: C 범위 로컬 구현 / Codex root·백엔드·프런트 협업
- 기준: `feature/ad-logic` / `f22f974` 이후 기존 미완성 변경 보존
- 범위: M-06/A-03·A-04/U-01·U-03의 로컬 재생 연결 예외. 공유 ADMIN·운영 배포 완료가 아닙니다.
- 최신 사용자 결정: 키 없이 URL·CSV 등록/미연결 검수를 구현하고, 후속 선택에 따라 **YouTube 외부 재생 기본·접이식 iframe 보조**를 적용합니다.

## 기준 → 구현

[음악 통합 계약](../product/3차_음악_정책_통합_계약.md)·[추천 가이드](../product/카페_음악_추천_서비스_3차_컬럼_기반_추천_로직_가이드.md)·[공통 계약](../product/3차_공통_개발_계약과_검증_기준.md)을 대조했습니다. 첫 네 제품 문서 전문의 영향 대조는 문서 담당이 수행했습니다. 수령 원문 `docs/handoff/music/`는 이번에 변경하지 않았습니다.

기존에는 immutable 결과의 영상 ID 또는 선택적 Data API 검색으로 중앙 iframe을 자동 준비했습니다. 지금은 별도 로컬 검수 레지스트리를 조회해 외부 대기열 링크를 미리 준비합니다. 새 계정 재생목록을 만들거나 저장하지 않습니다. 원래 음악18개·RDB4테이블·카탈로그·결과·점수·176~184분 검증·전체 GENERAL86,485곡 후보를 유지합니다. 영상 상태를 음악 적격 필터로 사용하지 않습니다.

| 공급/파일 | 실제 변경과 소비 |
|---|---|
| `backend/recommendation/youtube_registry.py` | Git 제외 SQLite, URL/ID 허용 목록, 원자 CSV 등록, track revision, native/iframe 독립 검수·철회·감사 기록 |
| `youtube_review_api.py` | 로컬 코드·CSRF·소유 확인 뒤 목록/등록/검수. 과거 결과의 POST에도 `playlist_id`를 전달하여 본인 snapshot 범위를 유지 |
| `management/commands/init_youtube_review.py` | 코드 값 비출력 초기화, 기존 연결을 iframe CANDIDATE로 수령, 명시 검수된 native 메타데이터 출처만 별도 승계 |
| `youtube_queue_api.py` | `native_queue`와 `YoutubeQueue`: 본인 결과 순서의 native 승인 ID만 임시 외부 링크로 연결. 누락/중복 ID를 숨겨 제거하지 않음 |
| `youtube_playback.py` | KEYLESS 기본에서 iframe 검수 완료 레지스트리만 사용. snapshot native VERIFIED로 우회하거나 원격 검색하지 않음 |
| `backend/cafe/settings.py`·`.env.example` | `YOUTUBE_PLAYBACK_MODE=KEYLESS` 기본. `OPTIONAL_SEARCH`는 명시 선택 이력이며 현행 외부 기본 재생에 필요하지 않음 |
| `backend/cafe/urls.py` | 아래 공개 큐·운영자 검수 경로 연결 |
| `YoutubeNativePlayback.tsx`·`PublicPage.tsx` | 중앙 기본 외부 CTA, 준비 수/부분 목록 명시, iframe은 사용자가 펼칠 때만 마운트. 외부 클릭 시 보조 iframe 정지 |
| `YoutubeReviewPanel.tsx`·`YoutubeReviewPreview.tsx`·`youtubeReview.ts` | 코드 메모리 보관, 현 결과 검색/상태, URL/UTF-8 CSV, 실제 iframe 관측과 수동 외부 재생 확인을 독립 처리 |
| `YoutubePlayer.tsx`·`youtubePlayerController.ts` | iframe 보조의 MAPPING_REQUIRED 누락 기록/다음 진행, 저장소·환경 장애는 보류 |

함수·클래스의 현재 시그니처와 1:1 짝 문서는 [AST 색인](../music-playback-routing/README.md)을 따릅니다.

## API·권한·저장 순서

`GET /api/playlists/{id}/youtube-queue`: owner와 제외 반영 상태를 확인하고 snapshot 곡을 순서대로 조회합니다. 응답은 `playlist_id, tracks[{track_id,video_id,source}], missing[{track_id,track_name,reason}], total_count, ready_count, is_complete, url, queue_kind=TEMPORARY_NATIVE_QUEUE, account_saved=false`입니다. 한 영상이 서로 다른 두 곡을 대신하면 조용히 중복 제거하지 않고 누락 사유로 남깁니다. 준비된 일부만 열면 CTA에 n/m곡을 표시합니다.

`watch_videos?video_ids=...`는 실제 브라우저에서 관측한 YouTube 임시 대기열 경로입니다. 공식 영구 계약·계정 저장 API로 표현하지 않습니다. 실제 수용 곡·순서·광고·자동 재생 여부는 YouTube에서 재확인합니다. 계정 저장 자동화는 OAuth 및 공식 쓰기 API의 별도 범위입니다.

운영자 경로는 `/api/youtube-review/status`, `/tracks`, `/mappings`, `/import`, `/verify`, `/block`, `/native-verify`, `/native-block`입니다. status만 비밀 없이 활성 여부/코드 파일 경로를 알려 줍니다. 나머지는 `LOCAL_DEMO` + `X-Youtube-Review-Code`를 요구하며 POST에는 CSRF를 적용합니다. 코드도 있어야 본인 결과를 조회/수정할 수 있습니다. 공유 ADMIN 어댑터가 없는 운영 환경은503으로 차단합니다.

- 연결 저장: `.local-preview-logs/youtube-mappings.sqlite3`
- 로컬 접근 코드: `.local-preview-logs/youtube-review-access.json` — Git/채팅/문서/브라우저 영구 저장에 값 복사 금지
- URL 등록: `{track_id,video_url,expected_revision,note?,playlist_id}` → CANDIDATE, native 미확인
- CSV: UTF-8/BOM 허용·1MiB·500행, `track_id,video_url,expected_revision,note`. 닫히지 않은 따옴표·헤더·중복·알 수 없는 곡·revision 충돌이면 전체 rollback. 행 오류를 반환하고 입력을 보존
- 검수·철회: revision 조건 검사 후 별도 SQLite 트랜잭션으로 매핑/감사/수정 번호를 함께 저장. 음악/추천/피드백 outbox는 변경하지 않음

iframe VERIFIED는 운영자 원곡 정보 확인·브라우저 PLAYING 보고·양의 관측 길이와 기본 허용차를 요구합니다. 외부 native는 운영자의 실제 YouTube 재생 확인 보고를 별도로 저장합니다. 브라우저 이벤트나 수동 체크를 YouTube 서명·파형 검증·전곡 청취로 주장하지 않습니다.

삽입 오류150으로 `/block`한 영상도 native 승인을 유지할 수 있습니다. `/native-block`은 외부 승인만 철회하며 legacy seed를 재실행해도 복구하지 않습니다. 길이가 다른 공식 영상판의 native 검수만 `duration_difference_confirmed=true` + 비어 있지 않은 메모 + 절대 차60초 이내를 허용하고 `VERIFY_NATIVE_DURATION_DIFFERENCE_ACK`를 남깁니다. iframe 허용차와 원본 duration은 그대로입니다.

## 실행·검증·인계

```powershell
$env:C_LOCAL_DEMO='1'
$env:YOUTUBE_PLAYBACK_MODE='KEYLESS'
.\.venv\Scripts\python.exe -m backend.manage init_youtube_review --seed-legacy --seed-native-reviewed
.\.venv\Scripts\python.exe -m backend.manage runserver 127.0.0.1:8011 --noreload
```

일반 CSV 카탈로그는 먼저 준비되어 있어야 합니다. `.env`는 이 실행기가 자동 로드하지 않습니다. 기존 API가 같은 포트에서 실행 중이면 그 프로세스를 먼저 종료합니다. 실제 키나 Google 비밀번호를 설정할 필요가 없습니다. 코드 회전은 `init_youtube_review --rotate`이며 기존 URL 레지스트리를 삭제하지 않습니다.

백엔드 전체136건·프런트49건과 최종 빌드를 통과했습니다. 독립 검토에서 찾은 과거 결과 POST 범위와 비엄격 CSV 파서를 수정하고 회귀 검증했습니다. [최종 수용 기록](../acceptance/YouTube_키없는_등록과_검수_검증_20261016.md)에 실제 URL/CSV·47개 외부 대기열·자연 전환과 미검증 범위를 남겼습니다.

후속 B/INF 연결은 공유 ADMIN 권한, 공용 매핑 저장소/백업·복구, 운영 접근 제한·관측 로그입니다. 현재 로컬 코드/SQLite를 AWS 운영 인증·정본 음악 저장으로 승격하지 않습니다. 커밋·푸시·PR·배포·계정 쓰기·미디어 다운로드·비공식 검색 수집은 수행하지 않았습니다.
