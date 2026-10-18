# 로컬 음악 재생 라우팅 색인

- 작성일/수정일: 2026-10-16
- 담당: 로컬 음악 재생 통합팀
- 기준: feature/ad-logic / f22f974
- 범위: 검사기가 수집한 신규/변경 Python 파일 전체. 기존 V2·통계 분석은 현행 후보의 보존 의존성이며 이번 작업에서 코드를 변경하지 않았습니다.
- 기존 docs/backend-routing과 수령 원문을 수정하지 않습니다.

## 계약과 실제 흐름

원본 CSV → 보존 V2 정책/날씨 풀 → music_playback의 별도 행사 판정 → GENERAL 전체 풀/3시간 예시로 연결합니다. GENERAL 판정은 기존 Django 로컬 CSV seed/추천 결과와 연결하며, 최신 사용자 선택은 기존 React PublicPage의 외부 YouTube 기본 재생과 접이식 iframe 보조입니다. API 키·LLM 없이 별도 registry의 방식별 검수 완료 영상을 재사용합니다. 기존 자료의 VERIFIED는 iframe 검수로 승계하지 않으며, 엄격한 원곡 메타데이터/native 큐 근거를 확인한 native 전용 승계는 명시 CLI로만 허용합니다. 공식 Data API는 명시 OPTIONAL_SEARCH 경로로 보존합니다. 아래 중앙 iframe 주 경로·최초 loopback PlaylistStore/iframe 큐·공식 검색 기본 경로는 이전 단계의 이력입니다. 통계 진단/검수 표본은 보완 근거이며 실재생의 필수 호출이나 학습된 정답이 아닙니다. FastAPI는 목표 스택이고 공유 운영 DB·운영 날씨 연결 완료로 보고하지 않습니다.

정본과 원문 차이는 [정본 변경 라우팅](../development/음악_재생_정본_변경_라우팅.md), 데이터 실행·전수 검증은 [시즌 필터 라우팅](../development/음악_시즌필터_변경_라우팅.md), 단계/입출력·실제 재생 한계는 [재생 가이드](../development/music/YouTube_로컬_재생_기획과_구현_가이드.md)를 확인합니다.

## API 키 없는 등록·검수와 외부 재생 — 현행

기존 추천 전체 GENERAL 후보와 결과는 보존하고 운영자 URL·CSV 등록 → 방식별 검수 → 외부 native 임시 큐 또는 보조 iframe을 연결합니다. native_verified와 iframe status는 독립이며 iframe BLOCKED가 native 사용을 막지 않고 native 승인만으로 iframe을 승인하지 않습니다. 로컬 보조 SQLite의 곡별 revision·대안·감사를 사용하며 음악18개/RDB정본·불변 카탈로그/결과를 변경하지 않습니다. 외부 큐는 원래 순서와 중복 video_id·누락을 명시하고 준비된 곡만 여는 부분 큐는 전체 완료와 구분합니다. 보조 iframe의 미연결·검수 전·차단은 MAPPING_REQUIRED, 운영 연결/저장소 기술 장애는 SEARCH_UNAVAILABLE입니다. 공개 재생 오류를 전역 BLOCKED로 자동 변경하지 않습니다. 건너뛴 시간이 있으면 원래 176~184분 선곡표를 실제 3시간 재생 완료로 표시하지 않습니다. 외부 임시 큐는 계정에 저장한 재생목록이 아닙니다.

