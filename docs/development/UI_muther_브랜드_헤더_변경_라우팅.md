# muther 서비스명과 공통 헤더 변경

- 작성일: 2026-10-18
- 수정일: 2026-10-18
- 작성자: Codex, 서비스명과 공통 헤더 UI
- 작업 범위: U-01 관련 공개 화면과 공통 로그인 헤더의 브랜드 표시
- 기준: `origin/develop`의 `757edbcc6c969a7d90ed4170878a2075e51102df` (`fix(integration): [D-02] 광고 배달과 추천·이력 정합성 및 CI 보완`). 기존 브랜드 미리보기 기준은 `e2b7d62a2161856714b14de8f56ca32611886969`였습니다.
- 작업 브랜치: `codex/muther-branding`, Codex 관리 작업 트리 `muther-youtube-review`. 공유 `develop` 작업 폴더의 미커밋 변경을 보호하기 위해 최신 원격 커밋에서 분리하고 브랜드 네 파일만 재적용했습니다.
- 상태: 최신 develop에 브랜드 변경 통합, 로컬 빌드·YouTube 경로 검증 완료. 모든 변경은 미커밋이며 커밋·푸시·AWS 배포는 수행하지 않았습니다.

사용자는 2026-10-18 서비스명을 `muther`로 확정하고, 기존 상단의 “날씨 기반 음악 선곡”을 서비스명과 짧은 설명으로 바꾼 로컬 미리보기를 요청했습니다. 첨부한 `image.webp`의 파란색·짙은색·주황색 워드마크를 참고했습니다. 설명 문구 “날씨와 취향을 담은 3시간 선곡표”는 이번 미리보기 제안입니다. 같은 날 추가 요청에 따라 화면 오른쪽 아래에 날씨 아이콘과 `MUSIC × WEATHER`를 고정 표시했습니다.

## 기준과 구현 연결

다음 수령 문서는 기준 커밋의 원문을 보존했습니다.

| 기준 문서 | 적용 내용 |
| --- | --- |
| [서비스 기능 및 사용자 흐름](../product/카페_음악_서비스_기능_및_사용자_흐름_정리.md) | 공개 메인·로그인·헤더 사용 안내와 기존 화면 흐름 유지 |
| [구현 설계도](../product/카페_음악_서비스_구현_설계도.md) | 공통 헤더와 모바일 줄바꿈·조작 영역 유지 |
| [컬럼 기반 추천 로직 가이드](../product/카페_음악_추천_서비스_3차_컬럼_기반_추천_로직_가이드.md) | 추천 ON/OFF·후보·점수·시간 계약에 변경 없음 |
| [3차 구현 태스크](../product/카페_음악_추천_서비스_3차_구현_태스크.md) | U-01의 헤더 표시 범위만 조정하며 광고·추천 기능 범위 유지 |

과거 실행 인계의 임의 서비스명 제거 기록에 대해서는 이번 사용자 확정 이름을 우선합니다. 기존 수령 문서와 다른 작업자의 변경 라우팅 문서는 수정하지 않았습니다.

## 변경 파일과 동작

| 파일 | 변경 내용 |
| --- | --- |
| [Header.tsx](../../frontend/src/components/Header.tsx) `Header` | 기존 브랜드 링크를 `muther.` 워드마크와 설명으로 변경. 접근성 이름은 `muther · 날씨와 취향을 담은 3시간 선곡표`이며 홈 링크·사용 안내·로그인·로그인 화면의 홈 이동을 유지. 날씨 아이콘과 `MUSIC × WEATHER` 표시를 함께 렌더링 |
| [header-brand.css](../../frontend/src/components/header-brand.css) | 공통 헤더 안의 브랜드에만 적용하는 전용 스타일. `mu`는 `#287df2`, `ther`는 `#122146`, 점은 `#ff6b22`. 700px·380px 이하 글자 크기 조정. 우측 하단 문구는 작은 고정 배지로 표시하고 `pointer-events: none`으로 클릭·터치 통과 |
| [index.html](../../frontend/index.html) | 브라우저 제목과 서비스 설명 메타데이터에 `muther` 반영 |

기존 `PublicPage.tsx`, `style.css` 등 작업 시작 당시 다른 변경이 있던 파일은 이번 수정에 포함하지 않았습니다. 공통 `Header`를 사용하는 공개 메인과 로그인 화면에 반영되며, 별도 구현된 관리자 전용 헤더는 기존 표시를 유지합니다.

API 경로·입력/응답·인증/소유·DB·큐·추천 정책·환경변수 규격은 동일합니다. DNS·인증서·AWS 라우팅 변경은 포함하지 않습니다.

