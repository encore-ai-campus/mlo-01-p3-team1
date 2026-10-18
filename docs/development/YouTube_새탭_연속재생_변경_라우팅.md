# YouTube 새 탭 연속 재생 변경 라우팅

- 작성일: 2026-10-18
- 수정일: 2026-10-19
- 담당/범위: B 통합 조율, 사용자 요청에 따른 공개 재생 연결·첫 검수 묶음. 담당 재배치나 운영 배포를 의미하지 않습니다.
- 구현 시작 기준: `develop` / `757edbc`. 2026-10-19 사용자 게시 지시에 따라 `feature/ad-logic`에서 최신 `develop`의 `e8883da`를 포함해 커밋·푸시 대상으로 정리했습니다. 수집 원본과 수령 문서는 보존하며 게시 전 검증 범위는6절을 따릅니다.
- 최신 사용자 결정: 새 탭에서 YouTube 선곡표를 연속 재생하고, 가운데에는 앨범·곡 정보와 재생 버튼을 유지합니다. 수집 URL 중 검수 통과분부터 연결합니다.
- 추가 수집 반영 후 현재 로컬 상태: 매핑75,186개 / 매핑이 있는 곡62,175개 / 외부 검수 승인153곡. 수집 후보와 재생 승인을 구분하며 상세는5절을 따릅니다.

## 1. 기준과 실제 연결

[기능/흐름](../product/카페_음악_서비스_기능_및_사용자_흐름_정리.md), [구현 설계도](../product/카페_음악_서비스_구현_설계도.md), [후보 산출 가이드](../product/카페_음악_추천_서비스_3차_컬럼_기반_추천_로직_가이드.md), [태스크](../product/카페_음악_추천_서비스_3차_구현_태스크.md)의 음악18개·전체 GENERAL·불변 결과·ON/OFF 점수·176~184분을 보존합니다. 수령 [음악 테이블 원문](../handoff/music/테이블_구조_설계.md)은 수정하지 않습니다. 원문의 Spotify `play_url`은 직접 스트리밍 파일이 아니며, 로컬 YouTube 영상 레지스트리와 구분합니다.

기존에는 결과를 받은 뒤 가운데 카드가 외부 큐/보조 iframe 위주로 렌더링돼 앨범·첫 곡 정보가 빠졌습니다. 이번에는 결과 첫 곡의 커버·곡명·아티스트·앨범명을 복원하고 새 탭 재생 동작을 명시합니다. 커버는180px로 표시해 버튼과 정보를 밀어내지 않으며, URL이 없으면 기존 기본 이미지로 표시합니다. 첫 곡 표시는 외부 YouTube의 현재 재생곡 자동 추적이 아닙니다. 수령 음악 테이블 원문의 확인 커밋은 `2d5d924`입니다.

`PublicPage` → `YoutubeNativePlayback`의 큐 사전 조회 → `GET /api/playlists/{id}/youtube-queue` → 본인 소유·제외 반영 검사 → `native_queue` → 별도 레지스트리의 `native_verified` 영상 → 준비된 곡의 원래 순서로 `https://www.youtube.com/watch_videos?video_ids=...` 링크 → 사용자 클릭으로 새 탭을 엽니다. 이 경로는 계정에 저장하는 재생목록 생성 API가 아니며, YouTube의 광고/재생 가능 여부·버전 길이·자동 전환을 앱이 보장하지 않습니다.

## 2. 변경 파일과 동작

| 파일/함수 | 변경과 연결 영향 |
|---|---|
| `frontend/src/features/recommendation/PublicPage.tsx` / `PublicPage` | 결과 첫 곡의 앨범·곡 정보 복원. 새 탭에서 실제 재생됨을 안내. 기존 조건 변경·제외 미반영·안내/검수 중 재생 보류를 유지 |
| `frontend/src/features/recommendation/YoutubeNativePlayback.tsx` / `YoutubeNativeQueueView`, `YoutubeNativePlayback` | 전체 연결 버튼에 ‘선곡표 연속 재생’·접근성 이름에 ‘새 탭’을 명시. 부분 큐의 준비/전체 수·누락·재생시간 감소 안내, `_blank`·`noopener noreferrer`, 엄격한 URL/순서 검증 유지 |
| `frontend/src/features/recommendation/YoutubeNativePlayback.css` | 첫 곡의 긴 이름·아티스트·앨범명·설명 표시. 기존 카드/반응형 구조 사용 |
| `frontend/src/features/recommendation/youtubeNativePlayback.test.ts` | 새 버튼 이름/접근성 계약 확인. 기존 소유·순서·URL 위조·부분 큐·조건 보류 회귀 유지 |