| 소스 | 목적 | 1:1 문서 |
|---|---|---|
| `backend/recommendation/youtube_registry.py` | 보조 SQLite·곡별 revision·원자 등록·native/iframe 독립 검수/철회·명시 기존 자료 승계 | [짝 문서](files/backend/recommendation/youtube_registry.py.md) |
| `backend/recommendation/youtube_review_api.py` | LOCAL_DEMO 접근코드·CSRF·곡/소유 확인·등록/검수 API 8개 | [짝 문서](files/backend/recommendation/youtube_review_api.py.md) |
| `backend/recommendation/management/commands/init_youtube_review.py` | 비밀값 비출력 로컬 코드 초기화·회전과 기존 ID 재검수 seed | [짝 문서](files/backend/recommendation/management/commands/init_youtube_review.py.md) |
| `backend/recommendation/youtube_queue_api.py` | 본인 선곡표의 원래 순서·방식별 검수·중복/누락을 보존한 외부 임시 큐 | [짝 문서](files/backend/recommendation/youtube_queue_api.py.md) |
| `backend/recommendation/tests/test_youtube_queue_api.py` | 외부 큐 순서/불변·부분/중복·iframe 대체 금지·소유/운영 5건 | [짝 문서](files/backend/recommendation/tests/test_youtube_queue_api.py.md) |
| `backend/recommendation/tests/test_keyless_playback.py` | 원문/API 검색 우회 금지·검수 대안·차단·기술/운영 분리 4건 | [짝 문서](files/backend/recommendation/tests/test_keyless_playback.py.md) |
| `backend/recommendation/tests/test_youtube_registry.py` | URL/CSV·revision·독립 승인/철회·길이 명시 예외·보안·비출력 격리 16건 | [짝 문서](files/backend/recommendation/tests/test_youtube_registry.py.md) |
| `backend/recommendation/tests/test_youtube_review_api.py` | 코드/CSRF/소유·과거 본인 곡·잘못된 CSV 전체 거절·독립 승인/철회·운영 503 10건 | [짝 문서](files/backend/recommendation/tests/test_youtube_review_api.py.md) |

기존 settings.py의 KEYLESS 기본값과 선택 공식 검색, urls.py의 검수 경로 8개와 외부 큐 GET, youtube_playback.py의 _keyless_candidates, 기존 검색/API 시험의 OPTIONAL_SEARCH override도 각각 짝 문서에 반영했습니다. 접근코드는 Git 제외 파일에서 로컬 운영자가 확인하고 화면 메모리에만 입력하며, 공유 ADMIN·운영 DB/AWS는 별도 연결입니다. 상세 계약 → 코드 → 검증은 [키 없는 등록·검수 통합 라우팅](../development/YouTube_키없는_등록과_검수_변경_라우팅.md)을 따릅니다. 아래 각 단계의 숫자는 당시 이력이며 최신 검사 수는 `.local-preview-logs/keyless-routing-audit.json` summary를 정본으로 확인합니다.

최종 AST 재검사는 exit0/summary.ok=true, Python39개·심벌406개·누락0입니다. 통합 담당은 백엔드 전체136건 통과와 프런트 빌드를 확인했습니다. 실제 외부 YouTube 대기열47개와 첫→둘째→셋째 곡 자동 진행 관찰은 [관측 JSON](../acceptance/assets/keyless-native47-natural-transition-20261016.json)과 [재생 화면](../acceptance/assets/keyless-native47-playing-20261016.png)을 확인합니다. Next 수동 클릭 없이 관측한 범위이며 전곡 완청·3시간 경과·사용자 Chrome/Premium·물리적 소리는 확정하지 않습니다.

