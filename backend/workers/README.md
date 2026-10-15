# 광고 로그 전달 작업자

`ads_log_relay.py`는 `ad_admin_changes.log_relay`의 불변 payload를 설정된 공통 PostgreSQL sink로
동일 log_event_id로 전달합니다. 로그 지연 시 PENDING을 유지하고 광고 토큰을 재계산하지 않습니다.
next_retry_at·attempt_count로 claim과 늦은 ACK를 제어합니다. 기본 30초는 작업자 기술 초기값이며,
광고 예산·집계 주기·노출 정책이 아닙니다. 실제 공통 sink는 연결 전이며 새로운 SQL 테이블은 만들지 않습니다.
