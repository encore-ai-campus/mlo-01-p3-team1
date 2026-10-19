# backend/recommendation/youtube_registry.py 라우팅

## 2026-10-19 수집 URL 공개 연결 — 현행

- 담당: Codex root / U-01·M-06·Q-02 연결 수정
- 브랜치/기준: feature/youtube-url-connection / develop a7dfafb
- 작성/수정: 2026-10-19. 기존 수령 원문은 보존합니다. 아래 앞 단계 서술은 당시 구현 이력이며 이번 절이 현행입니다.
- 계약·전체 검증: [수집 URL 연결 변경 라우팅](../../../../development/수집_URL_공개화면_연결_변경_라우팅.md).

track_registries는 요청한 곡 ID만 중복 제거 후 500개 단위·한 연결에서 조회합니다. 로컬 SQLite와 운영 Django 공유 DB 어댑터를 그대로 사용하며 미등록 곡은 revision=0·빈 mappings입니다. SELECT 조건은 매개변수로 바인딩합니다. 새 함수는 검수·감사·곡 revision을 변경하지 않습니다.

### AST 시그니처 — 검사 결과

```python
registry_path()
access_code_path()
initialize_access_code(rotate=False)
validate_access_code(value)
normalize_video_url(value)
_now()
_connection(write=False)
_mapping(row)
read_registry()
track_registry(track_id)
track_registries(track_ids)
playback_candidates(track_id, excluded_video_ids=())
verified_candidates(track_id, excluded_video_ids=())
_revision(connection, track_id, expected)
_audit(connection, track_id, video_id, action, revision)
_note(value)
register_mappings(rows, source='OPERATOR_URL')
parse_mapping_csv(text)
verify_mapping(track, video_id, expected_revision, identity_confirmed, playback_observed, duration_seconds, note='')
verify_native_mapping(track, video_id, expected_revision, identity_confirmed, playback_observed, duration_seconds, note='', duration_difference_confirmed=False)
block_mapping(track_id, video_id, expected_revision, reason)
block_native_mapping(track_id, video_id, expected_revision, reason)
seed_legacy_mappings(tracks)
seed_native_reviewed_mappings(tracks)
```

## 앞 단계 기록

- 작성일/수정일: 2026-10-16
- 담당: API 키 없는 YouTube 등록·검수 백엔드 / 통합팀
- 기준 브랜치/커밋: feature/ad-logic / f22f974
- 소스: `backend/recommendation/youtube_registry.py`
- 통합 근거: docs/development/YouTube_키없는_등록과_검수_변경_라우팅.md

## 기준 → 저장 → 소비

최신 사용자 결정인 API 키 없는 등록·검수와 기존 음악 카탈로그/선곡표 불변 원칙을 구현합니다. Django 모델·음악 RDB 4개 테이블을 변경하지 않으며 로컬 보조 SQLite에 track_revision, mapping, review_audit를 저장합니다. 기본 경로는 Git 제외 `.local-preview-logs/youtube-mappings.sqlite3`이며 YOUTUBE_REGISTRY_PATH로 시험용 파일을 주입할 수 있습니다.

| 함수 묶음 | 입력·순서·소비 |
|---|---|
| registry_path / access_code_path / initialize_access_code / validate_access_code | BASE_DIR 아래 Git 제외 파일, 초기화/회전, 헤더와 상수시간 비교. YOUTUBE_REVIEW_ACCESS_FILE 경로만 노출하며 비밀값을 출력하지 않습니다. |
| normalize_video_url | 11자리 ID 또는 허용 HTTPS YouTube URL에서 ID만 추출합니다. 외부 호출·리디렉트·다운로드는 하지 않습니다. credential/기타 호스트/비표준 포트/control 문자는 거절합니다. |
| _connection / _revision / _audit | 별도 SQLite 연결·BEGIN IMMEDIATE·곡별 revision 비교·감사 이벤트·원자 commit/rollback을 담당합니다. 기술 장애는 REGISTRY_UNAVAILABLE/503입니다. |
| register_mappings / parse_mapping_csv | URL·UTF-8 BOM CSV를 검증한 뒤 CANDIDATE로 등록합니다. 최대 500행·1MiB·곡별 10개 대안. CSV는 track_id,video_url,expected_revision 및 선택 note입니다. 같은 곡의 다른 영상은 허용하고 같은 곡·영상 중복, 서로 다른 예상 revision, stale 수정은 전체 거부합니다. 수식 문자열은 실행하지 않습니다. |
| verify_mapping / block_mapping | 원곡 확인과 운영자 브라우저 PLAYING 보고·양수 길이를 모두 요구합니다. 원본 길이와 min(60초,max(12초,12%)) 이내일 때 VERIFIED가 되며, 명시 사유의 BLOCKED는 공개 후보에서 제외됩니다. PLAYING 보고는 YouTube의 서명 보증이나 완청이 아닙니다. |
| read_registry / track_registry / playback_candidates / verified_candidates | 검수 목록과 곡별 revision·대안·상태를 공급합니다. helper 후보 source는 LOCAL_REGISTRY이고 공개 resolver가 MAPPING_REGISTRY·곡명을 채웁니다. 공개 재생은 검수된 VERIFIED만 소비합니다. |
| seed_legacy_mappings | 기존 snapshot의 VERIFIED 표기와 무관하게 LEGACY_REVIEW_PENDING/CANDIDATE만 추가합니다. 기존 검수/차단·원문·카탈로그를 덮어쓰지 않습니다. |

