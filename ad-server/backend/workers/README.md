# 광고 로그 전달 작업자

`ads_log_relay.py`는 `ad_admin_changes.log_relay`와 `ad_events.log_relay`의 불변 payload를
설정된 공통 PostgreSQL sink로 동일 log_event_id/hash와 함께 전달합니다.
`relay_ads_logs`는 관리 변경 발생 순서, `relay_ads_event_logs`는 측정 처리 순서로 한 batch를 실행합니다.
로그 지연 시 PENDING을 유지하고 광고 판정·원응답·예상 토큰을 재계산하지 않습니다.
next_retry_at·attempt_count로 claim과 늦은 ACK를 제어합니다. 기본 30초는 작업자 기술 초기값이며,
광고 예산·집계 주기·노출 정책이 아닙니다. 실제 공통 sink는 연결 전이며 새로운 SQL 테이블은 만들지 않습니다.
sink의 durable commit 또는 기존 동일 payload 확인에 대한 True 응답 뒤에만 SENT로 바꿉니다.
MongoDB ACK가 실패하면 같은 ID로 재전달하므로 PostgreSQL sink에도 멱등 저장이 필요합니다.