| 소스 | 목적 | 1:1 문서 |
|---|---|---|
| `analysis/weather_music_20261016/analyze.py` | V2 날씨 점수·전체 풀·3시간 분석의 원래 재현 코드 | [짝 문서](files/analysis/weather_music_20261016/analyze.py.md) |
| `analysis/weather_music_20261016/archive/v1/analyze.py` | V1 단일 패턴 분석의 보존 이력 | [짝 문서](files/analysis/weather_music_20261016/archive/v1/analyze.py.md) |
| `analysis/weather_music_20261016/diagnostics_20261016/build_diagnostics_notebook.py` | 통계 진단 노트북 생성·실행 보조 | [짝 문서](files/analysis/weather_music_20261016/diagnostics_20261016/build_diagnostics_notebook.py.md) |
| `analysis/weather_music_20261016/diagnostics_20261016/build_review_sample.py` | LLM/사람 검수 대상 500곡의 결정적 표본 생성 | [짝 문서](files/analysis/weather_music_20261016/diagnostics_20261016/build_review_sample.py.md) |
| `analysis/weather_music_20261016/diagnostics_20261016/profile_analysis.py` | 음악 특성의 분포·상관·동점·검토 플래그 진단 | [짝 문서](files/analysis/weather_music_20261016/diagnostics_20261016/profile_analysis.py.md) |
| `analysis/weather_music_20261016/diagnostics_20261016/sensitivity_analysis.py` | 원래 정책을 보존하는 OAT 민감도 분석 | [짝 문서](files/analysis/weather_music_20261016/diagnostics_20261016/sensitivity_analysis.py.md) |
| `analysis/weather_music_20261016/diagnostics_20261016/validate_diagnostics.py` | 통계 진단의 독립 원본·계산 대조 | [짝 문서](files/analysis/weather_music_20261016/diagnostics_20261016/validate_diagnostics.py.md) |
| `music_playback/__init__.py` | 로컬 시즌 필터 패키지 선언 | [짝 문서](files/music_playback/__init__.py.md) |
| `music_playback/__main__.py` | build/verify 명령 진입점 | [짝 문서](files/music_playback/__main__.py.md) |
| `music_playback/candidates.py` | 일반 운영 후보와 3시간 예시 생성 | [짝 문서](files/music_playback/candidates.py.md) |
| `music_playback/seasonality.py` | 별도 행사 상태·근거·버전 판정 | [짝 문서](files/music_playback/seasonality.py.md) |
| `music_playback/verify.py` | 저장된 일반 후보의 독립 검증 | [짝 문서](files/music_playback/verify.py.md) |
| `prototype/youtube-player/server.py` | loopback 전용 플레이어·큐/영상 매핑 로컬 HTTP 서버 | [짝 문서](files/prototype/youtube-player/server.py.md) |
| `prototype/youtube-player/tests/test_server.py` | 로컬 HTTP·매핑·선택 검색의 오프라인 회귀검증 | [짝 문서](files/prototype/youtube-player/tests/test_server.py.md) |
| `tests/test_music_candidates.py` | 일반 후보·시간 탐색의 단위 검증 | [짝 문서](files/tests/test_music_candidates.py.md) |
| `tests/test_music_seasonality.py` | 행사 판정과 오탐 방지의 단위 검증 | [짝 문서](files/tests/test_music_seasonality.py.md) |

## 재검사

```powershell
python -X utf8 C:/Users/이해나/.codex/skills/routing-doc-auditor/scripts/audit_routing.py --repo . --routing-dir docs/music-playback-routing --format json --output .local-preview-logs/music-playback-routing-audit.json
python -m unittest discover -s tests -p 'test_music_*.py' -v
python -m unittest discover -s prototype/youtube-player/tests -v
```

검사 범위/누락 수는 위 JSON summary에서 확인합니다. AST 문서 통과는 음성 출력·YouTube 계정/Premium·영상 길이·광고/버퍼링·3시간 연속 재생 완료를 뜻하지 않습니다. 실제 브라우저 관찰은 재생 담당의 별도 기록을 확인합니다.

2026-10-16 실제 실행 결과: 검사기 exit0/summary.ok=true, 변경 Python16개·심벌139개·누락0입니다. 시즌 필터/시간 탐색 단위 검증15건과 재생 서버의 오프라인/loopback HTTP 검증9건, 합계24건이 통과했습니다. 이 색인과 짝 문서17개의 내부 링크 누락·행 끝 공백도0건입니다. 원본 분석 재실행·외부 YouTube API 호출은 이 라우팅 검증에서 수행하지 않았습니다.

## 기존 대시보드 CSV 추천 연결 후속

사용자 정정에 따라 기존 공개 대시보드의 로컬 CSV 추천을 행사 스크린된 새 test Catalog에 연결합니다. 외부 YouTube 이동은 선택 영상 매핑 snapshot 또는 원곡명·아티스트의 검색 URL을 사용하며, 임베드 제한을 검증 완료로 바꾸지 않습니다. 운영 FastAPI/공유 DB·새 migration은 별도입니다.

