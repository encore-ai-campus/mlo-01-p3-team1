# API 키 없는 영상 등록·검수와 외부 연속 재생 변경 라우팅

> 각 절의 승인 수·미등록·미검수 상태는 당시 회차의 기록입니다. [공유/로컬 보관 안내](music/YouTube_수집자료_공유와_로컬보관.md)와 [후속 실제 등록·게시 라우팅](./YouTube_새탭_연속재생_변경_라우팅.md)을 함께 확인합니다.

- 작성일: 2026-10-16
- 수정일: 2026-10-19
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

## 후속 추가 100곡 메타데이터 검수·등록 — 2026-10-16

사용자 요청으로 세 팀이 기존 47곡 외 100곡을 병렬 검수했습니다. 공식 더보기의 곡/아티스트/앨범·제공사·버전과 원본 길이를 대조하고, 전곡 청취 대신 각 곡의 짧은 native 시간 진행을 별도로 관측했습니다. [선정·점수·근거·예외와 적용 결과](../../analysis/youtube_mapping_100_20261016/README.md)·[최종 100곡](../../analysis/youtube_mapping_100_20261016/final-100-reviewed.json)·[CSV](../../analysis/youtube_mapping_100_20261016/youtube-additional-100-mappings.csv)를 연결합니다.

기존 등록/외부 승인 함수를 그대로 사용해 로컬 레지스트리에 추가했고 실행 중 API의 누적 검수 완료 147곡을 재조회했습니다. iframe 승인은 기존 11곡, 원래 GENERAL86,485곡과 점수·시간·불변 추천 결과는 보존했습니다. 공식 설명의 정보 점수 85/100은 확률·파형 동일성·청취 적합도 점수가 아닙니다. 공개 KR 포함은 96곡 확인/4곡 미확인으로 구분하고, 공개 HTTP 속도 제한 뒤 추가 직접 요청을 중단했습니다. 앱 코드·화면·API 계약·수령 원문은 바꾸지 않았습니다.

## 후속 URL 1,000개 수집 — 2026-10-18

- 담당·범위: Codex root 및 URL 수집 3팀 / 사용자 요청에 따른 추가 영상 URL 수집만 수행했습니다. 작업 확인 기준은 `develop` / `757edbc`이며 기존 변경은 보존했습니다.
- 기준 → 자료 흐름: 기존 147곡과 알려진 영상 ID를 제외하고, 로컬 GENERAL 86,485곡 카탈로그의 읽기 전용 스냅샷에서 대상을 선정했습니다. [선정 출처·버전·대상 · 로컬 보관](music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_1000_20261018) (`analysis/youtube_urls_1000_20261018/selection.json`) → 팀별 검색 발견 근거와 곡 ID 연결 → 고유 URL 통합 → [URL 전용 TXT · 로컬 보관](music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_1000_20261018) (`analysis/youtube_urls_1000_20261018/youtube-additional-1000-urls.txt`)·[곡 정보 및 검색 출처 CSV · 로컬 보관](music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_1000_20261018) (`analysis/youtube_urls_1000_20261018/youtube-additional-1000-urls.csv`)로 내보냈습니다. 수령 원문과 서비스 코드·함수·API·DB·환경 설정은 변경하지 않았습니다.
- 실제 검증: 별도 로컬 내보내기 도구 `assemble.py --final`로 곡 ID·영상 ID 각 1,000개 고유, 이전 영상 ID와 중복 0개, URL 형식 오류 0개, 검색 발견 근거 누락 0개를 확인했습니다. 내보낸 TXT·CSV를 다시 읽어 각 1,000행과 URL 순서 일치를 확인했습니다. 결과·파일 해시는 [수집 요약](../../analysis/youtube_urls_1000_20261018/collection-summary.json)에 기록했습니다.
- 인계 상태: 전부 `URL_COLLECTED_UNREVIEWED`입니다. 원곡·버전·한국 재생 가능 여부·iframe·실제 재생은 검수하지 않았으며 레지스트리 등록과 대시보드 연결도 수행하지 않았습니다. 이번 수집으로 기존 승인 147곡을 늘리지 않습니다. 추가 검수·등록은 후속 범위이며 커밋·푸시·배포는 수행하지 않았습니다.

## 후속 나머지 URL 수집 — 2026-10-18

