# ad-server/backend/domains/ads/management/commands/__init__.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- 역할: Django가 광고 관리 명령을 검색할 패키지를 구성합니다.
- 정의된 클래스·함수: 없음.

`apply_ads_schema`, `apply_ads_public_schema`, `apply_ads_policy_schema`, `check_ads_database`, `run_ads_dev`, `refresh_ads_policy`, `check_ads_logs`, `check_ads_runtime`, `run_ads_workers`, `run_ads_sandbox` 명령을 제공합니다. 광고 로그는 MongoDB에 저장하며 외부 로그 전달 명령은 제거했습니다.
