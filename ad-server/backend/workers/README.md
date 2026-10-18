# 광고 MongoDB 작업과 점검

- 수정일: 2026-10-16

광고 로그는 업무 문서의 `log_record`에 같은 MongoDB 트랜잭션으로 저장합니다.
외부 전달 작업·PostgreSQL 로그 테이블·ADS_LOG_SINK는 사용하지 않습니다.
기존 `log_relay`는 과거 자료로 보존하며 재전달하거나 SENT로 변경하지 않습니다.

- `ads_jobs.py` / `run_ads_workers --watch`: 예산 검증·통계를300초마다 실행합니다. 실패 후 다음 주기 재시도, 상태 출력과 Ctrl+C 종료를 지원합니다.
- `ads_logs.py` / `check_ads_logs --limit 20`: 환경별 신규/기존/누락 건수와 제한 표본의 hash를 읽기 점검합니다. 업무·로그를 변경하지 않습니다.
- `ads_runtime_check.py` / `check_ads_runtime --database`: 설정·기존10컬렉션 validator/인덱스·로그를 확인합니다. 자동 보정과 공유 인증 성공 판정은 하지 않습니다.
- `ads_retention.py` / `check_ads_retention --limit 100`: 확정된90/365일 기산점·기간 도래·참조를 제한 표본으로 읽기 점검합니다. 삭제/TTL 모드는 없습니다.

2026-10-16 watch에 시작 상태 즉시 출력·SIGTERM/키보드 종료와 핸들러 복원을 추가했습니다.
실제 검증과 남은 운영 인계는 [보관 점검·배치 종료](../../../docs/runbook/광고_보관_점검과_배치_종료.md)를 따릅니다.

구조·호환·스키마 적용은 [광고 로그 저장 계약](../../../docs/development/ads/MongoDB_광고_로그_저장_계약.md),
후속 연결은 [남은 작업](../../../docs/development/ads/광고_남은_작업과_연결_계획.md)을 따릅니다.