- 담당·범위: Codex root 및 공개 자료 수집·대조·독립 검증 팀. 사용자 요청에 따라 이전 1,147곡을 제외한 서비스 GENERAL 카탈로그의 나머지 85,338곡을 URL 수집 대상으로 확장했습니다. 기준 브랜치·커밋은 `develop` / `757edbc`이며 수령 원문은 보존했습니다.
- 기준 → 실제 흐름: [이전 수집 출처 · 로컬 보관](music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_1000_20261018) (`analysis/youtube_urls_1000_20261018/selection.json`)의 로컬 카탈로그 버전과 같은 읽기 전용 스냅샷 및 원본 Spotify CSV를 참조했습니다. [잔여 대상·제외·버전 · 로컬 보관](music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_remaining_20261018) (`analysis/youtube_urls_remaining_20261018/selection.json`) → 전체 잔여 큐 → Kaggle 공식 원본의 Spotify ID 조인·엄격 메타데이터 조인, LAION 고정 revision 5파일의 제목·전체 아티스트·길이 조인, TIMJ 공식 원본의 ID·제목·단일 아티스트 조인 → 곡·영상 조합 중복 제거 → [신규 URL TXT · 로컬 보관](music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_remaining_20261018) (`analysis/youtube_urls_remaining_20261018/youtube-remaining-unique-urls.txt`)·[후보 CSV · 로컬 보관](music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_remaining_20261018) (`analysis/youtube_urls_remaining_20261018/youtube-remaining-url-candidates.csv`)·기존 영상 재사용/미수집 목록으로 분리했습니다. 원천 시점·자료 라이선스·변환·출처 행은 [수집 설명](../../analysis/youtube_urls_remaining_20261018/README.md)과 각 원천 요약에서 확인합니다.
- 실제 결과: 추가 43,167곡에서 고유 신규 영상 URL 48,744개와 곡·영상 조합 53,544개를 확보했습니다. 기존 영상 재사용 후보까지 포함한 곡은 43,220곡이며, 아직 42,118곡은 미수집입니다. 공개 자료에 없거나 일치 조건을 충족하지 못한 곡을 영상 없음으로 확정하거나 임의 URL로 채우지 않았습니다.
- 구현·검증 근거: 별도 Git 제외 수집 도구의 `prepare.py`는 SQLite `mode=ro`로 대상만 읽고, `assemble.py --final`은 출처 키·대상 메타데이터·영상 URL/ID·중복·기존 영상 제외·전체 곡 수 대조 후 TXT/CSV를 다시 읽어 검증했습니다. LAION 42,689개 및 피처링 보완 275개 조합은 실제 Parquet 행으로, TIMJ 6,013개 조합은 원본 TSV 행으로 전수 재조회했습니다. [최종 집계·해시](../../analysis/youtube_urls_remaining_20261018/collection-summary.json)·[독립 출처 무결성 검사](../../analysis/youtube_urls_remaining_20261018/source-integrity-verification.json)에 실제 결과를 기록했습니다. 원천 파싱의 제외·자료 시점·재생시간 미제공은 각 원천 요약에 보존했습니다.
- 남은 연결: `URL_COLLECTED_UNREVIEWED` 후보 수집 단계입니다. 미수집 곡의 추가 검색, 원곡·버전·생존/재생 검수, 승인·등록과 화면 연결은 남아 있습니다. 이번 작업은 서비스 함수/클래스·API·인증·DB/큐·추천 정책·환경 설정을 바꾸지 않았고, 외부 계정·미디어·비밀값·커밋·푸시·배포를 다루지 않았습니다.

## 잔여 42,118곡 계속 수집 — 2026-10-18

