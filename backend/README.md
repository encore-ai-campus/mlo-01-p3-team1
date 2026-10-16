# 추천 API와 서비스 조회 코드

- 작성일: 2026-10-16
- 수정일: 2026-10-16

| 위치 | 책임 |
|---|---|
| cafe/ | 추천 API 호스트의 Django 설정·URL |
| recommendation/ | 추천 요청·작업/결과·제외/승인·평가 |
| music/ | 음악 모델·CSV 등록 명령·카탈로그 발행·migration |
| weather/ | 지역/도로명 검색·저장된 최신 날씨 조회 함수 |

날씨 HTTP와 추천 bundle 어댑터는 연결 대기입니다. `backend.weather.queries.weather_for_region(identifier)`를 추천 `WEATHER_PROVIDER(region_id, as_of)`로 바로 지정할 수는 없습니다. 조회 의존성은 [날씨 requirements](../pipeline/weather/requirements.txt)를 확인합니다.

광고는 [ad-server/backend](../ad-server/backend/)의 독립 Django 실행 단위입니다. 루트 backend와 광고의 설정/인증/migration·의존성을 임의 혼합하지 않습니다. [환경 안내](../config/environments/README.md)에서 별도 환경·포트·프록시를 확인합니다.

현재 경로와 과거 인계의 경로 차이는 [통합 변경 라우팅](../docs/development/통합_폴더_정리_변경_라우팅.md)을 따릅니다.