Python 원본/API 경로·DB 스키마·공유 인증·큐 저장 방식·추천/평가/승인 동작은 이번에 변경하지 않습니다. 기존 보조 iframe은 사용자가 명시해서 펼치는 별도 경로로 유지하며 외부 승인만으로 iframe 검수를 승격하지 않습니다.

## 3. 초기 수집 URL 검수와 로컬 반영

수집 원본은 로컬 `analysis/youtube_urls_1000_20261018/youtube-additional-1000-urls.csv`의 첫 3곡과, 실제 생성한 47곡 선곡표에 포함된 추가 2곡입니다. 추가 곡의 수집 경로는 아래 검수 결과 JSON에 기록합니다. 전체 수집분을 검수 완료로 표시하지 않습니다. 기존 `spotify-preview-b202fa49909b-general-c2478b153aa8-yt-39c5056603a0`의 원곡 정보/길이와 앱 내 브라우저 직접 재생 관측을 대조했습니다. 원래 카탈로그와 수집 CSV는 덮어쓰지 않습니다.

| 곡 | 원본 / 실제 영상 초 | 판정 |
|---|---|---|
| Un Ratito | 176.936 / 177.061 | 제목·아티스트/버전 정보와 광고 이후 본영상 진행 확인, 외부 연결 승인 |
| No Surprises | 229.120 / 227.161 | 제목·아티스트/버전 정보와 본영상 진행 확인, 외부 연결 승인 |
| Bad Decisions (with BTS & Snoop Dogg) | 172.714 / 242.761 | 차이70.047초로 보류. 기본 허용차20.726초와 명시 차이 예외 최대60초를 넘으므로 승인하지 않음 |
| Vivir Asi | 294.400 / 294.501 | Maelo Ruiz/앨범 메타데이터와 본영상 진행 확인, 외부 연결 승인. iframe은 이번 묶음에서 검수하지 않음 |
| Olha o Que o Amor Me Faz - Ao Vivo | 197.549 / 197.561 | Vitinho/라이브 버전 메타데이터와 광고 이후 본영상 진행 확인, 외부 연결 승인. iframe은 이번 묶음에서 검수하지 않음 |

`register_mappings` → 실제 오류150을 관측한 경우에만 iframe `block_mapping` → 길이/원곡·외부 PLAYING 근거를 검사하는 `verify_native_mapping`을 기존 곡별 revision 규칙으로 실행했습니다. 처음 두 통과곡의 iframe은 BLOCKED이며, 추가 두 통과곡의 iframe은 CANDIDATE로 유지합니다. native 승인과 독립입니다. Bad Decisions는 후보/삽입 차단 이력만 보관하고 외부 큐에는 넣지 않습니다.

Git 제외 `.local-preview-logs/youtube-mappings.sqlite3`만 갱신했습니다. 두 차례 SQLite backup으로 이전 상태를 보존했고, 첫 적용 전149행과 추가 적용 전152행의 기존 필드가 모두 유지됨을 각각 대조했습니다. 이 첫 검수 묶음 반영 당시 전체 mapping은154행, native 승인은 기존147+이번4=151행이었습니다. 이전147곡의 근거는 그대로 유지하며 당시151곡을 전부 재생·청취했다는 뜻이 아닙니다. 이후 추가 수집 반영은5절에 분리합니다.

실제 근거는 [검수 결과](../acceptance/assets/youtube-native-review-20261018.json)와 로컬 `.local-preview-logs/native-rollout-20261018/`에 둡니다. 브라우저/메타데이터 검수이며 전곡 청취·물리 음향·사용자 Chrome/Premium 검증은 아닙니다. 실행코드/쿠키/키/계정 값은 문서에 기록하지 않습니다.

## 4. 검증과 실행/인계

