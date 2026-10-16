# 추천 API와 서비스 조회 코드

- 작성일: 2026-10-16
- 수정일: 2026-10-16

| 위치 | 책임 |
|---|---|
| cafe/ | 추천 API 호스트의 Django 설정·URL |
| recommendation/ | 추천 요청·작업/결과·제외/승인·평가 |
| music/ | 음악 모델·CSV 등록 명령·카탈로그 발행·migration |
| weather/ | 지역/도로명 검색·저장된 최신 날씨 조회 함수 |

날씨 HTTP는 `backend.weather.adapter.display`, 추천 bundle은 `backend.weather.adapter.obtain(region_id, as_of)`로 연결합니다. PostgreSQL 매핑 → ES 최신 자료·공통 특징을 읽고 조회 때 만료를 재검사합니다. 원문 `weather_for_region`을 추천 provider로 바로 지정하지 않습니다. `common/`은 guest·ADMIN·피드백/outbox·음악 관리·광고 인증 어댑터를 제공합니다. 실제 운영 저장소 연결은 설정 후 별도로 검증합니다.

광고는 [ad-server/backend](../ad-server/backend/)의 독립 Django 실행 단위입니다. 루트 backend와 광고의 설정/인증/migration·의존성을 임의 혼합하지 않습니다. [환경 안내](../config/environments/README.md)에서 별도 환경·포트·프록시를 확인합니다.

현재 경로와 과거 인계의 경로 차이는 [통합 변경 라우팅](../docs/development/통합_폴더_정리_변경_라우팅.md)을 따릅니다.

현재 API·설정·migration·실행과 시험/미검증 경계는 [서비스 통합 구현 라우팅](../docs/development/서비스_통합_구현_변경_라우팅.md)을 확인합니다. ASGI 앱 진입점은 `backend.cafe.asgi:application`입니다. 실행 서버/운영 서비스 설치나 배포를 이 파일만으로 완료 처리하지 않습니다.
