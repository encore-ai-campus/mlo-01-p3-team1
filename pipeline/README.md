# 데이터 파이프라인

- 작성일: 2026-10-16
- 수정일: 2026-10-16

- `music/`: 음악 CSV 입력·정제. 기존 추천/음악 앱과 연결합니다.
- `weather/`: 날씨 수집·정규화·ES 최신 자료/공통 특징 저장·Spark 패키징입니다. 기존 `weather/pipeline/`의 중복 계층을 없애 이 위치에 모았습니다.

서비스의 지역·도로명·최신 날씨 조회 함수는 [backend/weather](../backend/weather/)입니다. Kafka/Spark 작업을 사용자 요청마다 실행하지 않습니다. 최신 저장 경계·실제 실행·인증/소유와 문서 간 차이는 [통합 변경 라우팅](../docs/development/서비스_통합_구현_변경_라우팅.md)에 남깁니다.

날씨 명령은 저장소 루트에서 `python -m pipeline.weather.run_collector`, `python -m pipeline.weather.submit_spark`입니다. 실제 수집/저장 명령이므로 외부 환경 준비가 필요합니다. [환경 안내](../config/environments/README.md)에 의존성과 .env 위치를 정리했습니다. 수집기의 KMA_API_KEY는 프로세스 환경변수를 우선하고, 없으면 `pipeline/weather/.env`에서 읽습니다. Kafka·DB·Spark 등 나머지 설정은 실행 프로세스에 환경변수로 전달해야 합니다. [키 연결 라우팅](../docs/development/날씨_환경설정_변경_라우팅.md)을 확인합니다.

2026-10-16 사용자가 다시 지정한 날씨 문서 6개를 구현 기준으로 채택합니다. PostgreSQL은 지역/도로명 매핑, ES는 최신 날씨·공통 특징, MongoDB는 광고용입니다. 날씨 원천 응답 파일은 보관하지 않습니다. `mongo_current`, `prepare_mongo`, `publish_admin`은 이전 경로로 남아 있으며 현재 수집·조회 실행 경로에서 사용하지 않습니다. 전용 ES 인덱스 규격은 `python -m pipeline.weather.prepare_es`로 출력하고, 인프라 준비 후에만 `--apply`를 사용합니다.