| 소스 | 목적 | 1:1 문서 |
|---|---|---|
| `backend/recommendation/management/commands/seed_csv_preview.py` | 기존 사용자 대시보드 로컬 CSV 프리뷰 적재 연결 | [짝 문서](files/backend/recommendation/management/commands/seed_csv_preview.py.md) |
| `backend/recommendation/occasion.py` | 로컬 CSV 추천용 행사 판정 snapshot 로더 | [짝 문서](files/backend/recommendation/occasion.py.md) |
| `backend/recommendation/tests/test_occasion.py` | 기존 대시보드 API·행사 판정·영상 snapshot 통합 검증 | [짝 문서](files/backend/recommendation/tests/test_occasion.py.md) |
| `backend/recommendation/youtube.py` | 외부 YouTube 이동용 검증 원곡 매핑 snapshot 로더 | [짝 문서](files/backend/recommendation/youtube.py.md) |

후속 검증은 루트 `.venv` Python3.12.13으로 `C_LOCAL_DEMO=1`을 설정하고 `.\.venv\Scripts\python.exe -m backend.manage test backend.music backend.recommendation.tests --verbosity 1`을 실행했으며 전체57건(신규7)이 메모리 DB에서 통과했습니다. 실제 CSV 적재·사용자 대시보드 기동·브라우저 이동은 통합 담당의 기록을 따릅니다.

후속 통합 검사기 결과는 exit0/summary.ok=true, 변경 Python20개·심벌156개·누락0입니다. 실제 기존 대시보드47곡·177분32.228초와 영상확인0/47·곡별 검색·네이티브2곡 진단은 [새 수용 기록](../acceptance/기존_대시보드_YouTube_연결_검증_20261016.md), Python 검사 대상 밖의 TypeScript 연결은 [화면 라우팅](../development/기존_대시보드_YouTube_연결_라우팅.md)을 확인합니다.

## 47곡 명시 선택 후속 검증

사용자 승인 교체1곡을 포함한47곡을 기존 대시보드의 새 로컬 test Catalog로 연결했습니다. `seed_csv_preview.py`의 `load_playback_selection`과 `--playback-selection`은 원본 해시·GENERAL·고유ID·전곡 VERIFIED를 확인하고 이전 카탈로그를 보존합니다. 짝 문서와 `test_occasion.py`의 선택/거부/보존 검증도 함께 갱신했습니다.

이번 검사기 결과는 exit0/summary.ok=true, Python20개·심벌162개·누락0이고 백엔드 전체61건이 통과했습니다. 위57건/156심벌은 앞 연결 단계의 이력입니다. 실제47/47 영상 확인·목록 순서·첫→둘째 곡 자연 전환과 남은 청취 범위는 [47곡 수용 기록](../acceptance/YouTube_47곡_매핑_검증_20261016.md)을 따릅니다.

## 일반 추천 후보와 고정 재생 시험 분리 후속

최신 고정 47곡 카탈로그가 신규 일반 추천에도 선택되어 장르 필터 후 3곡·12분37.825초만 남은 원인을 수정했습니다. 일반 추천용 전체 GENERAL 카탈로그와 고정 재생 시연의 용도를 분리합니다. 목표 180분·허용 176~184분·선택 장르·사이클 고정 정책은 완화하지 않습니다.

| 소스 | 목적 | 1:1 문서 |
|---|---|---|
| `backend/recommendation/service.py` | 신규 일반 추천의 전체 카탈로그 선택·고정 재생 subset 제외·부모 고정 | [짝 문서](files/backend/recommendation/service.py.md) |
| `backend/recommendation/worker.py` | 같은 카탈로그 사전 로딩·후보 수/시간 진단·실패 근거 저장 | [짝 문서](files/backend/recommendation/worker.py.md) |
| `backend/recommendation/solver.py` | 전체 후보 부족·신규곡 부족·제한 탐색 미완료 구분 | [짝 문서](files/backend/recommendation/solver.py.md) |
| `backend/recommendation/tests/test_api.py` | 일반 선택/사전 로딩·503·운영 범위·과거 결과/부모 보존 회귀 | [짝 문서](files/backend/recommendation/tests/test_api.py.md) |
| `backend/recommendation/tests/test_preview_shortage.py` | 후보 부족/불충분 탐색·OFF 단계·신규곡 판정 11건 | [짝 문서](files/backend/recommendation/tests/test_preview_shortage.py.md) |