## 최신 develop 통합과 로컬 검증 — 2026-10-18

아래 수령 코드와 문서는 기준 커밋의 구현 상태를 확인하는 데 사용했으며 수정하지 않았습니다.

| 기준 → 코드·저장 흐름 | 확인 내용 |
| --- | --- |
| [키 없는 등록·검수 라우팅](./YouTube_키없는_등록과_검수_변경_라우팅.md) → `YoutubeNativePlayback.tsx`, `youtube_queue_api.py` | 외부 임시 대기열이 기본이며 연결 승인된 곡만 원래 순서로 포함. 준비된 곡 수와 누락 수를 표시 |
| [기존 실제 검증](../acceptance/YouTube_키없는_등록과_검수_검증_20261016.md) → `YoutubePlayer.tsx`, `YoutubeReviewPanel.tsx`, `youtube_registry.py` | 공식 iframe 보조 경로와 외부/삽입 독립 승인. 별도 로컬 SQLite 레지스트리·운영자 코드 사용 |
| `seed_csv_preview.py` → `occasion.py` → 로컬 `Catalog` → 추천 작업자 → 불변 결과 → 재생 연결 조회 | CSV와 분류표 manifest를 검증한 뒤 전체 GENERAL 후보를 발행. 재생 가능 여부로 추천 후보·점수·원래 선곡표를 줄이지 않음 |

이번 소스 수정은 브랜드 세 파일과 이 문서뿐입니다. YouTube·추천·DB 코드 수정, 기존 미커밋 취소/UI/인프라 코드의 이관은 하지 않았습니다.

| 검증 | 실제 결과 |
| --- | --- |
| `cd frontend && pnpm install --frozen-lockfile` | 성공, 잠금 파일 변경 없음 |
| `cd frontend && pnpm test` | 9개 파일·52개 테스트 통과. 외부 링크·iframe API·재생 제어·등록/검수 포함 |
| `cd frontend && pnpm build` | TypeScript 검사와 Vite 배포 빌드 성공 |
| `C_LOCAL_DEMO=1 INTEGRATION_ENABLED=0 GEMINI_ENABLED=0 YOUTUBE_PLAYBACK_MODE=KEYLESS .venv/bin/python -m backend.manage test backend.recommendation.tests.test_youtube_playback backend.recommendation.tests.test_youtube_playback_api backend.recommendation.tests.test_youtube_queue_api backend.recommendation.tests.test_youtube_registry backend.recommendation.tests.test_youtube_review_api backend.recommendation.tests.test_keyless_playback --verbosity 1` | 59개 테스트 통과. 소유/CSRF·순서·독립 승인·revision·운영 차단 포함 |
| 로컬 전체 CSV 카탈로그 | 원본 114,000행·분류표 89,741곡, GENERAL 후보 86,485곡. 47곡 한정 후보 옵션은 사용하지 않음 |
| 날씨 OFF 실제 생성 | 47곡 생성 성공. 기존 영상 매핑과 일치하는 곡이 없어 최초 0/47 연결 준비를 표시. 검색·후보 등록만으로 승인하지 않음 |
| 외부 링크 실제 재생 | OFF 결과의 `I Like That / Bazzi`에 공식 Audio `jAkP5qh9plo`를 로컬 등록하고 외부 승인. 서비스가 생성한 `watch_videos` 링크에서 실제 재생 30.70초·길이 158.321초 관측. 음소거 상태이며 물리 음향·전곡 완주는 확인하지 않음 |
| 외부/삽입 분리 | 같은 Bazzi 영상의 iframe은 실제 오류 150. 로컬에서 삽입 차단 사유를 기록한 뒤에도 외부 승인과 1/47 외부 링크 유지. YouTube 제한을 우회하지 않음 |
| 날씨 ON 실제 생성 | 성수1가제2동·로컬 맑음 샘플로 47곡 생성 성공. 외부 매핑 45/47 연결 준비. 이 비율은 이 결과에 한하며 전체 카탈로그 보장 수치가 아님 |
| 공개 보조 iframe 실제 재생 | `Somos Instantes / Gabriel Elias;Vitor Kley`, 영상 `fmQviVOk7s4`의 재생 시작과 225.901초 길이를 관측한 뒤 로컬 삽입 승인. 공개 플레이어에서 앞의 미검수 4곡을 건너뛰고 5/47 위치로 이동, 8.88→23.87초 재생 진행 확인. 원래 47곡 결과 유지·단축 안내 표시. 마지막에 일시 정지·관리 잠금 |
| 최신 화면 | 제목·헤더 `muther`, 우측 하단 `MUSIC × WEATHER` 확인. 기본 IAB 화면 너비 610px에서 가로 넘침 없음, 배지 높이 29px·화면 내 위치 확인 |
| 기존 브랜드 미리보기 회귀 근거 | 동일 브랜드 코드의 1440px·390px 메인/로그인에서 겹침·가로 넘침 없음, 배지 `pointer-events: none` 클릭 통과. 최신 코드에서는 위 기본 화면으로 추가 확인 |

