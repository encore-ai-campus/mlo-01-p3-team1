# 기존 사용자 대시보드 YouTube 연결 라우팅

- 작성일: 2026-10-16
- 수정일: 2026-10-16
- 기준: `feature/ad-logic` / `f22f974`
- 요청: 기존 사용자 대시보드의 중앙 앨범 영역에 YouTube iframe을 연결하고 자동재생을 시도하며, 곡 종료 뒤 다음 곡으로 진행합니다.
- 상태: 키/LLM 없이 저장 매핑을 사용하는 중앙 플레이어/후보 API·자동검증과 일부 실제 재생/자동 진행을 확인했습니다. 공식 Data API 자동 검색은 선택 기능이며 키 미등록으로 실호출은 미실행입니다. 아래 과거 이력과 새 중앙 관측을 구분하며 전곡 완주·물리 소리/Premium은 미검증입니다.

## 최신 사용자 정정 — 중앙 iframe이 주 재생 경로

이번 결정은 이전의 ‘네이티브 YouTube 이동을 주진입으로 사용’하는 결정을 대체합니다. 주진입은 계속 기존 `PublicPage`이며 **중앙 앨범 영역에 보이는 공식 iframe 플레이어**를 넣습니다. 추천 성공 뒤 현재 결과의 순서로 자동재생을 시도하고, 브라우저가 차단하면 같은 곡에서 [재생]을 기다립니다. 새 별도 페이지나 LLM을 선행 조건으로 추가하지 않습니다. 곡별 외부 검색/직접 열기는 보조로 유지하고 전체 네이티브 임시 목록 유틸/증거는 보존하되 현재 전체 연결 영역은 표시하지 않습니다.

추천 입력은 전체GENERAL86,485곡이며 고정47곡 시험 카탈로그를 신규 일반 요청에서 제외하는 아래 계약을 유지합니다. 추천 결과·곡 순서·원본 `duration_ms`·176~184분 검증은 불변입니다. 영상 검색 실패 때문에 추천 후보를47개로 제한하거나 기존 결과의 곡을 다른 곡으로 바꾸지 않습니다. iframe의 대안은 **같은 원곡/버전의 다른 영상 후보**이며, 실패 곡을 건너뛰더라도 원래 선곡표에서 삭제하지 않고 별도 실패 목록과 실제 재생 범위에 남깁니다.

검색은 기존 확정 매핑을 먼저 확인하고, 부족한 곡은 서버에서 공식 YouTube Data API로 찾습니다. 원문 곡명·아티스트·버전·길이와 영상 메타데이터를 규칙으로 대조하며 LLM 호출은 없습니다. 검색 결과와 실패/재시도 캐시는 카탈로그·추천 결과·기존 `YOUTUBE_MAPPING_V1` 파일과 분리합니다. API 키 확인/공급과 실제 요청 경로는 구현 담당이 검증하며 키가 없거나 할당량/접속 오류이면 명시적으로 검색 불가를 안내합니다. 검색 결과가 없다고 꾸미거나 모든 곡을 순차 생략하지 않습니다.

자동 후보의 재생 시험은 원곡 일치를 수동 확정한 VERIFIED나 청취/Gold 검수와 다릅니다. 기존47곡 VERIFIED도 국내 네이티브 목록 대조 범위이며 iframe 허용을 보증하지 않습니다. 검색 출처·후보 상태·영상ID·메타데이터 확인 시각과 이번 플레이어의 실제 오류/상태를 분리해 표시합니다. 기존18개 `play_url`과 일반 적격/점수를 덮어쓰지 않습니다.