`service.current_catalog`는 로컬 ready 시험 카탈로그에서 `source_ref=local-preview:youtube-playback-selection:…`인 고정 재생 목록을 제외합니다. `catalog`가 신규 요청에 이 기준을 적용하고 `worker.warm_current_catalog`가 동일 helper를 사용합니다. `enqueue`의 부모 결과는 원래 catalog_id를 계속 사용합니다. 과거 47곡 카탈로그/선곡표는 보존하며 전체 카탈로그가 없으면 명확한 POLICY_NOT_READY/503을 반환합니다. 사용자 임의 카탈로그 선택 API는 추가하지 않습니다.

후보 진단은 공통 필터 전후·날씨 탈락 수·총시간·누락 장르·장르별 수·필요 신규곡 수를 포함합니다. 전체 필요조건이나 전체 조합 INFEASIBLE로 부족을 입증한 경우 CANDIDATE_SHORTAGE/422, 가용 신규곡 부족은 NO_MEANINGFUL_CHANGE/422, 제한 창·UNKNOWN/시간 초과는 SEARCH_INCOMPLETE/503으로 구분합니다. 상세 reason을 Job.error → 폴링 → 기존 대시보드 안내로 전달하고 선택 조건·기존 결과를 보존합니다.

카탈로그 API 표적 5건과 프리뷰 부족/탐색 표적 11건이 통과했습니다. 프런트 15건과 빌드도 통과했으며, 실제 전체 백엔드·전체 GENERAL 요청·브라우저 결과와 미실행 항목은 [일반 추천/재생 시험 분리 수용 기록](../acceptance/일반_추천_후보와_재생시험_분리_검증_20261016.md)을 따릅니다. 이 후속의 AST 검사 결과는 exit0/summary.ok=true, 변경 Python25개·심벌224개·누락0입니다. 위 20개/162심벌은 이전 단계의 보존 기록입니다. 수령 원문·기존 backend-routing·원본 데이터/음악 점수는 수정하지 않습니다.

## 중앙 iframe·공식 검색 후속

최신 사용자 정정으로 기존 대시보드 중앙 앨범 영역의 공식 YouTube iframe·자동재생 시도·실제 종료 이벤트 뒤 다음 곡을 주 경로로 연결했습니다. 이전 전체 네이티브 목록 이동은 보조 기능/검증 이력입니다. 공식 IFrame API·기존 매핑·공식 Data API 규칙 검색을 사용하며 LLM을 재생 필수 조건으로 두지 않습니다. 키 없음·자동재생 차단·삽입 제한150/153은 상태로 표시하고 우회하지 않습니다.

| 소스 | 목적 | 1:1 문서 |
|---|---|---|
| `backend/cafe/settings.py` | 서버 전용 검색 키·시간 제한·분/일 보호 한도·캐시 TTL | [짝 문서](files/backend/cafe/settings.py.md) |
| `backend/cafe/urls.py` | 본인 선곡표의 YouTube 재생 조회 POST 등록 | [짝 문서](files/backend/cafe/urls.py.md) |
| `backend/recommendation/api.py` | CSRF/소유·제외 반영·결과 내 곡 확인 뒤 resolver 연결 | [짝 문서](files/backend/recommendation/api.py.md) |
| `backend/recommendation/youtube_playback.py` | 기존 VERIFIED 또는 공식 검색 CANDIDATE·분리 캐시·후보/검색 한도 | [짝 문서](files/backend/recommendation/youtube_playback.py.md) |
| `backend/recommendation/tests/test_youtube_playback.py` | 네트워크 없는 검색/필터·캐시/한도·불변성 회귀 18건 | [짝 문서](files/backend/recommendation/tests/test_youtube_playback.py.md) |
| `backend/recommendation/tests/test_youtube_playback_api.py` | 재생 조회·키 없음·소유/CSRF·잘못된 입력·업무 상태 보존 6건 | [짝 문서](files/backend/recommendation/tests/test_youtube_playback_api.py.md) |