- 담당·범위: Codex root와 공개 원천 대조·웹 수집·출처 무결성 확인 팀. 사용자 결정대로 URL 수집만 이어갔으며 음악 검수·승인·등록은 분리했습니다. 기준은 `develop` / `757edbc`입니다. 서비스 코드·DB·수령 원문과 앞선 수집 결과는 보존했습니다.
- 기준 → 실제 흐름: 이전 [미수집 42,118곡 · 로컬 보관](music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_remaining_20261018) (`analysis/youtube_urls_remaining_20261018/remaining-uncollected.csv`)의 해시를 고정하고, 기존 44,367개 곡 ID와 49,893개 영상 ID를 [이번 제외 기준 · 로컬 보관](music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_residual_20261018) (`analysis/youtube_urls_residual_20261018/selection.json`)에 저장했습니다. 잔여 큐 → LAION 원천의 전체 단어·전체 아티스트·명시 참여자·길이 근거별 수집과 공백 보완 → TIMJ/Kaggle 기존 원천 재대조 및 WaveGenAI 공개 메타데이터 대조 → 개별 웹 검색 115곡 시도/100개 후보 → 기존 곡·영상 제외와 고유 곡·영상 조합 통합 → [신규 TXT · 로컬 보관](music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_residual_20261018) (`analysis/youtube_urls_residual_20261018/youtube-residual-new-urls.txt`)·[후보 CSV · 로컬 보관](music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_residual_20261018) (`analysis/youtube_urls_residual_20261018/youtube-residual-new-candidates.csv`)·[최신 미수집 목록 · 로컬 보관](music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_residual_20261018) (`analysis/youtube_urls_residual_20261018/remaining-uncollected.csv`)으로 내보냈습니다.
- 실제 결과: 추가 10,410곡, 고유 신규 영상 URL 12,040개, 고유 곡·영상 조합 13,266개입니다. 원천 조합 13,271개에서 원천 간 중복 5개를 제거했고 기존 수집 곡·영상과의 중복은 0입니다. 아직 31,708곡은 미수집이며 개별 검색 전체를 완료한 것으로 표시하지 않았습니다.
- 수집 함수·검증: 별도 Git 제외 `youtube_residual/prepare.py`가 이전 산출물만 읽어 제외 기준을 만들고, `laion_residual_collect.py::match_target_source()`와 `compact_collect.py::match_target_source()`는 원문·버전 단어를 보존한 후보 조건만 반환합니다. `assemble.py --final`에서 대상/원천 키·URL/ID·실제 검색 근거 튜플·기존 자료와의 중복·TXT/CSV 재조회·전체 곡 수 합계를 확인했습니다. 원천 행 재조회와 최종 산출물 집계는 별도 [출처 무결성 확인](../../analysis/youtube_urls_residual_20261018/source-integrity-verification.json)에 기록합니다. [집계·해시](../../analysis/youtube_urls_residual_20261018/collection-summary.json)·[범위·원천·변환·인계 설명](../../analysis/youtube_urls_residual_20261018/README.md)을 연결합니다.
- 인계 상태: 모든 후보는 `URL_COLLECTED_UNREVIEWED`입니다. 길이 차이 1,087개 조합, 공백·구분자 보완 177개 조합과 짧은 식별자 위험을 별도 필드로 남겼고 같은 녹음·같은 버전으로 확정하지 않았습니다. 신규 미수집 목록의 추가 검색과 이후 음악/재생 검수·등록·대시보드 연결은 남아 있습니다. 이번 작업으로 승인 147곡이나 앱 함수/클래스·API·인증·DB/큐·추천 정책·환경·외부 계정 상태를 바꾸지 않았으며 커밋·푸시·PR·배포도 수행하지 않았습니다.

<!-- youtube-tail-31708-20261018:start -->
## 잔여 31,708곡 계속 수집 — 2026-10-18

