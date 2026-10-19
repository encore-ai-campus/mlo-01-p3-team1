# 광고 로그 — MongoDB 독립 저장 계약

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- 사용자 결정: 광고는 PostgreSQL 로그 연결과 공통 로그 테이블 규격을 사용하지 않고 MongoDB에서 관리합니다.
- 적용: `feature/ad-logic`의 광고 관리·측정·소진 로그. 공통 사용자 인증과 음악·피드백 저장 계약은 별도입니다.

## 1. 저장 위치

| 자료 | MongoDB 컬렉션 | 저장 시점 |
|---|---|---|
| 광고 변경·이미지 업로드 감사·멱등 원응답 | `ad_admin_changes.log_record` | 관리 변경과 같은 트랜잭션 |
| 최초 노출/클릭 판정·중복/억제·처리 근거 | `ad_events.log_record` | claim·판정·인정 원장과 같은 트랜잭션 |
| 최초 예산 소진 확인 근거 | `ad_budget_states.log_record` | cutoff·광고 기술 상태·통계와 같은 트랜잭션 |

기존 관리3+공개5+정책2, 총10컬렉션을 유지합니다. 로그 전송용 컬렉션·공통 SQL 테이블·광고용 사용자 테이블은 추가하지 않습니다. 로그 저장에 실패하면 업무 변경도 롤백하며 성공 응답을 만들지 않습니다. 동일 멱등키/event_id 재전송은 최초 응답과 로그를 보존합니다. 소진 로그는 후속 검증에서 당시 합계·cutoff·payload를 바꾸지 않습니다.

## 2. 광고 전용 로그 형식

| 필드 | 타입·의미 |
|---|---|
| `log_schema_version` | `ads-mongo-log-20261015.1` |
| `log_event_id` | 관리 변경/event/최초 소진에서 정한 안정적인 식별자 |
| `payload` | 해당 광고 업무의 당시 사실·버전·시각·처리 결과·필요한 외부 ID 참조 |
| `payload_hash` | 정규 JSON의 SHA-256. 기존 코드의 정규화 규칙 적용 |
| `stored_at` | 같은 MongoDB 트랜잭션에서 사용하는 UTC BSON Date. 원격 전송 완료 시각이 아님 |

공통 `FeedbackEventEnvelope`나 PostgreSQL 로그 테이블에 맞춘 필수 컬럼을 요구하지 않습니다. 새 payload에는 `source_domain=ADS`를 넣지 않습니다. 관리·측정·소진은 각 도메인의 필요한 필드를 보존하며 하나의 공통 테이블로 평탄화하지 않습니다. 원본 이미지·비밀번호·쿠키·delivery proof·접속 URI·서명키는 로그에 넣지 않습니다.

새 로그에 PENDING/SENT·전송 시도·재시도/ACK 필드는 없습니다. MongoDB 커밋 확인이 저장 성공의 기준입니다. MongoDB 장애·응답 유실은 기존 트랜잭션 재시도와 동일 ID 조회로 해결합니다.

## 3. 기존 자료와 스키마 적용

기존 `log_relay`의 payload/hash·PENDING/SENT·시도 이력은 과거 자료로 보존합니다. 외부 전달을 다시 시도하거나 PENDING을 SENT로 바꾸지 않습니다. 새 검증기는 이전 스키마 버전과 기존 필드를 허용하고, 새 쓰기는 `log_record`를 사용합니다. 기존 소진 로그가 있으면 예산 재검증에도 원본 그대로 유지하며 새 최초 소진 로그를 만들지 않습니다.

manifest 버전은 관리 `phase3-ads-data-20261015.4`, 공개 `phase3-ads-public-20261015.2`, 정책 `phase3-ads-policy-20261015.2`입니다. 과거 문서/스냅샷 버전과 광고 단가·운영 정책 버전은 소급 변경하지 않습니다. 기존 relay 인덱스는 자동 삭제하지 않으며 새 설치에는 만들지 않습니다. 새 조회 인덱스는 `mongo_log_created`입니다.

기존 DB는 쓰기 전에 manifest 3개의 validator/인덱스를 적용해야 합니다. `check_ads_runtime --database`로 불일치를 확인하고, 로컬 `_dev`에서만 기존 `apply_ads_schema`·`apply_ads_public_schema`·`apply_ads_policy_schema --apply` 절차를 따릅니다. 공유/운영 DB 변경과 대량 데이터 변환·삭제는 이번 구현에서 실행하지 않습니다. 로컬 sandbox는 시작 시 스키마를 준비합니다.

## 4. 실행과 조회

`ad-server/backend`에서 실행합니다.

```powershell
.\.venv\Scripts\python.exe manage.py check_ads_logs --limit 20
.\.venv\Scripts\python.exe manage.py check_ads_runtime --database
.\.venv\Scripts\python.exe manage.py run_ads_workers --watch
```

`check_ads_logs`는 환경별 신규 저장/이전 기록/필수 로그 누락 건수와 컬렉션별 최대20문서의 payload/hash를 검사합니다. `--limit`은1~100이며 전수 무결성 검사라는 의미는 아닙니다. `stored`, `legacy_preserved`, `missing_required`, `sample_checked`, `sample_invalid`, `sample_document_limit`를 반환하며 payload나 인증 자료를 출력하지 않습니다. 읽기 여러 번의 관측값이므로 동시 쓰기 중 하나의 원자 스냅샷 통계는 아닙니다. 누락·표본 오류는 실패로 알리며 자동 수정하지 않습니다.

`run_ads_workers`는5분 예산 검증·통계만 실행합니다. 실패 후 다음 주기 재시도·안전한 상태 출력·Ctrl+C 종료를 유지합니다. 별도 로그 전달 작업은 필요하지 않습니다. `ADS_LOG_SINK` 설정과 `relay_ads_logs`·`relay_ads_event_logs`·`relay_ads_budget_logs` 명령은 제거했습니다. 이전 `.env`에 남은 값은 읽거나 실행하지 않습니다.

공통 ADMIN/guest는 기존 외부 인증 어댑터를 통해 확인합니다. 사용자 DB·인증 세션을 광고 MongoDB로 복제하지 않습니다. 이 어댑터의 실연결 검증은 여전히 남아 있습니다.

## 5. 보관과 남은 검증

원본 측정/배달90일·관리 감사/원장/집계365일의 기존 기산점과 참조 보호를 유지합니다. 로그는 소속 문서와 함께 보존합니다. 최초 소진 로그·일반 운영 진단/HTTP 로그·이미지/백업의 세부 보관과 자동 정리 정책은 별도이며 임의 TTL·삭제 작업을 추가하지 않습니다. 광고 로그를 저장하는 PostgreSQL 경로는 만들지 않습니다.

이번 변경은 업무 로그의 MongoDB 저장입니다. 모든 HTTP 요청/서버 예외를 새 컬렉션으로 자동 수집하는 기능은 구현하지 않습니다. 운영 환경의 TLS/권한·백업/복구·상시 실행·정식 화면/공유 인증 검증은 [남은 작업](./광고_남은_작업과_연결_계획.md), 실제 테스트 결과는 [검증 기록](../../acceptance/광고_개발_준비_검증.md)을 따릅니다.