`POST /api/playlists/{playlist_id}/youtube-playback`은 track_id와 시도에서 제외할 video_id 목록만 받습니다. 본인 결과와 제외 반영 상태를 확인한 후 당시 곡 snapshot을 resolver에 공급합니다. 음악 DB·카탈로그·원본 매핑·추천 점수·Job·승인/평가는 바꾸지 않으며 별도 검색 캐시/보호 카운터만 사용할 수 있습니다. 기존 VERIFIED와 자동 CANDIDATE·청취 검수·실제 플레이 상태는 구분합니다.

이 단계의 백엔드 전체101건은 통과했습니다. 최종 AST 검사는 exit0/summary.ok=true, 변경 Python31개·심벌306개·누락0이며 `.local-preview-logs/music-playback-routing-audit.json` summary를 정본으로 확인합니다. Python 밖의 중앙 UI·IFrame 이벤트·실제 관찰과 미실행 항목은 [중앙 iframe 수용 기록](../acceptance/대시보드_중앙_YouTube_iframe_검증_20261016.md), 호출·응답·캐시 상세는 [자동 검색 변경 라우팅](../development/YouTube_자동검색_변경_라우팅.md)을 따릅니다. 실제 서버 API 키가 없어 공식 검색의 실호출은 검증 대기이며 물리적 소리·Chrome/Premium·전곡 재생 완료를 단위/AST 검사 통과로 확정하지 않습니다.

## 추천 선곡 성능 개선 후속 — 2026-10-19

R-02/R-04의 성능 부분을 검증된 카탈로그 작업자와 선택 장르 규칙 solver에 연결합니다. 점수식·후보 정책·176~184분 계약·API/저장 스키마는 유지합니다. 자세한 기준→코드→실제 CSV 대조는 [추천 선곡 성능 개선 변경 라우팅](../development/추천_선곡_성능개선_변경_라우팅.md)을 확인합니다. 넓은 후보/OFF 순회는 기존 경로를 유지하고, 좁은 ON 상속 장르·속도 조건에만 버전별 인덱스를 적용합니다.

| 소스 | 목적 | 1:1 문서 |
|---|---|---|
| `backend/recommendation/candidate_index.py` | 버전별 bitset 후보 필터와 기존 정책 점수/감사값 보존 | [짝 문서](files/backend/recommendation/candidate_index.py.md) |
| `backend/recommendation/worker.py` | 검증 카탈로그에서 상속 필터를 전달하고 선택적으로 인덱스 조회 | [짝 문서](files/backend/recommendation/worker.py.md) |
| `backend/recommendation/matching.py` | solver와 exact search의 공통 결정적 장르 매칭 | [짝 문서](files/backend/recommendation/matching.py.md) |
| `backend/recommendation/exact_search.py` | 증명 가능한 시간·점수·장르 exact path와 CP-SAT fallback | [짝 문서](files/backend/recommendation/exact_search.py.md) |
| `backend/recommendation/solver.py` | 정확 검색 라우팅·장르 제약·목적/tie 분할 | [짝 문서](files/backend/recommendation/solver.py.md) |
| `backend/recommendation/tests/test_candidate_index.py` | 상속 필터·캐시·vocal·감사 집계 동등성 | [짝 문서](files/backend/recommendation/tests/test_candidate_index.py.md) |
| `backend/recommendation/tests/test_exact_search.py` | 장르 비율·대표·동점 및 CP-SAT 대체 경로 비교 | [짝 문서](files/backend/recommendation/tests/test_exact_search.py.md) |

86,485개 실제 GENERAL CSV 후보의 네 조건에서 ID·정확 점수·감사 집계가 전체 순회와 같았습니다. 좁은 ON 후보 생성은 로컬 검사에서 인덱스 재사용 뒤 약 0.6ms였습니다. 넓은 조건은 인덱스가 더 느린 측정이 있어 기존 순회를 유지합니다. 해당 수치는 전체 선곡 API/AWS 응답 P95나 동시 작업 부하가 아닙니다.