등록·검수 API는 다음 짝 문서를, 실제 보조 iframe 후보·실패 정책은 youtube_playback.py 짝 문서를 확인합니다. 후보 86,485곡의 추천 점수·날씨 풀과 분리합니다. 운영 공유 저장소/ADMIN 어댑터는 미연결입니다.

## 외부 YouTube 기본·iframe 보조의 독립 검수

최신 사용자 선택으로 기본은 외부 YouTube 재생이며 iframe은 보조입니다. mapping의 기존 status/identity_confirmed/playback_observed/duration_seconds/observed_at/reason은 iframe 판정으로 유지합니다. 별도 native_verified/native_duration_seconds/native_observed_at/native_source/native_reason을 additive ALTER로 추가하며 이전 로컬 데이터를 보존합니다. 새 URL·CSV 등록은 두 재생 방식 모두 미검수입니다.

verify_native_mapping은 운영자가 외부 탭 실제 재생과 원곡 정보를 수동 확인한 보고를 저장합니다. iframe 상태를 바꾸지 않으며 source=OPERATOR_NATIVE_REPORTED_PLAYING입니다. 표준 길이 허용은 iframe과 같고, 초과 시에는 duration_difference_confirmed=true·비어 있지 않은 note·절대 차이 60초 이내를 모두 갖춘 명시 예외만 허용합니다. 이 경우 감사 action=VERIFY_NATIVE_DURATION_DIFFERENCE_ACK로 남깁니다. 예를 들어 공식 MV의 확인된 인트로로 길어진 영상판을 허용할 수 있으나 원본 duration·추천 176~184분 성공 판정은 바꾸지 않습니다. iframe 검수와 legacy 자동 seed에는 이 예외를 적용하지 않습니다.

block_native_mapping은 native_verified=false/native_source=OPERATOR_NATIVE_BLOCK/native_reason을 저장하며 iframe 판정은 유지합니다. 명시 재승인은 native_reason을 비우고 같은 곡 revision을 증가시킵니다. iframe 차단은 별도 block_mapping이며 외부 승인 상태를 자동 철회하지 않습니다.

seed_native_reviewed_mappings는 명시 CLI 요청에서만 기존 1:1 원곡·아티스트·앨범·원본 길이·영상 ID·날짜·검수자·비고·버전·PRIMARY_METADATA_AND_NATIVE_QUEUE_INCLUSION 근거와 길이를 대조하여 native만 승인합니다. source=LEGACY_NATIVE_METADATA_REVIEW와 당시 확인 시각을 보존하며 전곡 PLAYING·완청을 주장하지 않습니다. 이미 외부 철회한 OPERATOR_NATIVE_BLOCK은 다시 seed해도 복구하지 않습니다. 실제 공개 외부 큐는 youtube_queue_api.native_queue가 native_verified만 소비합니다.

## 검증·인계

본 모듈의 격리 시험 16건과 검수 API 시험 10건이 2026-10-16 통합 백엔드 136건 실행에서 통과했습니다. 마지막 CSV 독립 검토를 반영해 DictReader strict=True를 사용하고 fieldnames 파싱 오류도 CSV_HEADERS_INVALID로 처리합니다. 시험 저장소는 workspace 내 임시 폴더이며 운영/실제 매핑과 분리합니다. 실제 47곡 재검수·브라우저 관측 범위는 통합 라우팅과 수용 기록을 따릅니다.

## AST 시그니처

검사기 `.local-preview-logs/keyless-routing-audit.json`의 python_files[].symbols를 그대로 기록합니다.

```python
registry_path()
access_code_path()
initialize_access_code(rotate=False)
validate_access_code(value)
normalize_video_url(value)
_now()
_connection(write=False)
_mapping(row)
read_registry()
track_registry(track_id)
playback_candidates(track_id, excluded_video_ids=())
verified_candidates(track_id, excluded_video_ids=())
_revision(connection, track_id, expected)
_audit(connection, track_id, video_id, action, revision)
_note(value)
register_mappings(rows, source='OPERATOR_URL')
parse_mapping_csv(text)
verify_mapping(track, video_id, expected_revision, identity_confirmed, playback_observed, duration_seconds, note='')
block_mapping(track_id, video_id, expected_revision, reason)
seed_legacy_mappings(tracks)
verify_native_mapping(track, video_id, expected_revision, identity_confirmed, playback_observed, duration_seconds, note='', duration_difference_confirmed=False)
block_native_mapping(track_id, video_id, expected_revision, reason)
seed_native_reviewed_mappings(tracks)
```
