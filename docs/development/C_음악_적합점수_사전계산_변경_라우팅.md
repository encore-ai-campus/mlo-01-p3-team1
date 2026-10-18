# C 음악 적합 점수 사전 계산 변경 라우팅

- 작성·수정일: 2026-10-16
- 담당: C — 공개 추천·음악 데이터
- 범위: M-01~M-05, A-05/A-06, R-02/R-03, Q-01
- 작업 브랜치/기준 커밋: `feature/integration` / `3471175`
- 상태: 코드·로컬 CSV 프리뷰 검증 완료. 운영 PostgreSQL/S3·곡 검수·청취 수용·화면 지연 통합 검증은 별도입니다.

## 기준과 사용자 결정

- [ON/OFF 후보 산출 가이드](../product/카페_음악_추천_서비스_3차_컬럼_기반_추천_로직_가이드.md), [공통 개발 계약](../product/3차_공통_개발_계약과_검증_기준.md), [음악 통합 계약](../product/3차_음악_정책_통합_계약.md), [저장소 경계](../product/3차_저장소_경계와_발행_계약.md)를 확인했습니다.
- 수령 입력은 [CSV](../handoff/music/spotify_dataset.csv), [음악 컬럼·변환](../handoff/music/음악_분류_컬럼_정의_및_변환_규칙.md), [테마·장르](../handoff/music/테마_장르_정의.md), [음악 테이블](../handoff/music/테이블_구조_설계.md)입니다. 수령 자료 자체는 변경하지 않았습니다. 저장소 CSV의 실제 바이트 SHA-256은 `335e5ee0a07a3f30b20ca9860c87562c98082a032e0ecd90e8ca0a86d965fe58`이며 수령 문서의 원본 해시와 줄바꿈 차이가 있습니다. 로컬 프리뷰는 정규화된 LF 해시도 확인하되 실제 입력 해시를 기록합니다.
- 최신 사용자 결정: PostgreSQL에 곡별 날씨·테마 적합 점수를 계산해 저장하고 선곡에 사용합니다. 확정 mood·main_inst 태그를 CSV에서 만들어 넣지 않습니다. 현재 물리 구현은 기존 `Catalog.tracks`의 버전별 불변 JSON입니다. 음악 전용 별도 DB/점수 테이블 채택은 확정하지 않았습니다.
- 수령 [테마·장르 정의](../handoff/music/테마_장르_정의.md)는 장르에서 확정 mood를 자동 부여하지 않고 ON의 승인 mood 일치 100/0을 설명합니다. 최신 결정은 **확정 mood를 만들지 않는 조건을 유지하면서 ON의 가점만 자동 적합 점수로 교체**합니다. 수령 원문은 수정하지 않았고 변경된 가점은 제품 가이드 3.2~3.3절에 명시했습니다. 이 불일치가 필요한 B/PL 인계 범위는 청취 표본 검수와 기존 결과의 정책 버전 경계입니다.

## 기준 → 코드·저장 흐름

| 변경 | 코드와 전후 동작 |
|---|---|
| 사전 계산 | [policy.py](../../backend/recommendation/policy.py)의 `precompute_scores`가 곡별 5개 날씨 W와 9개 테마별 OFF 원조건 점수를 정확 유리수 `[분자,분모]`/NULL로 계산합니다. 이전에는 로컬 맑음 W만 사전 계산하고 다른 점수는 요청마다 계산했습니다. `weather_version`·`theme_version`을 값에 함께 기록합니다. |
| ON 선택 테마 | 같은 파일의 `score`가 승인 mood의 100/0 일치 대신 선택 테마의 계산 점수 최대값을 P_ON 테마 그룹으로 사용합니다. 빠르기·장르는 기존 필수 조건 통과 100점, W≥75와 S_ON=.75W+.25P_ON은 유지합니다. 정책 버전은 `WEATHER_CHOICE_20261016_V2`입니다. 미확인 계산값은 0점이며 승인 mood로 대체하지 않습니다. |
| OFF 요청 | 선택 테마만 있고 직접 장르·빠르기 입력이 없으면 저장 점수를 읽습니다. 직접 입력이 있으면 G/T 기준을 요청에 맞게 다시 계산합니다. OFF 점수식 자체와 장르 100%/80% 구성은 유지합니다. |
| 운영 카탈로그 발행 | [catalog.py](../../backend/music/catalog.py)의 `publish`가 검수된 RDB 곡을 `export_tracks`로 읽고 점수를 사전 계산해 `Catalog` JSON·SHA-256에 포함합니다. 기존 버전은 수정하지 않고 새 버전을 발행합니다. 등록·검수·발행 API 입력/응답·권한 계약은 변경하지 않았습니다. |
| 로컬 CSV 프리뷰 | [seed_csv_preview.py](../../backend/recommendation/management/commands/seed_csv_preview.py)가 모든 점수를 계산해 새 `spotify-preview-…-v3` 버전을 만듭니다. `is_test=true`, `local-preview:` 출처·미검수 상태는 유지합니다. |
| 작업자·결과 | [worker.py](../../backend/recommendation/worker.py)는 검증된 불변 카탈로그를 프로세스에서 재사용하고 요청 점수를 계산합니다. 결과 곡에는 당시 실제 W/P/S·원본/카탈로그 참조를 남기되 14개 사전 점수 전체를 결과·피드백 이벤트에 중복 복사하지 않습니다. 캐시가 없는 기존 버전은 동일 수식으로 계산합니다. |

