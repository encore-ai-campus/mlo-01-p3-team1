# 데이터 파이프라인

- 작성일: 2026-10-16
- 수정일: 2026-10-16

- `music/`: 음악 CSV 입력·정제. 기존 추천/음악 앱과 연결합니다.
- `weather/`: 날씨 수집·정규화·MongoDB 최신 저장·관리자 ES 발행·Spark 패키징입니다. 기존 `weather/pipeline/`의 중복 계층을 없애 이 위치에 모았습니다.

서비스의 지역·도로명·최신 날씨 조회 함수는 [backend/weather](../backend/weather/)입니다. Kafka/Spark 작업을 사용자 요청마다 실행하지 않습니다. 저장 정책/실제 실행·인증/소유와 문서 간 차이는 [통합 변경 라우팅](../docs/development/통합_폴더_정리_변경_라우팅.md)에 남깁니다.

날씨 명령은 저장소 루트에서 `python -m pipeline.weather.run_collector`, `python -m pipeline.weather.submit_spark`, `python -m pipeline.weather.publish_admin`입니다. 실제 수집/저장 명령이므로 외부 환경 준비가 필요합니다. [환경 안내](../config/environments/README.md)에 의존성과 .env 위치를 정리했습니다. `pipeline/weather/.env`는 자동 로드되지 않으며 실행 프로세스에 환경변수로 전달해야 합니다.
