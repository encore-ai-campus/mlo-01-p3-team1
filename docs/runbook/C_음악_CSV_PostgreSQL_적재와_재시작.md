# C 음악 CSV → PostgreSQL 적재·재시작

- 작성·수정일: 2026-10-16
- 상태: 코드와 로컬 시험 DB에서 명령 검증. 운영 PostgreSQL/S3 실행·부하/복구 확인은 미실행.
- 담당: C(입력·점수·카탈로그), B(관리/검수 API·공통 상태), INF(DB·원본 보관·백업/복구), PL(검수 수용)

## 1. 경계

원본 [spotify_dataset.csv](../handoff/music/spotify_dataset.csv)는 `track_id`별 정규화 후 음악 기본4개 테이블(`music_album`, `music_track`, `music_tag`, `track_tag`)로 들어갑니다. `music_import_run`은 대량 적재의 재시작 위치만 기록하는 운영 테이블입니다. 적재 시 곡 검수는 `draft`, 카탈로그는 미발행 상태입니다. 5개 날씨 W·9개 테마 적합 점수는 검수 뒤 [카탈로그 발행](../../backend/music/catalog.py)에서 불변 `Catalog.tracks`에 계산·저장합니다. 자동 점수는 확정 `mood`/`main_inst` 태그가 아닙니다.

이 명령은 서버 운영자가 해당 DB에 접근하는 환경에서 실행합니다. 관리자 HTTP 등록/검수 API의 인증을 우회해 공개 호출하는 기능이 아닙니다. 실제 DB 주소·비밀값을 파일이나 명령 인자에 기록하지 않습니다.

## 2. 운영 전제

1. `C_LOCAL_DEMO=0`, `INTEGRATION_ENABLED=1`, `DJANGO_SECRET_KEY`, PostgreSQL `PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD` 및 필요한 `PGSSLMODE/PGSSLROOTCERT`를 비공개 환경에서 설정합니다. 현재 코드는 음악4개 테이블·`Catalog`·공통 상태를 Django 기본 PostgreSQL 연결에 둡니다. 별도 음악 DB/스키마는 아직 연결되지 않았습니다.
2. `MUSIC_RAW_DIRECTORY`는 명령과 관리 API가 공유하는 절대 경로로 준비합니다. `MUSIC_S3_BUCKET`, `MUSIC_S3_REGION`, `MUSIC_S3_PREFIX`를 설정하고 버킷 versioning·권한·백업을 검증합니다. 운영 모드에서 원본 S3 보관이 실패하면 적재를 시작하지 않습니다.
3. DB 백업·공간·연결 수를 확인하고 `python backend/manage.py migrate --plan`을 검토한 뒤 `python backend/manage.py migrate`를 적용합니다. `music.0003_musicimportrun`이 체크포인트를 생성합니다. 실제 운영 DB 마이그레이션은 이 문서 작성 때 수행하지 않았습니다.
4. `Get-FileHash docs/handoff/music/spotify_dataset.csv -Algorithm SHA256`로 **현재 배포된 파일의 바이트 해시**를 확인합니다. 이 작업 폴더의 값은 `335e5ee0a07a3f30b20ca9860c87562c98082a032e0ecd90e8ca0a86d965fe58`이며 문서 수령 원본과 줄바꿈이 달라 수령 원본의 다른 해시를 그대로 명령에 넣지 않습니다.

## 3. 검산과 배치 적재

아래는 이 작업 폴더의 실제 해시 예시입니다. 다른 환경에서는 2절에서 계산한 값을 사용합니다.

```powershell
python backend/manage.py import_music_catalog_source docs/handoff/music/spotify_dataset.csv --schema spotify-raw20-v1 --expected-sha256 335e5ee0a07a3f30b20ca9860c87562c98082a032e0ecd90e8ca0a86d965fe58
```

기본은 **읽기 전용 검산**입니다. 현재 CSV는 114,000행에서 89,740곡으로 정규화되고 65,902행의 필수값 오류 1건을 격리합니다. 숫자는 운영 적격/승인곡 수가 아닙니다. 오류 원본 행과 원인, 예상 적재 수를 확인한 후 격리 허용 여부를 결정합니다. `--apply`만 주면 오류·충돌 ID가 하나라도 있을 때 중단합니다.