- 작성/수정: 2026-10-18. 담당·범위: Codex root와 공개 원천·웹 수집·독립 출처 대조 팀. 사용자 요청대로 URL 수집만 진행했습니다. 기준 브랜치/커밋은 `develop` / `757edbc`입니다. 새 수령 원문은 수정하지 않았으며, 기존 카탈로그와 앞선 수집 산출물을 읽기 전용 기준으로 사용했습니다.
- 기준 → 실제 흐름: 이전 [미수집 31,708곡 · 로컬 보관](music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_residual_20261018) (`analysis/youtube_urls_residual_20261018/remaining-uncollected.csv`)의 SHA256을 고정하고, 기존 54,777곡/61,933개 영상 ID를 [제외 기준 · 로컬 보관](music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_tail_20261018) (`analysis/youtube_urls_tail_20261018/selection.json`)에 보존했습니다. 잔여 전체 큐 → LAION 고정 5파일의 명시 크레딧/동일 제목 반복·라틴 악센트·동일 연도 remaster 표기 보완과 별도 길이 차 후보 대조 → YouNiverse 보존 prefix의 실제 완전한 JSONL 행 대조 → 곡별 공개 웹 검색 → 기존 곡/영상 제외 및 출처 간 곡·영상 조합 중복 제거 → [신규 URL TXT · 로컬 보관](music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_tail_20261018) (`analysis/youtube_urls_tail_20261018/youtube-tail-new-urls.txt`)·[후보 CSV · 로컬 보관](music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_tail_20261018) (`analysis/youtube_urls_tail_20261018/youtube-tail-new-candidates.csv`)·[최신 미수집 목록 · 로컬 보관](music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_tail_20261018) (`analysis/youtube_urls_tail_20261018/remaining-uncollected.csv`)으로 내보냈습니다.
- 실제 결과: 추가 **2,637곡 / 고유 신규 영상 URL 2,632개 / 고유 곡·영상 조합 2,715개**입니다. 기존 곡·영상 중복은 각각 0개이며, 누적 57,414곡과 미수집 **29,071곡**을 합치면 GENERAL 86,485곡과 일치합니다. 개별 검색 시도는 1,917곡, 정상 검색 완료는 1,910곡으로 구분했고 제한/오류 재시도는 완료 처리하지 않았습니다. 전체 31,708곡 수집 완료로 표시하지 않았습니다.
- 수집 도구: 별도 Git 제외 `youtube_tail/prepare.py`가 이전 입력과 제외 ID 집합을 고정합니다. `explicit_credit_collect.py::match_target_source()`, `latin_diacritic_collect.py::match_target_source()`, `remaster_order_collect.py::match_target_source()`, `latin_duration_collect.py::match_target_source()` 및 `youniverse_collect.py::match_title()/duration_flag()`가 원천 근거로 미검수 URL 후보만 반환합니다. `auto_batch.py`와 `part*_append.py`는 겹치지 않는 검색 대상·실제 발견 행·증거를 저장하며 기존 영상 참조는 신규 URL로 집계하지 않습니다. `assemble.py --final`은 출처 키·대상 곡·URL/ID·웹 evidence 튜플·기존 중복·재시도 상태·전체 합계를 확인하고 TXT/CSV를 재조회합니다. 이들은 로컬 자료 작업 도구이며 서비스 함수/클래스·API·인증/소유·DB/큐·추천 정책·환경 설정을 바꾸지 않습니다.
- 근거·제한: LAION의 원본 파일 hash와 실제 행 필드, YouNiverse 보존 prefix hash/후보 행, 검색 발견 튜플과 자동 수집 원발견 batch, 최종 파일 hash/분할 합계를 [독립 수집 무결성 확인](../../analysis/youtube_urls_tail_20261018/source-integrity-verification.json)에 기록합니다. [집계·파일 hash](../../analysis/youtube_urls_tail_20261018/collection-summary.json)·[원천/변환/인계 설명](../../analysis/youtube_urls_tail_20261018/README.md)을 연결합니다. YouNiverse는 원천 전체 중 130,023,424바이트의 prefix만 보존했고, 전체 다운로드·checksum 확인은 미완료로 남깁니다. 부분 원천을 전체 파일 검증 완료로 승격하지 않습니다.
- 인계 상태: 전부 `URL_COLLECTED_UNREVIEWED`이며 악센트·제한 범위 길이 차·짧은 식별자·공동 아티스트 미확인 등의 후보 한계를 보존합니다. 원곡/버전·생존/한국 재생/iframe/실제 재생 검수와 승인·등록·대시보드 연결은 후속입니다. 미수집 대상의 추가 검색과 재시도도 남아 있습니다. 앞선 수집 TXT/CSV/미수집 입력의 hash는 보존 확인했고, 기존 승인 147곡·추천 결과·수령 원문·외부 계정은 변경하지 않았습니다. 커밋·푸시·PR·배포는 수행하지 않았습니다.
<!-- youtube-tail-31708-20261018:end -->

<!-- youtube-next-29071-20261018:start -->
## 잔여 29,071곡 계속 수집 — 2026-10-18