새 미리보기는 `http://127.0.0.1:5188/`이며 API는 `127.0.0.1:8018`의 별도 SQLite DB와 로컬 작업자에 연결합니다. 날씨는 샘플, 광고는 기존 별도 샘플 API를 사용했습니다. AWS·운영 PostgreSQL·기상청·Gemini·YouTube Data API 키는 사용하지 않았습니다. 기존 `5187` 브랜드 샘플과 공유 작업 폴더는 유지했습니다.

실제 영상 재생 시작과 시간 진행을 확인했으며 전체 선곡표 연속 완주, 실제 음향 출력, Chrome/Premium별 동작, 실제 예보·광고·AWS 통합을 확인한 것은 아닙니다. 자동 다음 곡·오류 처리의 테스트 통과와 실제 전곡 완주를 구분합니다.

## CSV 보관과 배포 연결 대기

최신 develop clone에는 Git 제외 파일인 `analysis/weather_music_20261016/general/occasion_decisions.csv`가 없어 최초 `seed_csv_preview`가 안전하게 실패했습니다. 기존 `music_playback.candidates.screen_source`와 `write_csv`로 원본 CSV를 다시 분류하고, 기존 manifest의 분류표 SHA-256과 정확히 일치하는지 확인했습니다. manifest·분류 규칙·필수 필터는 바꾸지 않았습니다. 기존 자동 분류 산출물의 재현이며 전곡 수동 검수 완료를 새로 선언하지 않습니다.

- 원본 CSV LF 정규화 SHA-256: `b202fa49909b2d5cef71a04b1d21243cfeb36414535f2ca9272aa646721177bd`
- 분류표 SHA-256: `c2478b153aa8bee652fb9d7505dfa78621be37a9bd660094f01384f544788760`
- 원본 CSV·분류표 CSV·manifest·분류 정책·체크섬은 사용자 로컬 프로젝트의 Git 제외 `.private/deployment-inputs/music-catalog-757edbc-20261018/`에 별도 보관했습니다. 비밀값·DB·운영자 코드와 묶지 않았습니다.
- 초기 적재·재발행·복구에는 해당 버전의 입력 자료를 보관해야 합니다. 발행된 카탈로그 조회는 DB를 사용하므로 웹 요청마다 CSV를 읽지 않습니다. 이 로컬 사본 외에 배포용 버전 보관소에도 백업해야 합니다.

**운영 연결 미완료:** `seed_csv_preview`는 `C_LOCAL_DEMO=1` 전용이며 테스트 카탈로그를 발행합니다. `youtube_queue_api.py`도 운영 모드에서 `POLICY_NOT_READY`/503으로 차단하고, KEYLESS 운영 레지스트리 어댑터는 미연결입니다. 브랜드만 배포하는 것과 최신 develop의 음악 발행·YouTube를 운영에 연결하는 것은 별개입니다. 운영 카탈로그 발행 경로·공유 영상 저장소·ADMIN 권한·검수 데이터 이관을 연결하고 운영 모드로 검증해야 합니다. AWS에서 데모 모드를 켜는 것으로 대신하지 않습니다.

## 사용자가 직접 커밋할 범위

위 세 프론트엔드 파일과 이 문서만 추가합니다. 권장 메시지는 `feat(ui): muther 서비스명과 헤더 브랜딩 적용`입니다. 기존 공유 `develop` 폴더에는 타 작업자의 변경이 있으므로 이번에 준비한 `codex/muther-branding` 작업 트리에서 커밋합니다. 비밀값·생성 CSV·SQLite DB·검수 접근 코드는 `.gitignore` 대상이며 커밋에 포함하지 않습니다.

커밋 후 `git fetch origin develop`과 `git rebase origin/develop`으로 원격 변경을 반영한 다음, 팀의 develop 권한/보호 규칙에 따라 `git push origin HEAD:develop` 또는 PR 경로를 사용합니다. 강제 푸시는 사용하지 않습니다. 이번 작업에서는 커밋·푸시를 실행하지 않았습니다.

운영 반영 시 메인·로그인·브라우저 제목과 CDN 갱신을 확인합니다. 되돌릴 때도 브랜드 세 파일의 변경만 되돌려 병행 작업을 보존합니다.
