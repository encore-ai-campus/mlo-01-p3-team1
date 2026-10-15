# backend/domains/ads/management/commands/__init__.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- 역할: Django가 광고 관리 명령을 검색할 패키지를 구성합니다.
- 정의된 클래스·함수: 없음.

`apply_ads_schema`, `check_ads_database`, `run_ads_dev`, `relay_ads_logs` 명령을 제공하는 모듈이 이 경로에 있습니다. 실제 공통 PostgreSQL sink 연결 전에는 로그 전달 명령이 차단됩니다.
