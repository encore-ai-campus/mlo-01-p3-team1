# 수집 CSV URL의 공개 화면·외부 선곡표 연결 변경 라우팅

- 작성일/수정일: 2026-10-19
- 담당: Codex root. 범위: U-01 외부 URL 연결·M-06 검수 자료 연결·Q-02 회귀. 담당자를 새로 배정하지 않습니다.
- 브랜치/기준: `feature/youtube-url-connection`, 최신 develop `a7dfafb`에서 분기. root feature/ad-logic·SourceTree의 타 작업 브랜치는 보존합니다.
- 기준: 제품 기능/흐름·구현 설계도·ON/OFF 로직 가이드·3차 구현 태스크의 2026-10-19 버전. 수령 `docs/handoff/music/음악_분류_컬럼_정의.md`는 a7dfafb 그대로 보존합니다.
- 최신 사용자 결정: “미검수 영상까지 전부 플레이리스트에 들어가도록”. 앞 단계의 native 승인 영상 전용 큐 제한을 대체하되 실제 검수·승인은 자동 변경하지 않습니다.

## 문제와 변경 전후

AWS `https://d55cemi1yl53l.cloudfront.net/playlist`에서 생성한 44곡의 곡별 버튼이 모두 `results?search_query=`를 열었습니다. 기존 개별 버튼은 불변 선곡표/카탈로그에 있던 youtube_video_id·youtube_match_status만 사용하고, 실제 CSV 수집/운영 검수는 별도 registry로 관리돼 현재 매핑이 개별 버튼에 반영되지 않았습니다. 중앙 큐는 registry를 읽지만 native 승인만 허용해 1/44곡만 준비로 표시됐습니다. 이는 현재 운영 화면의 재현이며 AWS 공유 DB의 전체 수집 행 수를 직접 조회한 것은 아닙니다.

변경 후 본인 선곡표 큐가 현재 registry의 수집 대안·외부 검수 여부를 함께 반환합니다. 곡별 버튼은 수집 영상의 공식 watch URL을 열고 미검수를 표시하며, 대안 URL도 접어서 제공합니다. 큐는 외부 승인 우선→미검수 후보 순으로 곡당 하나를 선택해 원래 순서를 유지합니다. 미수집·명시 차단/외부 철회·중복 영상만 남는 곡은 누락에 표시합니다. iframe BLOCKED라도 별도 native 승인이 있으면 사용할 수 있으며, native 철회는 iframe 승인만으로 복원하지 않습니다. 영상이 없는 곡을 추천 결과에서 삭제하거나 임의 URL을 채우지 않습니다.

## 기준 → 코드·API·저장 → 검증