| 플레이어 상태/사건 | 진행 계약 |
|---|---|
| 준비/자동재생 시도 | 현재 결과의 곡 하나를 로드하고 재생을 시도. PLAYING 이전 상태를 재생 성공으로 기록하지 않음 |
| `onAutoplayBlocked` | 현재 곡을 유지하고 브라우저 재생 차단/[재생] 안내. 곡 실패나 후보 부족으로 바꾸지 않음 |
|15초 로딩·재생시간0초 / iframe 준비20초 초과|앞의 경우 일반 준비 지연 안내로만 처리하고 광고/버퍼링을 차단으로 단정하지 않음. 실제 iframe 준비 시간 초과는 별도 준비 오류/재확인|
| 실제 PLAYING 뒤 `ENDED` | 현재 영상/큐 버전을 확인해 다음 곡으로 한 번만 진행. 늦은 콜백·중복 종료로 두 곡을 넘기지 않음 |
| `2/100/101/150` | 같은 곡의 제한된 대안 후보를 시도하고 실패ID를 재사용하지 않음. 대안 소진 시 빠진 곡/사유를 남긴 뒤 다음 곡으로 진행 |
| `153`·플레이어 환경 오류 | Referer/API client 식별 등 실행 환경을 안내하고 현곡 보류. 지역/삽입 제한 우회·브라우저 식별 위조 없음 |
| 검색 키/할당량/접속 불가 | 첫 조회는 현곡 보류. 실제100/101/150 뒤 대안 조회도 불가이면 그 곡만 실패로 기록한 뒤 다음 곡을 시도하며, 다음 미매핑의 검색도 불가이면 다시 보류. 전곡 일괄 실패 없음 |
| 설정 편집·제외 미반영·생성/저장 중·사용 안내 | 현재 재생 정지와 진행 중 요청 취소. 해제 후 자동으로 재개하지 않고 명시 [재생]을 기다림 |