- `python -m backend.manage test backend.recommendation.tests.test_youtube_queue_api backend.recommendation.tests.test_youtube_registry backend.recommendation.tests.test_youtube_review_api --noinput --verbosity 1`: 31개 통과. 시험 DB 격리.
- 프런트 Vitest: 52개 통과. TypeScript·Vite 빌드 통과. 설치된 도구를 직접 실행했으며 pnpm의 샌드박스 symlink 오류는 검사 실패와 구분합니다.
- Python 소스 변경은0개입니다. AST 전체 저장소를 음악 전용 색인에 비교하면 다른 도메인의 문서까지 누락으로 집계되므로 이 수를 이번 변경의 누락으로 해석하지 않습니다. 소유 범위별 라우팅 검사와 실제 변경 파일/함수 목록을 함께 확인합니다.
- 소유 범위 라우팅 검사 `python scripts/check_routing.py`: 광고87파일/908심볼, 통합17파일/133심볼, 문제0건. TypeScript 변경 4개와 본 라우팅의 파일/함수 목록을 별도로 대조했습니다.
- 변경한 기준/색인/라우팅 문서6개의 상대 파일 링크137개가 존재함을 확인했습니다. 기존 점수 수식의 대괄호 표현2개는 링크가 아닌 수식임을 원문에서 확인해 검사에서 구분했습니다. 검수 JSON 구문/5건 판정 수와 수집 원본3개 경로도 확인했습니다. `git diff --check` 통과.
- 별도 새 탭에서 실제 `PublicPage`의 기본 조건으로 추가 생성한 46곡은 연결된 곡이0개였습니다. 가운데 첫 곡·아티스트·앨범명과 미검수 안내가 표시되고, 승인 없는 재생 링크는 제공되지 않았으며 기본 iframe 개수는0개였습니다. 이 경우도 포함해 모든 새 선곡표의 외부 재생을 보장하지 않습니다.
- 실제 앱의 OFF 기본 조건에서 47곡 결과를 생성했습니다. 본인 쿠키로 `GET /api/playlists/{id}/youtube-queue?format=json`을 조회해 준비2/전체47/누락45, 부분 목록임을 확인했습니다. 후보 URL이 존재하는 것과 외부 재생 검수 승인은 구분하며, 미검수45곡을 임의 승인하거나 결과에서 삭제하지 않습니다.
- 기존 `YoutubeNativeQueueView`에 실제 API 응답을 연결한 별도 렌더링 시험에서 CTA 클릭으로 YouTube 새 탭과 2곡의 원래 순서를 확인했습니다. 첫 곡 `SwkqH_ar810` 본영상 진행(8.162/294.501초) 뒤 UI 탐색 슬라이더의 End로 끝부분을 탐색했고, 다음 버튼을 누르지 않고 `XthQbbcq0T8`·목록2/2로 자동 전환됐습니다. 다음 곡 광고에는 YouTube가 제공한 ‘건너뛰기’를 사용했으며, 광고가 아닌 본영상19.318/197.561초·재생 중·오류 없음까지 확인한 뒤 일시정지했습니다. 전곡 완주 시험은 아닙니다.

브라우저 근거는 로컬 `.local-preview-logs/native-rollout-20261018/native-transition.json`, `native-first-playing.png`, `native-second-playing.png`, `native-card-reviewed.png`에 보관합니다. 직접 주소창에서 API의 HTML 표현을 요청하면 기존 DRF 템플릿 설정 오류가 있으므로 JSON 표현으로 확인했습니다. 앱의 JSON 요청과 새 탭 외부 재생 흐름은 이 오류와 별개이며, 이번에는 API 렌더러 설정을 변경하지 않습니다.

이번 세션의 실제 공개 화면은 `http://127.0.0.1:5173/`, 검수된47곡 중2곡 연결 컴포넌트 시험 화면은 `http://127.0.0.1:5174/native-live.html`입니다. 후자는 실제 API 응답을 사용한 별도 검증 페이지이며 제품 화면이나 새 성공 추천 결과로 취급하지 않습니다. 해당 개발 서버가 실행 중일 때만 접근할 수 있습니다. 광고 서버는 이 음악 시험에 기동하지 않았으므로 광고 통합 완료 근거로 사용하지 않습니다.

로컬 화면 검증은 기존 `local-demo.sqlite3`의 복제본에 필요한 migration을 적용해 실행하며 원래 추천 DB·원래 불변 카탈로그는 수정하지 않습니다. 재생 영상 레지스트리는 위에서 명시한 원본 로컬 경로를 사용합니다. 공유 ADMIN·운영 레지스트리/다중 서버·AWS·전체 수집 URL 검수/원곡 대조·전곡 완주와 물리 음향 수용은 별도입니다. 공통 DB에 새 코드 적용 시 필요한 migration/카탈로그 순서는 [통합 정합성 라우팅](./통합_정합성_수정_변경_라우팅.md)을 따릅니다.