| 기준/역할 | 실제 변경 파일·함수 | 연결·이유 |
|---|---|---|
| 수집 CSV·별도 검수 계약 | `backend/recommendation/youtube_registry.py::track_registries` | 요청 곡 ID만 500개 단위·한 연결로 읽습니다. 로컬 SQLite/운영 Django DB 어댑터를 유지합니다. 기존 단일 조회·등록/승인/철회 함수는 보존합니다. |
| 본인 결과 소유·외부 선곡표 | `youtube_queue_api.py::native_queue`, `YoutubeQueue.get` | 소유·제외 반영 검사를 먼저 실행합니다. 현재 매핑으로 공개 링크/미검수 포함 큐를 만들며 DB write는 하지 않습니다. |
| 개별 곡 직접 연결 | `youtubeDestinations.ts::checkedTrackLinks`, `youtubeTrackDestination` | 본인 결과 순서·곡 ID·revision·최대 10개 고유 영상 ID·bool을 검증합니다. 공식 watch URL을 ID에서 직접 구성합니다. 빈 최신 매핑이 옛 VERIFIED 필드를 덮도록 해 철회를 보존합니다. |
| 화면 연결/대안 | `YoutubeLinks.tsx::YoutubeTrackLink`, `YoutubeLinks.css` | 직접 연결·미검수·미수집 검색과 대안을 구분하고 새 탭/클릭 격리를 유지합니다. 제외한 곡은 연결하지 않습니다. |
| 응답·갱신 수명 | `YoutubeNativePlayback.tsx::YoutubeNativePlayback`, `checkedNativeQueueHref`, `YoutubeNativeQueueView` | 기존 한 번의 큐 GET으로 mapping snapshot 콜백을 전달합니다. 결과 변경/검수 revision/재시도 시 초기화·AbortController로 오래된 응답을 무시합니다. 미검수 수량과 재생 제한을 표시합니다. |
| 공개 페이지·불변 추천 | `PublicPage.tsx::PublicPage` | liveYoutubeMappings를 본인 playlist_id·화면 mappingRevision에 맞을 때만 적용합니다. items·후보·점수·feedback·날씨·Gemini를 수정하지 않습니다. |
| 회귀·CI | `test_youtube_collected_links.py`, 기존 queue/registry 테스트, `youtubeLinks.test.ts`, `youtubeNativePlayback.test.ts`, `.github/workflows/application-tests.yml` | 실제 Django 공유 어댑터·원자 승인/감사 보존·차단·조회 범위·프런트 검증. PostgreSQL CI 대상에 신규 테스트를 추가합니다. |
| 문서 연결 | AGENTS·네 제품 기준 문서·`docs/music-playback-routing`·`config/routing-scopes.json` | 최신 사용자 결정·실제 변경·AST 시그니처를 연결합니다. 수령 원문은 수정하지 않습니다. |

## 응답·오류·인증 계약

기존 `GET /api/playlists/{playlist_id}/youtube-queue`에 추가합니다. 다른 사람 결과는 404, 미반영 제외는 409 EXCLUSIONS_NOT_APPLIED, 미설정 저장소는 503 POLICY_NOT_READY이며, 등록/검수용 ADMIN 권한은 변경하지 않습니다. 기존 response의 필드는 유지합니다.

```text
track_links: [{track_id, revision, candidates: [{video_id, native_verified}]}]  # 선곡표 전 곡 순서
tracks[].native_verified: bool
tracks[].source: 승인된 기존 native_source 또는 COLLECTED_UNREVIEWED
unreviewed_count: 큐에 실제 포함된 native_verified=false 곡 수
missing[].reason: MAPPING_REQUIRED 또는 DUPLICATE_VIDEO
```

track_links에는 운영자 note·reason·actor·감사 원문을 포함하지 않습니다. music RDB와 불변 Playlist snapshot·registry의 status/native_verified·revision/review_audit는 변경하지 않습니다. 스키마/마이그레이션·큐 작업·API 키·외부 검색 호출·미디어 저장을 추가하지 않습니다. LOCAL_DEMO는 복사한 로컬 registry, 운영은 기존 `YOUTUBE_REGISTRY_BACKEND=database` 어댑터를 사용합니다.

## 실제 검증과 한계