현재 Django 기본 연결은 로컬에서 SQLite, 운영 설정에서 PostgreSQL입니다. 새 점수 전용 마이그레이션은 없고 기존 `Catalog.tracks` JSON에 값이 추가됩니다. 원본 해시 → 음악4개 테이블의 등록·검수 → `Catalog` 발행 → 추천 작업의 catalog FK 고정 → 작업자 조회·결과 스냅샷 순서입니다. 원본 적재 API의 S3 버전 보관 요구와 관리자 인증·멱등 처리는 유지합니다. API·큐·공통 outbox의 입력/응답 스키마는 바꾸지 않았습니다.

## 검증과 남은 연결

- `backend/manage.py test backend.recommendation backend.music backend.common --verbosity 1` — 로컬 SQLite 시험 DB에서 76개 통과. 사전 계산 점수와 요청 시 계산의 정확 일치, 5개 날씨/9개 테마, mood·main_inst 미생성, 혼합 날씨를 포함합니다.
- 실제 CSV 읽기 전용 전곡 계산 — 89,740 고유곡, 오류 1행, 충돌 ID 0개, 변환 약 1.92초·14개 점수 계산 약 40.37초(이 PC 단일 실행). 모든 CSV 곡을 포함한 계산 수이며 READY/추천 적격 수가 아닙니다.
- `seed_csv_preview` 실행 — 로컬 DB에 `spotify-preview-335e5ee0a07a-v3` 생성, 89,740곡·맑음 W 합격 49,396곡, `unreviewed_preview=true`. `verified_catalog`로 해시·고유 ID를 확인하고 최신 프리뷰의 첫 곡에서 날씨5·테마9 점수와 mood/main_inst NULL을 확인했습니다. 기존 v2 카탈로그·과거 결과는 보존했습니다.
- 남은 항목: 운영 PostgreSQL 연결/대용량 JSON 발행·조회·백업·S3 원본 보관, 검수 곡 READY 발행, 첫 요청/동시 요청의 P95 2.5초 화면 측정, 실제 청취 적합성 표본 검증, B/INF의 DB 물리 배치와 카탈로그 전환/복구 확인. 로컬 프리뷰 통과를 운영 연결 완료로 표시하지 않습니다.
- 이 PC의 현재 셸에는 PGHOST/PGDATABASE/PGUSER/PGPASSWORD·MUSIC_DATABASE_URL·MUSIC_S3_BUCKET·MUSIC_RAW_DIRECTORY가 설정되어 있지 않았고 로컬 5432 리스너도 확인되지 않았습니다. 따라서 실제 PostgreSQL 쓰기나 운영 카탈로그 발행은 수행하지 않았습니다.
- 정책 버전 V1인 기존 Family/대기 작업은 V2 작업자에서 자동 재해석하지 않습니다. 기존 결과는 보존하며 새 정책 선곡은 새 결과 계열로 요청해야 합니다. 배포 전 기존 대기 작업 처리·사용자 안내를 B/C가 확인해야 합니다.

## 2026-10-16 후속 — PostgreSQL 이전용 배치 적재

- 사용자 지시에 따라 [운영 절차](../runbook/C_음악_CSV_PostgreSQL_적재와_재시작.md)를 작성했습니다. 수령 CSV·인계 원문은 수정하지 않았고 음악 기본4개 테이블에 새 추천 속성을 추가하지 않았습니다.
- [MusicImportRun](../../backend/music/models.py)과 `music.0003_musicimportrun`은 원본 SHA-256별 처리 곡 수·마지막 ID·완료 여부를 저장하는 운영 체크포인트입니다. [관리 명령](../../backend/music/management/commands/import_music_catalog_source.py)은 기본 읽기 전용 검산, `--apply` 시 원본 해시·로컬 보관·S3 version 확인 후 배치(기본 500곡)별 트랜잭션으로 곡/앨범/장르·검수 draft·원본 연결을 적재합니다. 오류/충돌 행은 `--allow-quarantined-rows` 명시 전까지 적용하지 않습니다. 검수 승인·READY 발행은 기존 관리자 API에 남깁니다. `music_import_run`은 기본 음악4개 외 운영 상태이며 사용자 API 응답을 바꾸지 않습니다.
- 배치 실패 시 마지막 성공 배치까지 커밋되고 동일 SHA/스키마/변환 코드로 재실행하면 마지막 ID 다음부터 처리합니다. 정규화 코드 배포가 바뀐 중간 실행은 계속하지 말고 결과 차이를 대조한 뒤 새 적재 계획을 정해야 합니다. 기존 확정 instrumental 검수는 각 행을 잠근 뒤 재확인해 보존합니다. 운영 명령 실행 권한은 DB/S3 접근 가능한 서버 운영 환경으로 제한합니다.
- 실제 CSV의 읽기 전용 명령은 89,740곡·오류 행 65,902 한 건·충돌 0을 반환했고 DB는 변경하지 않았습니다. 소규모 `TransactionTestCase`에서 2곡 커밋 후 다음 배치 실패/재시작·미검수/미발행을 확인했습니다. 백엔드 78개 테스트 통과, `makemigrations --check --dry-run`은 변경 없음입니다. 운영 PG/S3·대용량 쓰기 시간·다중 실행 경쟁은 여전히 미검증입니다.