## 5. 다른 작업에서 수집한 추가 URL 반영 — 2026-10-18

사용자 추가 요청에 따라 `analysis/youtube_urls_*_20261018/`의 완료된 후보 CSV8개(1,000개·remaining·residual·tail·next·continue·followup 및 기존 영상 재사용 목록)를 연결했습니다. 수집 담당의 라우팅/CSV/README와 수령 원문을 수정하지 않았습니다. 각 경로·SHA256·행 집계는 [추가 반영 결과](../acceptance/assets/youtube-collected-import-20261018.json)에 기록합니다. source 원본과 라이선스/부분 checksum/표기·버전 검수 필요 플래그는 수집 기록을 그대로 따릅니다. 수집 완료를 원곡·재생 검수 완료로 승격하지 않습니다.

### 기준 → 등록 → 공개 연결

로컬 고정 GENERAL86,485곡 카탈로그 ID/목표 곡명·아티스트·제공된 앨범/길이 대조 → 기존 허용 목록 `normalize_video_url` → 중복/곡당10개 상한 검사 → `register_mappings`를500개 이하 배치로 호출 → 별도 SQLite의 CANDIDATE·native 미승인 상태와 revision/감사 기록 → 기존 `ReviewTracks`에서 검수 후보 조회 → 실제 외부 재생/원곡 확인에 통과한 곡만 `verify_native_mapping` → 기존 `native_queue`에서 원래 순서로 새 탭 링크를 구성합니다. API/인증/추천 점수/전체 후보 필터/원본 시간/불변 결과는 변경하지 않았습니다.

| 입력/처리 | 실제 결과 |
|---|---:|
| 후보 CSV 총 행 | 75,697 |
| 이미 등록된 곡·영상 조합, 내용 보존 후 건너뜀 | 5 |
| 신규 CANDIDATE 등록 | 75,032 |
| 기존 곡당10개 상한 초과, 원본과 별도 quarantine 기록에 보존 | 660 |
| 누적 매핑 / 매핑이 있는 곡 | 75,186 / 62,175 |
| 자동 재생 승인 | 0 |

### 직접 검수한 추가3곡

| 곡/영상 | 원본 / 관측 길이 초 | 결과 |
|---|---|---|
| Rhythm Of The Night / `eFs8FeXXW-k` | 229.106 / 229.121 | DeBarge·동명 앨범·UMG 제공 설명과 광고 이후 본영상46.616초 진행 확인, 외부 승인 |
| Happy Together / `OIyMGE8JpVo` | 152.659 / 152.681 | Mel Tormé·UMG 제공 설명과 본영상47.884초 진행 확인, 외부 승인. 원본은 편집 앨범 The Greatest Jazz Mix, 영상 설명은 A Time For Us(1969)이므로 앨범 차이를 메모에 명시. 파형/마스터 동일성 검증은 아님 |
| La Cumparsita / `aMV6B3YJ2lg` | 158.320 / 관측 불가 | Hugo Del Carril 영상 페이지에 ‘동영상을 재생할 수 없음 / 동영상을 볼 수 없습니다.’ 표시. `block_native_mapping`으로 외부 차단 사유만 기록. 제한의 정확한 원인은 미확정 |

iframe은3곡 모두 CANDIDATE로 유지하며 삽입 검수·승인/차단으로 바꾸지 않았습니다. 외부 승인 총수는151→153곡입니다. 추가3개 매핑만 수동 검수 상태가 바뀌었고, 이번 대량 반영 전154개 매핑의 모든 필드는 그대로 유지됐습니다. 기존46곡 스냅샷은 연결0→2/46(누락44), 앞선47곡 스냅샷은2/47(누락45)입니다. 결과 곡/순서/점수/길이를 바꾸거나 미검수 곡을 조용히 제거하지 않았습니다. 이 수는 저장된 스냅샷으로 큐 함수를 재조회한 결과이며, 새로운 모든 추천에 연결곡이 있다는 뜻이 아닙니다.

### 실제 검증과 운영 인계