```powershell
python backend/manage.py import_music_catalog_source docs/handoff/music/spotify_dataset.csv --schema spotify-raw20-v1 --expected-sha256 335e5ee0a07a3f30b20ca9860c87562c98082a032e0ecd90e8ca0a86d965fe58 --batch-size 500 --allow-quarantined-rows --apply
```

`--allow-quarantined-rows`는 오류 행을 승인한다는 뜻이 아니라 **오류 행을 제외하고 나머지를 적재한다는 명시적 운영 선택**입니다. 이 명령은 원본의 실제 해시 검증 → 로컬 해시명 보관 → S3 version ID/크기/해시 확인 → `MusicSource` 생성 → 곡별 변환값/장르/원본 연결과 `draft` 검수를 배치별 트랜잭션으로 적재합니다. 한 배치가 실패하면 그 배치만 롤백됩니다. 같은 원본 해시·스키마·명령으로 다시 실행하면 `music_import_run.last_track_id` 다음 곡부터 이어집니다. 다른 원본 버전은 새 해시로 구분합니다. 기존 확정 `instrumental_review_value`는 일반 재적재에서 초기화하지 않습니다.

관리 HTTP 업로드는 현재 전체 파일을 한 요청에서 처리합니다. 이 대량 CSV에는 위 운영 명령을 쓰고, HTTP 경로를 운영 대량 적재로 쓰려면 별도의 시간 초과·부하 검증이 필요합니다.

## 4. 적재 후 검수·카탈로그 발행

1. `music_import_run.completed=true`, `processed_count=normalized_tracks`, `MusicSource`의 원본/S3 version, 오류 행과 `TrackOrigin`의 연결을 대조합니다. `Track` 전체 수는 기존 출처 곡이 있으면 이 파일의 고유곡 수와 같지 않을 수 있으므로 출처로 필터링합니다.
2. 관리자 음악 검수 화면/API에서 필요한 곡을 검토·승인합니다. CSV만으로 곡별 확정 `mood`·주 악기·무보컬 검수를 일괄 승인하지 않습니다. 등록과 승인·READY를 별도로 기록합니다.
3. 준비 현황의 승인/적격 규모와 176~184분 구성 가능성, 날씨 ON/OFF 표본을 확인한 뒤 관리자 `POST /api/admin/music/catalogs`로 **새** `version`, `source_ref=music-source:<sha256>`, `source_sha256`을 발행합니다. 발행 시 승인된 해당 출처 곡만 불러 5개 날씨/9개 테마 점수를 계산하고 카탈로그 해시를 저장합니다. 기존 카탈로그/결과를 수정하지 않습니다.
4. 작업자의 새 버전 해시·고유 ID, 캐시 메모리/첫 요청/동시 요청, 브라우저 [선곡표 받기]→목록 P95 목표 2.5초를 확인합니다. 실제 청취 적합성·장르 대표·시간/승인 조건도 검증합니다. 실패 시 새 요청의 카탈로그 선택을 중단하고 기존 정상 버전 및 결과를 보존합니다. 현재 구현은 READY 발행 시 최신 버전을 자동 선택하므로 운영 발행 전에 이 검증과 전환/롤백 절차를 B/C/INF가 함께 확인해야 합니다.

## 5. 이번 검증 범위

- `import_music_catalog_source`의 전체 CSV 읽기 전용 검산: 89,740곡, 오류 1행, 충돌 ID 0. 이 PC의 로컬 DB에서는 적용하지 않았습니다.
- 소규모 시험 DB에서 2곡 커밋 후 다음 배치 실패를 유도하고 재실행으로 3곡 완료를 확인했습니다. 미검수 `draft`와 카탈로그 미발행을 확인했습니다.
- 실제 PostgreSQL 접속·S3 업로드·89,740곡 DB 적재 시간/메모리·다중 실행 경쟁·복구·운영 추천은 미검증입니다. 환경 설정과 운영 자료가 준비되면 이 항목을 다시 실행해 결과를 기록합니다.