- 작성/수정일 2026-10-18. 담당은 Codex root와 공개 원천·웹 수집·독립 근거 대조 팀입니다. 범위는 사용자 요청의 URL 수집이며 기준 브랜치/커밋은 `develop` / `757edbc`입니다. 수령 원문 수정 없이 기존 카탈로그·수집 산출물을 읽기 전용 기준으로 사용했습니다.
- 기준 → 실제 흐름: [이전 미수집 29,071곡 · 로컬 보관](music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_tail_20261018) (`analysis/youtube_urls_tail_20261018/remaining-uncollected.csv`) SHA256을 고정하고 기존 57,414곡/64,565영상 ID를 [제외 기준 · 로컬 보관](music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_next_20261018) (`analysis/youtube_urls_next_20261018/selection.json`)에 보존했습니다. 전체 큐 → LAION 5개 고정 메타데이터의 명시 표기/전체 제목/크레딧 대조 → YouNiverse 영상 prefix와 채널 원천 조인 → 겹치지 않는 곡별 공개 검색 → 기존 곡/영상 제외·출처 간 조합 통합 → [신규 URL TXT · 로컬 보관](music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_next_20261018) (`analysis/youtube_urls_next_20261018/youtube-next-new-urls.txt`)·[곡/영상 CSV · 로컬 보관](music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_next_20261018) (`analysis/youtube_urls_next_20261018/youtube-next-new-candidates.csv`)·[미수집 목록 · 로컬 보관](music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_next_20261018) (`analysis/youtube_urls_next_20261018/remaining-uncollected.csv`)으로 내보냈습니다.
- 실제 결과: **추가 2,438곡 / 고유 신규 영상 URL 2,404개 / 조합 2,523개**, 기존 곡·영상 중복 각각 0개입니다. 누적 59,852곡 + 미수집 **26,633곡** = GENERAL 86,485곡입니다. 개별 검색 1,848곡 중 정상 완료 1,841곡, 미수집 재시도 대상 7곡을 구분했습니다. 전체 수집 완료는 아닙니다.
- 변경 도구/이유: 별도 Git 제외 `youtube_next/prepare.py`가 이전 산출물 hash와 기존 ID를 고정합니다. `orthographic_collect.py::match_target_source()`와 `orthographic_fulltitle_collect.py::match_target_source()`는 명시 라틴 표기 보완 후 전체 제목/아티스트·버전·길이를 유지한 미검수 후보만 반환합니다. `primary_missing_credits_collect.py::match_target_source()`는 제목/주 아티스트·3초 이내 길이와 원천 아티스트 진부분집합을 요구하고 누락 공동 크레딧을 미확인으로 보존합니다. 새 YouNiverse 수집 도구는 영상의 명시 아티스트/제목 또는 채널 전체 아티스트명과 제목을 대조하고 원천 행·부분 checksum 상태를 보존합니다. `auto_batch.py`·`part*_append.py`는 대상 분리·실제 검색 발견·증거 저장과 기존 영상 제외를 처리합니다. `assemble.py --final`은 원천별 후보·웹 evidence·baseline·누적 검색/재시도·전체 분할을 확인하고 CSV/TXT를 재조회합니다. 서비스 함수/클래스·API·인증/소유·DB/큐·실행 환경 계약은 바꾸지 않았습니다.
- 검증/근거: 원천 실제 행과 원본 파일 hash, 영상 prefix hash/실제 행과 채널 전체 MD5/행, 실제 검색 발견 튜플·batch·최종 hash/집계를 [수집 무결성 확인](../../analysis/youtube_urls_next_20261018/source-integrity-verification.json)에 기록합니다. [집계·해시](../../analysis/youtube_urls_next_20261018/collection-summary.json)와 [원천·규칙·인계 설명](../../analysis/youtube_urls_next_20261018/README.md)을 함께 확인합니다. YouNiverse 영상은 4,294,967,296바이트의 부분 파일이며 전체 13,636,127,630바이트 다운로드/MD5 확인은 미완료입니다. 채널 파일 전체 검증과 혼동하지 않습니다.
- 검증 실행: 호환 Python으로 `python .local-preview-logs/youtube_next/verify_orthographic.py`, `python .local-preview-logs/youtube_next/assemble.py --final`, `python .local-preview-logs/youtube_next/independent_export_verify.py`, `python .local-preview-logs/youtube_next/preservation.py --verify`를 수행했습니다. 개별 원천 행/규칙 대조와 독립 내보내기 확인은 각 JSON report의 실제 결과를 따릅니다. [이전 파일 보존 · 로컬 보관](music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_next_20261018) (`analysis/youtube_urls_next_20261018/prior-files-preservation.json`)도 함께 남깁니다. 서비스 동작·통합 재생 검증은 이번 범위에서 실행하지 않았습니다.
- 실행 환경 보완: 기본 Python 3.14에서 Parquet 확인 도구를 처음 실행했을 때 기존 pyarrow native 모듈을 읽지 못해 `ModuleNotFoundError: pyarrow.lib`로 실패했습니다. 데이터나 전역 설치를 바꾸지 않고 bundled Python 3.12.14로 재실행해 실제 원천 행/규칙 대조를 통과했습니다.
- 추가 수집 함수: `album_artist_subset_collect.py::match_target_source()`는 전체 제목/앨범·3초 이내 길이·대상 참여자 진부분집합을 요구하고, 원천에서 빠진 주/공동 아티스트를 미확인으로 보존합니다. `youniverse_collect.py::download_prefix()/load_targets()/match_title()/duration_flag()/parse()`와 `youniverse_channel_collect.py::channel_variants()/complete_channel_artists()/prepare()/collect()/verify()`가 영상 부분 원천·채널 조인 근거를 저장합니다. 원천 다운로드/대조와 서비스 등록·승인·재생은 별개입니다.
- 표기 보완·원천 확인 함수: `compact_album_collect.py::match_target_source()`는 전체 제목/전체 아티스트 canonical 문자 일치와 공백 경계 차이, 전체 앨범·3초 이내 길이를 요구하고 경계 검수 필요 표시를 보존합니다. `youniverse_prefix_verify.py::main()`은 저장 영상 prefix/실제 후보 행만 대조하며 전체 영상 파일 checksum 완료로 승격하지 않습니다.
- 남은 연결: 전부 `URL_COLLECTED_UNREVIEWED`입니다. 표기·길이 차·채널 이름·주 아티스트만 확인한 후보의 한계를 보존했습니다. 미수집 추가 검색/재시도, 원곡/버전·생존/한국 재생/iframe/실제 재생 검수·승인/등록·대시보드 연결은 후속입니다. 이전 수집 결과 hash는 보존 확인했고 기존 승인/추천/레지스트리·수령 원문은 변경하지 않았습니다. 커밋·푸시·PR·배포는 수행하지 않았습니다.
<!-- youtube-next-29071-20261018:end -->