- 격리된 잠금 버전 Python 환경에서 `python -B -m backend.manage test backend.common backend.music backend.recommendation backend.weather tests --noinput --verbosity 1`: 318건 중 303 통과·15 skip. skip은 실행 환경에 따른 기존 조건부 검사이며 PostgreSQL 실연결 수용을 뜻하지 않습니다.
- 라우팅 AST 검사: 변경 Python 5개·심벌 61개·누락 0개, `scripts/check_routing.py` 전체 scope 통과. `makemigrations --check --dry-run` 변경 없음, `git diff --check` 통과.
- 프런트 `vitest run`: 12파일·71건 통과. `tsc -b`와 `vite build` 통과.
- 원본 자료 읽기 전용 전수 대조: GENERAL 86,485곡·CSV URL 보유 62,175곡 중 62,173곡/75,184개 곡-영상 조합을 공개 연결 대상으로 확인했습니다. 2곡/2개 연결은 명시 차단/철회 상태로 제외했습니다. 미검수 공개 조합은 75,031개입니다. 모든 곡에 URL이 수집됐다는 의미가 아닙니다. 원본 DB·registry 해시는 전후 동일합니다. 결과: Git 제외 `.local-preview-logs/url-connection-tests/all-collected-url-check.json`.
- 실제 자료 복사본·최신 로컬 코드의 브라우저 시험: 44곡 중 URL이 있는 미검수 30곡이 큐와 곡별 버튼 모두에 연결됐고, 나머지 14곡은 검색으로 표시됐습니다. 이 선곡표는 AWS 재현에서 생성한 선곡표와 별개입니다. 원본 DB/CSV·운영 DB·검수 승인은 변경하지 않았습니다.
- URL 표시·공식 큐 구성·검수 상태 보존을 확인한 것이며 모든 영상의 생존/한국 재생·전곡 일치·3시간 완청을 확인한 결과는 아닙니다.
- PostgreSQL 서버/Docker 데몬이 현재 PC에서 실행되지 않아 실제 PostgreSQL 검사는 미실행입니다. 기존 CI postgres-regressions에 동일 테스트를 추가했으며 GitHub에 올리기 전 CI 성공으로 보고하지 않습니다.

## AWS 적용 인계·복구

로컬 검증 완료 후 2026-10-19 사용자가 이 수정본의 커밋·푸시·PR 생성·CI 성공 후 develop 병합을 명시 승인했습니다. GitHub 반영 결과와 최종 커밋/CI는 해당 PR 기록으로 확인합니다. 운영 배포는 이번 승인 범위에 포함하지 않습니다. 현재 PC에는 AWS CLI와 배포 담당 Mac의 운영 private payload가 없어 이 작업에서 운영 배포를 대신 실행하지 않습니다.

1. 최신 develop에 이 변경을 검토·통합하고 common/frontend/postgres-regressions CI를 확인합니다. 실제 배포 담당은 기존 운영 브랜치의 다른 변경을 보존합니다.
2. 운영 `YOUTUBE_REGISTRY_BACKEND=database`와 기존 `youtube_mapping`·revision·audit 테이블을 유지합니다. 이번 코드 수정에 DB 초기화·마이그레이션 재생성·검수 자동 승인은 필요하지 않습니다.
3. 기존 배포 절차로 백엔드 API를 먼저 반영하고 모든 API 인스턴스를 같은 버전으로 맞춥니다. 새 API는 구 프런트와 호환됩니다. 본인 youtube-queue에 track_links·unreviewed_count가 나오는지 확인합니다.
4. 새 프런트 dist를 기존 웹 버킷에 반영하고 기존 운영 절차로 index.html 캐시를 갱신합니다. hash asset은 새 이름을 사용합니다. 배포가 끝나기 전에 AWS 수정 완료로 보고하지 않습니다.
5. 운영 관리 권한으로 CSV의 곡·영상 조합이 공유 registry에 적재돼 있는지 확인합니다. 62,175곡/75,186조합은 전달 CSV 기준이므로 운영 실제 행 수를 별도로 확인해야 합니다. 자료가 없으면 기존 `import_youtube_handoff`의 해시·dry-run·원자 적용/검수 보존 절차로 반영하고, 전체 미검수 자동 승인은 하지 않습니다. 이전 ZIP의 구버전 코드로 현행 운영 코드를 덮어쓰지 않습니다.
6. 새로고침 후 기존 결과에서도 현재 수집 URL이 직접 열리는지, 미검수 수량·누락·차단/철회·새 결과 전환·기존 피드백을 확인합니다. 이전 프런트 asset과 백엔드 release로 복구할 수 있으며 이번 변경 때문에 DB를 롤백하지 않습니다. 구버전 복구 시 승인 영상 전용 큐/검색 링크의 기존 제한으로 돌아갑니다.

공유 자료/DB·접근 코드·.env·전달 ZIP과 로컬 화면 DB는 GitHub 업로드 대상이 아닙니다. 배포 담당에게는 이 문서와 코드 변경, 기존 검증된 CSV 패키지를 연결합니다.