- 별도 Git 제외 실행 도구: `.local-preview-logs/native-rollout-20261018/additional-import/import_collected.py`의 `digest`/`read_state`/`prepare`/`apply`가 원본 hash 고정·목표 대조·기존 매핑 제외·500개 배치 등록·백업/사후 비교를 처리합니다. `apply_reviews.py`의 `state`와 실행부는 저장한 브라우저 관측만 적용하고3개 상태 차이·기존154행 보존·큐/원본 hash를 검증합니다. 서비스 Python 소스 변경은0개입니다.
- 전체 복제 저장소 등록:151배치로75,032개 추가, 기존154행 필드 보존, 추가 행 전부 CANDIDATE/native 미승인, 감사75,032개, SQLite `integrity_check=ok`. 재실행 복제 시험은 추가0개·감사 추가0개·75,032개 건너뜀입니다.
- 실제 로컬 레지스트리에도 같은 계획을 적용했습니다. 적용 전 backup은 `.local-preview-logs/youtube-mappings-before-import.sqlite3`, 추가 수동 검수 전 backup은 위 추가 작업 폴더의 `registry-before-additional-reviews.sqlite3`입니다. 원본 CSV8개 SHA256의 보존을 재확인했습니다. 각 배치는 원자 저장되며 전체151배치를 하나의 트랜잭션으로 간주하지 않습니다.
- 기존 백엔드 큐/레지스트리/검수 API31개 시험을 다시 실행해 통과했습니다. 프런트 소스는 이 추가 반영에서 변경하지 않았으므로 앞 단계의52개/빌드 결과와 이번31개를 구분합니다.
- 실제 미들웨어·로컬 접근 코드 인증을 거치는 Django Client로 live 레지스트리의 관리 목록200/코드 누락403, 검수 승인 곡과 외부 차단 사유의 조회를 확인했습니다. 전체 요약은 미연결24,310·검수 대기62,021·승인153·차단1이며, full 목록 조회 한 번은2.142초였습니다. 검수 대기 곡 안의 개별 영상 차단과 곡 전체 차단 수는 구분합니다. 큐 함수의46/47곡 조회는 각각0.102/0.106초였습니다. 성능 보장 수치는 아닙니다.
- 라우팅 스킬의 기본 working-tree AST 검사는 기존 미커밋 자료인 `analysis/youtube_mapping_100_20261016/part1-build.py`의 짝 문서/색인 누락2건을 보고했습니다. 이 파일은 앞 단계 보존 hash와 동일하며 이번에 변경하지 않았고, 이번 서비스 Python 변경은0개입니다. 타 작업자의 수집 자료를 수정하거나 이번 데이터 반영의 새 누락으로 보고하지 않습니다. 검사 JSON은 추가 작업 폴더의 `routing-audit.json`에 보존하고 예외를 남깁니다. 본 라우팅의 상대 파일 링크와 추가 결과 JSON의 수/합계는 별도로 통과했습니다.
- 새 브라우저 문맥에서 과거46곡의 소유 API는404를 반환했습니다. 과거 쿠키를 복사하거나 소유 검사를 우회하지 않았으며, 이를 이번 사용자 문맥에서 과거 결과 API 재조회 성공으로 보고하지 않습니다. 위 Django Client 관리 API 검증·저장된 스냅샷 큐 검사와 구분합니다.
- 추가 승인2곡의 공개 `watch_videos` 링크를 앱 내 브라우저에서 별도로 열어 Happy Together → Rhythm Of The Night의2개 항목과 순서를 확인했습니다. YouTube의 정상 광고 건너뛰기 후 Happy Together 본영상54.837/152.681초·재생 중·광고 아님·오류 없음까지 관측하고 일시정지했습니다. 근거는 `additional-native-queue.json/png`입니다. 이 새2곡의 자연 완주/전환을 별도로 확인했다는 뜻은 아니며, 앞 단계의 끝부분 탐색 자동 전환 결과와 구분합니다.

상세 근거는 위 JSON과 로컬 추가 작업 폴더의 `prepared.json`, `plan.jsonl`, `quarantine.jsonl`, `stage-full-report.json`, `stage-idempotency-report.json`, `youtube-mappings-report.json`, `live-api-check.json`, 각 곡 관측 JSON/PNG에 있습니다. 남은 연결은 대부분의 후보에 대한 원곡/버전·실제 재생 검수, 상한 초과 후보의 수동 선택, 공유 ADMIN/운영 저장소입니다. 전체62,175곡 재생 검증·Chrome/물리 음향·전곡 완주·운영 배포는 이번 결과에 포함하지 않습니다. URL 반영 단계에서는 커밋·푸시하지 않았으며 후속 게시 범위는6절에 분리합니다.