<!-- youtube-continue-26633-20261018:start -->
## 잔여 26,633곡 계속 URL 수집 — 2026-10-18

- 작성/수정일 2026-10-18. 담당은 Codex root와 공개 원천·웹 수집·독립 대조 팀이며 범위는 사용자 요청의 **수집만**입니다. 기준 브랜치/커밋은 `develop` / `757edbc`입니다. 기존 음악 카탈로그와 앞선 수집 결과는 읽기 전용 기준이며 수령 원문은 수정하지 않았습니다.
- 기준 → 실제 흐름: [부모 미수집 26,633곡 · 로컬 보관](music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_next_20261018) (`analysis/youtube_urls_next_20261018/remaining-uncollected.csv`) SHA256 `53e5e3bf6f708e6840eeae5228cd52fcc4c526a044f395b5e63c2808b80b6921`을 고정하고, 기존 59,852곡/66,969영상 ID를 [제외 기준 · 로컬 보관](music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_continue_20261018) (`analysis/youtube_urls_continue_20261018/selection.json`)에 저장했습니다. [전체 큐 · 로컬 보관](music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_continue_20261018) (`analysis/youtube_urls_continue_20261018/continuation-queue.csv`) → LAION 고정 5파일의 제목/앨범/크레딧/길이 대조·YouNiverse 저장 prefix/채널 조인·곡별 공개 검색 → 기존 곡/영상 제외와 조합 병합 → [URL TXT · 로컬 보관](music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_continue_20261018) (`analysis/youtube_urls_continue_20261018/youtube-continue-new-urls.txt`)·[곡/영상 CSV · 로컬 보관](music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_continue_20261018) (`analysis/youtube_urls_continue_20261018/youtube-continue-new-candidates.csv`)·[미수집 목록 · 로컬 보관](music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_continue_20261018) (`analysis/youtube_urls_continue_20261018/remaining-uncollected.csv`)으로 내보냈습니다.
- 실제 결과: **추가 1,315곡 / 고유 신규 영상 URL 1,315개 / 곡·영상 조합 1,315개**, 기존 곡·영상 중복 각각 0개입니다. 누적 61,167곡 + 미수집 **25,318곡** = GENERAL 86,485곡입니다. 전체 수집 완료가 아닙니다. 개별 검색 2,188곡 중 정상 완료 2,188곡이며 미수집 재시도 대상 0곡을 구분했습니다.
- 변경 도구·이유: Git 제외 `youtube_continue/prepare.py`가 부모 산출물 hash와 기존 ID/누적 이력을 고정합니다. `primary_album_duration_collect.py::match_target_source()`는 전체 제목/버전·앨범·주 아티스트 일치, 원천 아티스트 진부분집합과 3초 초과 bounded 길이 조건을 요구하고 누락 크레딧/길이 차를 미확인으로 남깁니다. `unlabelled_remaster_collect.py::separate_remaster()/match_target_source()`는 한쪽 누락 terminal 리마스터 표시만 별도 후보로 분리하고 전체 나머지 제목·모든 아티스트·앨범·3초 이내 길이를 요구하며 동일 버전/원음원 미확인 표시를 보존합니다. 양쪽의 서로 다른 리마스터 라벨·다른 버전은 같게 만들지 않습니다. `youniverse_collect.py::download_prefix()/load_targets()/match_title()/duration_flag()/parse()`와 `youniverse_channel_collect.py::prepare()/collect()/verify()`는 실제 저장 영상 prefix와 전체 채널 파일의 증거를 저장합니다. `auto_batch.py`·분할 검색 append helper는 입력 분리·실제 URL/검색 증거와 중복 제외를 처리합니다. `assemble.py --final`은 후보 원천/evidence·baseline·누적 검색/재시도·전체 분할을 확인한 뒤 CSV/TXT를 재조회합니다.
- 검증/실행 근거: `python .local-preview-logs/youtube_continue/assemble.py --final`, 호환 Python 3.12로 `verify_album_duration.py`·`independent_export_verify.py`, `python .local-preview-logs/youtube_continue/preservation.py --verify`를 실행했습니다. 실제 원천 행·검색 발견 튜플·최종 hash/집계는 [출처/내보내기 대조](../../analysis/youtube_urls_continue_20261018/source-integrity-verification.json), [집계](../../analysis/youtube_urls_continue_20261018/collection-summary.json), [이전 파일 보존 · 로컬 보관](music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_continue_20261018) (`analysis/youtube_urls_continue_20261018/prior-files-preservation.json`)에 기록합니다. [조건·출처·후속 인계](../../analysis/youtube_urls_continue_20261018/README.md)를 함께 확인합니다. YouNiverse 영상 메타데이터 파일 `yt_metadata_en.jsonl.gz`는 6,442,450,944바이트 부분 prefix이며 전체 13,636,127,630바이트/공식 MD5 확인 미완료입니다. 채널 파일의 전체 checksum 확인과 혼동하지 않습니다.
- 이전 대비: 부모의 누적 검색 이력과 부모 continuation 위치를 보존하며, 이번 실제 정상 검색으로만 이전 재시도 상태를 해제합니다. 단순 사전 건너뛰기를 검색 완료로 집계하지 않습니다. 새 후보는 모두 `URL_COLLECTED_UNREVIEWED`이며 곡/재생 승인으로 승격하지 않습니다. 수집 범위의 변화는 별도 후보/원천 파일에만 기록합니다.
- 남은 연결: 미수집 곡 추가 검색/재시도와 원곡/버전·URL 생존/한국 재생/iframe/실제 재생 검수·승인/등록은 후속입니다. 이번에는 서비스 함수/클래스·API·인증/소유·DB/큐·실행 환경·추천·운영 레지스트리·대시보드·수령 원문을 변경하지 않았습니다. 통합 재생 검증·커밋·푸시·PR·배포·외부 계정 변경은 수행하지 않았습니다.
<!-- youtube-continue-26633-20261018:end -->