API는 [공식 검색 규격](https://developers.google.com/youtube/data/reference/rest/v3/search/list)의 삽입/외부 재생·한국 제공 필터와 [영상 메타데이터](https://developers.google.com/youtube/data/reference/rest/v3/videos)의 길이/상태를 대조합니다. 실제 삽입 오류와 자동재생 차단은 [IFrame API](https://developers.google.com/youtube/iframe_api_reference)의 사건으로 별도 확인합니다. HTTP 응답·검색 후보·iframe 준비·PLAYING·자연 종료 전환·전곡 경과 재생을 서로 다른 증거로 남깁니다.

현재 실제 Data API 키가 없어 새 자동 검색은 미실행입니다. 키 없이도 기존 매핑을 반환할 수 있으며 미매핑에는 `SEARCH_UNAVAILABLE/API_KEY_MISSING`을 안내합니다. [키 발급과 서버 설정](./music/YouTube_API_키_발급과_서버_설정.md)은 숨김 입력·API 프로세스 재시작을 안내하며 실제 키 등록 완료는 아닙니다. 후보 조회는 `POST /api/playlists/{pk}/youtube-playback`에서 기존 소유/CSRF 경계를 적용하고 해당 결과 스냅샷의 원곡만 사용합니다. resolver 상세는 [자동 검색 라우팅](./YouTube_자동검색_변경_라우팅.md), 중앙 수명주기/큐는 [iframe 플레이어 라우팅](./음악_iframe_플레이어_변경_라우팅.md)을 따릅니다. `playedTrackIds`는 재생 시작을 관측한 곡 목록이며 완주 수가 아닙니다.

### 이번 실제 중앙 재생 관측과 남은 범위

통합 백엔드101건·프런트32건과 최신 빌드는 PASS입니다. root의 실제 IAB는 기존 PublicPage 중앙에서420×262 iframe·현재 origin·`strict-origin-when-cross-origin`·autoplay 허용 속성을 확인했습니다. [당시 결과](../acceptance/assets/central-iframe-result-20261016.json)는 전체GENERAL86,485곡에서 기본 `ON/any/auto`·테마/장르 미선택으로 생성한47곡/10,652,228ms이며 카탈로그 메타데이터 매핑46개를 포함합니다. 사용자 승인 교체곡을 넣은 과거 고정47곡과 다른 결과이고 `preview_only=true`·`validation_passed=false`를 유지합니다.

앞4곡은 실제 삽입 제한과 대안 검색 키 없음으로 실패 목록에 남았고5번 Somos Instantes의 PLAYING 및 iframe0:41/3:45 시간 진행을 관측했습니다. [재생 관측](../acceptance/assets/central-iframe-playing-20261016.json)·[화면](../acceptance/assets/central-iframe-playing-20261016.jpg)에 연결합니다. Next를 누르지 않은 상태에서6번 Keep On Running/7번 Cứ Chill Thôi의 삽입 실패 기록 뒤8번 Night on the River의 PLAYING·누락6곡을 [후속 관측](../acceptance/assets/central-iframe-natural-transition-20261016.json)으로 확인했습니다. 실패한 곡을 포함한 원본47곡은 그대로 남습니다.

이는 기존 매핑을 이용한 일부 실제 중앙 재생/자동 진행이며47곡 전체 완주·약177분 실제 경과·물리 음향·Chrome 계정/Premium 검증이 아닙니다. 실제 Data API 검색/자동 매칭도 키가 없어 미실행입니다. 이 시험 도중 사용자가 별도로 요청한57곡 연주곡 결과의 Between Mind & Heart는 미매핑/`API_KEY_MISSING`으로 보류됐으며 위47곡 관측에 합치지 않습니다. 상세는 [이번 중앙 iframe 수용 기록](../acceptance/대시보드_중앙_YouTube_iframe_검증_20261016.md)을 따릅니다. 그 기록의 키 없는 등록/검수 시 영상 매핑 제안은 후속 설계이며 신규 입력/일괄 가져오기 화면이 구현된 것은 아닙니다.

## 일반 추천 전체 후보 풀 복원 후속 — 2026-10-16

사용자는47곡 재생 시험용 목록이 일반 추천의 기본 입력이 되어 다른 장르 조건에서 후보 부족이 발생하는 문제를 수정하도록 승인했습니다. [추천 가이드5절](../product/카페_음악_추천_서비스_3차_컬럼_기반_추천_로직_가이드.md)의 전체 적격 C_ON/C_OFF와200→전체 후보 확장, [공통 계약3.2/3.5절](../product/3차_공통_개발_계약과_검증_기준.md)의 부족 증명/SEARCH_INCOMPLETE를 적용합니다. 이 수정은 추천 수식·176~184분·필수 장르·시즌 필터를 완화하는 변경이 아닙니다.

`backend/recommendation/service.py`의 `current_catalog()`는 로컬 모드에서 READY/test 조건을 만족하는 카탈로그 중 `source_ref`가 `local-preview:youtube-playback-selection:`으로 시작하는 고정 재생 목록을 제외하고 최신 일반 카탈로그를 선택합니다. 신규 기본 요청의 `catalog()`와 `worker.py`의 `warm_current_catalog()`가 같은 선택 함수를 사용합니다. 고정 재생 목록만 존재하면 `POLICY_NOT_READY`/503과 일반 음악 카탈로그 준비 안내를 반환하며47곡으로 자동 대체하지 않습니다. 운영 모드의 기존 선택은 유지합니다.

이미 접수한 작업은 고정 `job.catalog`, 기존 결과 조회는 저장 스냅샷, 같은 계열 재설정은 `parent.job.catalog`를 계속 사용합니다. 새 카탈로그로 이전47곡 결과·평가·제외·승인·부모를 소급 변경하지 않습니다. 독립 새 추천과 작업자 사전 로딩의 현재 카탈로그만 일반 풀로 분리합니다.

일반 적재는 `seed_csv_preview --general-dir … --youtube-mappings …`이고 **`--playback-selection`을 사용하지 않습니다.** 확인된 새 일반 시험 카탈로그는 `spotify-preview-b202fa49909b-general-c2478b153aa8-yt-39c5056603a0`이며 GENERAL86,485곡·맑음 적격34,883곡·카탈로그 안의 기존 검증 매핑47개를 포함합니다. 매핑47개만으로 후보를 제한하지 않으며 이 카탈로그는 고정 선택 목록이 아닙니다. 당시47곡 한정 카탈로그·원본·실행 증거는 보존합니다.

일반 결과는 요청 조건으로 새로 계산하므로 곡 수·총시간·검증 영상 수가 과거47곡과 같다고 가정하지 않습니다. 미매핑 곡도 추천 적격이면 남기고 곡별 검색을 제공합니다. 전곡 VERIFIED가 아닌 결과의 전체 네이티브 링크는 기존 gate에서 보류하며 매핑된 일부만 모아 전체 목록처럼 열지 않습니다.

실제 사용자 요청은 `ON`·보컬 `any`·빠르기 `auto`, 테마 `BRIGHT/DREAMY/EMOTIONAL/PEACEFUL`, 장르 `CLASSICAL/J-POP/K-POP/NEWAGE/OPERA`입니다. [분리 감사](../acceptance/assets/catalog-isolation-repair-audit-20261016.json)에서 실패 요청과 새 성공 요청의 옵션이 정확히 같음을 확인했습니다. 과거47곡 카탈로그에서 공통 적격3곡·757,825ms만 남던 요청이 전체 카탈로그에서는 공통 적격6,818곡→날씨 탈락3,562곡→최종3,256곡(807,879,234ms)을 사용했습니다.

[새 실제 결과](../acceptance/assets/general-pool-repair-result-20261016.json)는 `SUCCEEDED`·45곡·10,560,186ms(176분00.186초), 탐색 창400·`FEASIBLE_GREEDY_PREVIEW`입니다. 장르 포함 수는 CLASSICAL1/J-POP32/K-POP10/NEWAGE2/OPERA1이며 복수 장르곡이 있으므로 합계를 고유곡 수로 더하지 않습니다. UI에서 영상 확인3/45·미확정42곡·전체 임시 목록 보류를 확인했습니다. 이 결과의 `preview_only=true`·`validation_passed=false`를 유지하고 운영 최적 시간/청취 검수 완료로 표시하지 않습니다.

카탈로그는 총3개(이전 전체86,485곡·고정47곡·새 전체86,485곡+매핑47개)를 보존했습니다. 이전47곡 결과 내보내기의13개 필드/전47행·순서·총ms가 동일하다는 읽기 전용 대조를 감사 파일에 남겼습니다. 과거47곡 결과를 이번45곡으로 덮어쓰거나 이전 평가/제외 조건을 새 계열에 복사하지 않았습니다.

증명 가능한 후보 부족은 실제 고정 카탈로그·요청 조건·전체 적격 수/총ms·장르별 후보와 대표 배정·탐색 범위로 설명합니다. `solver.py`의 `choose_preview()`가 아래 진단을 만들고 기존 작업/오류 응답 경로로 전달합니다. ON 부분 장르는 각각 서로 다른 대표곡이 필요하고 테마는 불일치 시 취향 가점0이며 필수 일치 필터가 아닙니다. 준비 현황 총시간이나 장르별 수만으로 조합 성공을 단정하지 않습니다.

|오류 코드|`details.reason`·확인 범위|
|---|---|
|`CANDIDATE_SHORTAGE`|`TOTAL_DURATION_BELOW_MINIMUM`, `SELECTED_GENRE_MISSING`, `DISTINCT_GENRE_REPRESENTATIVES_UNAVAILABLE`, `SELECTED_GENRE_DURATION_BELOW_REQUIRED_SHARE`, `FULL_ELIGIBLE_POOL_PROVEN_INFEASIBLE` 중 실제로 입증된 사유|
|`NO_MEANINGFUL_CHANGE`|`AVAILABLE_NEW_TRACKS_BELOW_REQUIREMENT`: 부모 대비 필요한 신규곡 수보다 전체 신규 후보가 부족함|
|`SEARCH_INCOMPLETE`|`SOLVER_OR_FULL_POOL_SEARCH_INCOMPLETE`: 제한 창·UNKNOWN/시간 초과·전체 풀의 미해결. OFF 선택장르100%의 불가가 입증되지 않았다면80% 보완으로 넘어가지 않음|

공통 details는 `candidate_count`, `total_ms`, `min_duration_ms`, `target_duration_ms`, `max_duration_ms`, `selected_genre_codes`, `genre_candidate_counts`, `missing_genres`, `missing_genre_labels`, `distinct_genre_representatives_possible`, `parent_track_count`, `required_new_count`, `available_new_count`, `checked_full_candidate_pool`입니다. 필요한 사유에 `solver_windows`·`genre_share_stage`·선택장르 총ms/필요ms를 추가합니다. `checked_full_candidate_pool=true`는 전체 입력 후보의 준비 지표를 검사했다는 뜻이며 UNKNOWN의 조합 불가 증명으로 사용하지 않습니다. 현재 CSV 프리뷰의 `FEASIBLE_GREEDY_PREVIEW`/`FEASIBLE_PREVIEW`는 가능 조합 시험이며 운영 최적 시간/품질 입증이 아닙니다.

`frontend/src/features/recommendation/RecommendationErrorNotice.tsx`는 위3종 오류에서 [선택 조건 확인]으로 음악 선택 영역에 초점을 이동하고 연결 장애의 재연결 안내와 구분합니다. `PublicPage.tsx`가 해당 콜백과 상태를 공급합니다. 사용자 선택을 자동으로 줄이거나 ON을 OFF로 바꾸지 않습니다. 통합 백엔드77건·프런트15건/빌드 PASS를 확인했으며 실제 새 요청 결과·매핑 확인 수·브라우저 회귀는 [일반 추천 분리 수용 기록](../acceptance/일반_추천_후보와_재생시험_분리_검증_20261016.md)에 연결합니다. 아래61건/47곡 수치는 앞 단계의 검증 이력입니다.

[실제 부족 회귀](../acceptance/assets/general-pool-shortage-result-20261016.json)는 별도 임시 탭에서 `ON/auto/instrumental_only/OPERA`를 요청해 전체86,485곡에서 공통113곡·날씨 탈락109곡·최종4곡/577,894ms를 확인했습니다. 오류는 `CANDIDATE_SHORTAGE`·`TOTAL_DURATION_BELOW_MINIMUM`이고 화면에서 “후보4곡·총9분37초·최소176분 미달”과 [선택 조건 확인]을 관측했으며 연결 재시도 버튼은 없었습니다. 후속 탭이 유지되지 않아 버튼 클릭 뒤 실제 초점 이동·해당 화면 스크린샷은 미확인입니다. 메시지/버튼 관측을 실제 초점 이동까지 성공한 것으로 확대하지 않습니다.

## 앞 단계47곡 전체 연결 검증 이력 — 2026-10-16

사용자는 기존47곡의 영상 매핑과 전체 연속 재생을 요청했고, 한국에서 차단된 `I'll Shut up Now (feat. Willie Nelson)`를 같은 날씨·장르 기준의 곡1곡으로 교체하도록 선택했습니다. GENERAL·맑음 W100·FOLK_COUNTRY·medium인 `All on Me`(Devin Dawson)로 교체했습니다. 나머지46곡의 원본ID·점수는 유지합니다.

최초 후보47개 중4개는 제목/길이가 조회되어도 `UNPLAYABLE`이었으며 실제 YouTube 목록에서도 생략됐습니다. 동일 곡의 다른 공식 배포본3개와 승인된 새 곡1개를 사용해 이를 해결했습니다. [최종 매핑](../../analysis/youtube_mapping_20261016/mapping-47-verified-v1.json)·[명시 선택](../../analysis/youtube_mapping_20261016/playback-selection-v1.json)·[실제47개 목록](../../analysis/youtube_mapping_20261016/native-final-47-observed.json)·[당시 수용 기록](../acceptance/YouTube_47곡_매핑_검증_20261016.md)에 연결합니다.

`seed_csv_preview --youtube-mappings … --playback-selection …`은 LOCAL_DEMO에서만 명시한47곡의 별도 test Catalog를 만듭니다. 원본 바이트 해시·GENERAL·고유ID·존재·전곡 VERIFIED를 확인하며 실패하면 기존 카탈로그를 유지합니다. 당시에는 이 최신47곡 카탈로그가 기본 로컬 요청에도 선택돼 제한된 재생 시험 결과를 만들었습니다. 위 후속 수정 이후 신규 일반 요청·사전 로딩에서는 이 종류를 제외합니다. 명시 선택을 다시 적재하는 것으로 일반 추천 기본 풀이47곡으로 돌아가지 않으며, 과거47곡 결과·부모 고정과 보관은 유지합니다.

기존 Django API/worker가 새47곡·10,632,974ms(177분12.974초) 결과를 만들었고, 기존 PublicPage에서47/47 확인·곡별 직접 영상·전체 임시 목록 버튼을 확인했습니다. 원본 길이 합과 YouTube 메타데이터 정수초 합10,648초(177분28초)는 다르며 광고·버퍼링을 포함하지 않습니다. 원본 미검수 CSV의 preview_only=true/validation_passed=false도 그대로 유지합니다. 영상 매핑 VERIFIED는 공식 메타데이터·국내 제공·목록ID/순서 대조의 범위이며 파형 동일성·전곡 청취 검수/운영 Gold를 의미하지 않습니다.

최종47곡 목록에서 첫 곡 Teeje Week가 끝난 뒤 Next 클릭 없이 두 번째 곡 Computadores Fazem Arte로 전환되어 재생되는 것을 확인했습니다. [자연 전환 관측](../../analysis/youtube_mapping_20261016/natural-transition-observed.json)에 기록했습니다. 기존 대시보드에서 곡 제외 시 전체 링크가 보류되고 제외 취소 시 복원되는 것도 [실제 UI 관측](../../analysis/youtube_mapping_20261016/dashboard-exclusion-gate-observed.json)으로 확인했습니다.

백엔드61건·Python20파일/162심벌/누락0을 통과했습니다. 프런트 코드는 이번 데이터 연결에서 변경하지 않았습니다. 기존 프런트11건/빌드 결과는 앞 연결 작업의 검증이고, 이번 변경은 실제 새 결과와 브라우저 연결을 검증합니다.

## 읽은 기준과 변경 경계

최신 사용자 정정을 우선하고 [서비스 흐름](../product/카페_음악_서비스_기능_및_사용자_흐름_정리.md), [구현 설계](../product/카페_음악_서비스_구현_설계도.md), [추천 가이드](../product/카페_음악_추천_서비스_3차_컬럼_기반_추천_로직_가이드.md), [구현 태스크](../product/카페_음악_추천_서비스_3차_구현_태스크.md)를 함께 대조했습니다. 음악 ON/OFF·176~184분·원본18개와 검수 보조·사이클·평가/제외/승인 규칙은 유지합니다. 수령 원문을 고치지 않고 현행 가이드와 라우팅에 연결했습니다.

기존 React `PublicPage`와 Django 로컬 시험 경로에 중앙 플레이어와 별도 영상 후보 조회를 연결하며 FastAPI는 목표 계약입니다. `prototype/youtube-player/`의 이전 독립 iframe 도구는 검수 보조/이력으로 보존하고 이번 중앙 플레이어와 구분합니다. 공유 DB·운영 날씨·계정 OAuth·외부 재생목록 저장·배포는 이번 연결의 완료 범위가 아닙니다.

## 공급·소비와 수정 위치

| 파일/경로 | 공급·소비와 역할 |
|---|---|
| `backend/recommendation/occasion.py` → `seed_csv_preview.py` | 원본/판정 해시와 버전 검증 후 GENERAL만 새 test Catalog로 적재. 이전 카탈로그 보존 |
| `backend/recommendation/youtube.py` → 같은 seed | 선택 `YOUTUBE_MAPPING_V1`의 VERIFIED 원곡·영상·검수 근거를 새 카탈로그에 불변 저장 |
| `backend/recommendation/youtube_playback.py` | `validate_playback_request`·`resolve_playback_candidates`: 기존 매핑 우선·공식 검색/메타데이터 규칙·별도 Django 캐시. 상세는 [자동 검색 라우팅](./YouTube_자동검색_변경_라우팅.md) |
| `backend/recommendation/service.py` → `catalog()`/신규 `enqueue()` | `current_catalog()`가 고정 재생 선택 카탈로그를 신규 일반 요청에서 제외. 기존 작업/부모는 고정 카탈로그 유지 |
| `backend/recommendation/worker.py` → `warm_current_catalog()` | 같은 일반 카탈로그 선택 기준으로 사전 로딩하고 검증 캐시는 카탈로그 버전/해시에 귀속 |
| `backend/recommendation/solver.py` → `choose_preview()` | 전체 입력 후보 수/총시간·장르별 수/대표 배정·신규곡 필요 수를 검사하고 증명된 부족과 탐색 미완료를 구분 |
| 기존 추천 worker/API → `frontend/src/shared/types.ts` | 요청 조건에 맞는 결과의 items와 선택 `youtube_video_id`/`youtube_match_status`를 전달 |
| `frontend/src/features/recommendation/youtubeDestinations.ts` | 검증 영상 watch URL, 원문 곡명·아티스트 검색 URL, 전곡 원순서의 임시 목록 URL 구성 |
| 같은 폴더 `YoutubeLinks.tsx`·`YoutubeLinks.css` | 현재는 곡별 `YoutubeTrackLink`만 소비. 과거 `YoutubePlaylistLinks` 전체 영역/스타일은 보존하되 PublicPage에서 미표시 |
| 같은 폴더 `PublicPage.tsx` | 중앙 `YoutubePlayer`·행 보조 링크 연결. 안내·생성·저장·조건/제외 미반영 상태를 플레이어 gate로 전달 |
| 같은 폴더 `YoutubePlayer.tsx`·`YoutubePlayer.css` | 중앙의 보이는 iframe·현재 곡/후보·재생/보류/실패 목록 표시. 기존 선택·목록·평가 영역과 연결 |
| 같은 폴더 `youtubePlayerController.ts`·`youtubeIframeApi.ts` | 현재 곡 후보 요청·공식 Player API 로딩·PLAYING/ENDED 진행·차단/대안/환경 오류·큐 취소 제어 |
| 같은 폴더 `youtubePlayer.test.ts` | 모의 플레이어 사건으로 한 번만 진행·자동재생 대기·제한된 대안·검색/환경 오류 보류·상태 변경 취소 확인. 실제 음악 재생과 구분 |
| 같은 폴더 `youtubeIframeApi.test.ts` | 공식 스크립트 단일 로딩/재시도·기존 콜백·실제 iframe 준비 제한·폐기된 인스턴스 사건 무시 검증 |
| 같은 폴더 `youtubeLinks.test.ts` | 인코딩·VERIFIED·ID·순서/중복·전곡 누락·제외/상태 보류·새탭/이벤트 격리 검증 |
| 같은 폴더 `RecommendationErrorNotice.tsx`·`recommendationErrors.test.ts` | 추천 조건 오류의 조건 확인과 연결 장애의 재연결 동작·문구 분리/검증 |

현재 주 재생 경로는 중앙 iframe이며 `youtubeTemporaryQueueUrl`과 저장형 URL 검사 `nativeYoutubePlaylistUrl`은 보관된 외부 열기 유틸입니다. 현재 전체 링크 영역은 렌더링하지 않습니다. 유틸을 사용할 경우 전곡 검증ID/원순서·상태 gate를 유지하고 반환된 임시 `TL...`을 계정에 저장한 목록으로 취급하지 않습니다.

외부 전체 링크는 미확정 곡을 생략하거나 여러 곡의 중복 영상ID를 임의로 합치지 않습니다. 중앙 iframe에서 대안 소진으로 건너뛴 곡은 별도 실패로 보존하고 전체 원곡 재생 성공으로 표시하지 않습니다. 현재 선택/제외가 미반영됐으면 재생과 전체 이동을 보류합니다. 승인 자체를 재생의 새 필수 조건으로 추가하지 않습니다. 재생/링크 클릭은 추천·Gemini·평가·제외·승인을 변경하지 않습니다. 원래 Spotify `play_url`도 유지합니다.

## 계약 JSON과 회귀 대조

[JSON 계약](../contracts/3차_공통_API_이벤트.schema.json)·[고정 예시](../fixtures/3차_공통_계약_예시.json)를 확인했습니다. 이 파일은 입력·피드백·제외·승인 계약이며 전체 playlist items DTO는 정의하지 않습니다. 제외 조회의 `items`는 여전히 track_id/track_name/artists_name 3개만 반환합니다. 앞 단계 선택 YouTube 메타데이터는 로컬 카탈로그/결과 스냅샷과 프런트 타입에, 이번 재생 후보 응답은 별도 소유 검사 조회/자동 검색 라우팅에 정의했습니다. 기존 피드백/제외 이벤트에 후보를 섞지 않으므로 해당 schema/fixture를 변경하지 않았습니다.

앞 연결 단계에서는 백엔드 전체57건·프런트11건·빌드를 통과했습니다. 당시 실행 환경, 실제 CSV47곡·원본 길이 합, 브라우저 조작, 별도 네이티브2곡 자동 전환과 남은 범위는 [이전 수용 기록](../acceptance/기존_대시보드_YouTube_연결_검증_20261016.md)에 보존합니다.47곡 연결 시점의 Python20개·심벌162개와 후속 코드 검사는 [AST 색인](../music-playback-routing/README.md)에 연결합니다. TypeScript는 해당 Python 검사 대상이 아니므로 위 파일표와 프런트 테스트로 연결을 검증했습니다.

## 다음 담당 인계

중앙 iframe 구현/일부 재생·실제 Data API 키 대기를 위 새 관측으로 인계합니다. 과거47곡 네이티브 전환과 일반45곡 생성은 중앙 삽입의 완료 증거가 아닙니다. PL·C는 자동 후보와 원곡/버전 확정·청취 검수를, B·C는 키 설정 후 실제 검색/한도·분리 캐시를, INF는 실제 Chrome 프로필·소리·장시간/다중 프로세스 환경을 추가 확인합니다. 원본176~184분과 실패/광고/영상 길이 차이가 있는 실제 재생시간을 구분합니다. Git 커밋·푸시·PR·병합·외부 계정 변경은 실행하지 않았습니다.