## 6. 개발 진행 확인과 게시 전 검증 — 2026-10-19

사용자는 현재 개발분의 커밋·푸시와 `develop` 연결을 요청했고, 게시 브랜치를 기존 광고 담당의 `feature/ad-logic`으로 지정했습니다. 원격 최신 `develop`은 서비스명/헤더 브랜딩 `e8883da`로, 네 파일이 추가/변경돼 있었습니다. 이번12개 파일과 겹치지 않음을 확인한 뒤 광고 브랜치를 fast-forward로 맞췄습니다. 실제 게시 커밋/PR/CI 결과는 GitHub 기록으로 확인하며 문서만으로 병합·운영 배포 완료를 확정하지 않습니다.

| 분야 | 현재 확인한 개발 상태와 남은 연결 |
|---|---|
| 독립 광고 서버 `ad-server/backend/` | 기존 관리·공개 API/MongoDB 원자 저장·5분 예산/통계 규칙 유지. 이번 작업의 광고 소스 추가 diff는0개. 공유 ADMIN/guest와 운영 환경 연결은 광고 서버 README의 인계 범위를 따름 |
| 공개 음악 화면 | 가운데 첫 곡의 커버·곡/아티스트/앨범 정보, 명시적인 새 탭 재생 버튼과 접근성 이름. 미연결·부분 연결·조건 변경 보류와 보조 iframe 분리 유지 |
| 추가 URL | 로컬 누적75,186매핑/62,175곡·외부 승인153곡. 미검수 후보 대량 등록과 실제 재생 검수 승인을 구분. 후보/승인 레지스트리와 수집 원본은 이 PC의 로컬 자료 |
| 통합·검증 | 최신 서비스명/헤더 포함. 실제 운영 인증·AWS·전체 음악 재생 완주와 배포는 이번 커밋의 완료 항목이 아님 |

게시 대상은 프런트4개 파일, 제품 기준 문서4개, 개발 색인/본 라우팅2개, 소량의 검수/집계 근거 JSON2개로 총12개입니다. 별도로 존재하던 수집 담당 라우팅과 `docs/handoff/music/README.md` 수정, 분석/수집 자료는 이 커밋에 섞지 않고 보존합니다. 게시 전333개 다른 변경 파일의 SHA256·크기를 별도 Git 제외 보존 목록에 기록했습니다. 대량 원본 CSV·DB/접근 코드·쿠키·실행 로그·임시 수집 도구를 GitHub에 업로드하지 않습니다. 따라서 코드/문서 푸시가 다른 PC의 로컬 카탈로그·75,032개 후보/검수 DB 복제를 뜻하지 않습니다. 데이터 인계 시5절의 원본·SHA256·등록 계획과 별도 안전한 자료 전달/저장 경로가 필요합니다.

게시 전 실제 재검증 결과:

- 공통/음악/추천/날씨/저장소 테스트: `python -m backend.manage test backend.common backend.music backend.recommendation backend.weather tests --noinput --verbosity 1` — **233개 통과**. 최초 Windows sandbox 임시 폴더 접근 오류22건은 작업 공간 내부의 확인된 TEMP/TMP와 정상 실행 권한으로 같은 검사를 재실행해 해소했습니다. 코드 변경으로 시험을 완화하지 않았습니다.
- 광고 서버 `python manage.py test tests --noinput --verbosity 1` — **372개 실행, 실패0, MongoDB 연결 시험4개 skip**. 로컬 검사는 `ADS_RUN_MONGO_TESTS=0`이며 실제 replica-set 연결의 근거가 아닙니다. 원격 CI의 분리 MongoDB 시험과 구분합니다.
- 프런트 Vitest **52개 통과**, TypeScript `tsc -b`·Vite build 통과. 설치된 잠금 도구를 직접 실행했습니다.
- `makemigrations --check --dry-run`: No changes detected. `scripts/check_routing.py`: 광고87파일/908심볼·통합17파일/133심볼 문제0건. 원본 분석 스크립트의 기존 라우팅 누락 예외는5절 그대로이며 수정하지 않았습니다.

자료/기록 보존 확인은 로컬 `.local-preview-logs/publish-playback-20261018/`의 선택 파일 목록·보존 hash·검증 로그를 사용합니다. 커밋/푸시·PR 생성과 `develop` 병합 여부는 실제 Git/GitHub 결과를 기준으로 별도 보고합니다.