<!-- youtube-followup-25318-20261018:start -->
## 잔여 25,318곡 URL 추가 수집 — 2026-10-18

- 작성/수정일 2026-10-18, 담당 Codex root, 범위는 최신 사용자 요청의 **URL 수집만**입니다. 기준 브랜치/커밋은 `develop` / `757edbc`입니다. 수령 원문·기존 음악 카탈로그·앞선 수집 산출물은 보존했습니다.
- 기준 → 실제 흐름: [부모 미수집 목록 · 로컬 보관](music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_continue_20261018) (`analysis/youtube_urls_continue_20261018/remaining-uncollected.csv`)의 SHA256 `d37e1fbabd883b1f1dc5832cf366de9619614134e782e2441b58942992fa14fa`을 고정했습니다. [별도 입력 큐와 제외 기준 · 로컬 보관](music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_followup_20261018) (`analysis/youtube_urls_followup_20261018/selection.json`)에서 기존 61,167곡·68,284영상 ID와 누적 검색/부모 위치를 보존했습니다. 서로 다른 곡의 공개 검색과 공개 메타데이터 처리 → 기존·이번 곡/영상 중복 제외 → [후보 CSV · 로컬 보관](music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_followup_20261018) (`analysis/youtube_urls_followup_20261018/youtube-followup-new-candidates.csv`)·[URL TXT · 로컬 보관](music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_followup_20261018) (`analysis/youtube_urls_followup_20261018/youtube-followup-new-urls.txt`)·[미수집 목록 · 로컬 보관](music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_followup_20261018) (`analysis/youtube_urls_followup_20261018/remaining-uncollected.csv`)으로 저장합니다.
- 실제 결과: 추가 **1,008곡 / 고유 신규 영상 URL 1,008개 / 조합 1,008개**, 기존 곡·영상 중복 각각 0개입니다. 누적 62,175곡 + 미수집 **24,310곡** = GENERAL 86,485곡입니다. 전체 수집 완료로 표시하지 않습니다. 실제 검색 2,092곡·정상 완료 2,092곡, 미수집 중 검색 오류/제한 재시도 0곡입니다. 전부 `URL_COLLECTED_UNREVIEWED`입니다.
- 변경 도구·동작: Git 제외 `.local-preview-logs/youtube_followup/prepare.py`가 부모 해시·기존 ID·누적 이력을 고정하고, `auto_search_runner.js::runBatch()`가 공개 검색의 실제 URL/제목·검색어·시도를 기록합니다. `auto_batch.py::existing_rows()/next/ingest`가 이미 확보한 곡/영상과 검색 이력을 제외하고 원발견·증거를 저장합니다. `youniverse_collect.py::download_prefix()/parse()`와 `youniverse_channel_collect.py::collect()`가 실제 받은 메타데이터 prefix 및 전체 채널 파일에서 후보를 추출합니다. 조기 EOF 뒤 정상 이어받기 한 번과 속도 저하에 따른 세션 종료·받은 범위 보존은 `source_resume.py`·`freeze_received_source.py`에 남겼습니다. `finalize_sources.py`가 출처 사이 중복을 제외하고, `assemble.py`가 CSV/TXT와 누적 이력·미수집 분할을 내보냅니다. 이전 대비 추가 수집 범위와 출력만 새 디렉터리에 기록하며 입력/기존 산출물을 덮어쓰지 않습니다.
- 원천 한계: YouNiverse 영상 메타데이터는 실제 **6,753,768,064바이트·완전 JSONL 36,302,124행**의 부분 prefix입니다. 요청한 8GiB 완료·전체 13,636,127,630바이트/공식 MD5 확인은 미완료입니다. 채널 파일 전체 checksum 확인과 구분하며 원천·길이/크레딧·제목 조건 및 미확인 표시는 [이번 README](../../analysis/youtube_urls_followup_20261018/README.md)에 기록했습니다.
- 검증·인계 근거: `python -X utf8 .local-preview-logs/youtube_followup/finalize_sources.py`, `assemble.py --final`, `independent_export_verify.py`, `preservation.py --verify`, `verify_documents.py`를 실행했습니다. [출처/내보내기 대조](../../analysis/youtube_urls_followup_20261018/source-integrity-verification.json)·[집계/해시](../../analysis/youtube_urls_followup_20261018/collection-summary.json)·[이전 파일 보존 · 로컬 보관](music/YouTube_수집자료_공유와_로컬보관.md#youtube_urls_followup_20261018) (`analysis/youtube_urls_followup_20261018/prior-files-preservation.json`)에서 실제 발견 튜플·원천 행/수집 규칙·파일 해시·전체 분할을 확인했습니다. 이는 음악·원음원/버전·청취·URL 생존/한국 재생/iframe 검수와 구분됩니다.
- 남은 연결: 미수집 곡 추가 수집과 검수·승인·등록은 후속입니다. 서비스 함수/클래스·API·인증/소유·DB/큐·운영 레지스트리·추천·대시보드·수령 원문은 변경하지 않았습니다. 통합 재생 검증·커밋·푸시·PR·배포·계정 변경도 하지 않았습니다.
<!-- youtube-followup-25318-20261018:end -->
