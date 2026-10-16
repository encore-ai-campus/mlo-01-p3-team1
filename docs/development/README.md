# 개발 문서와 현재 코드 경로

- 작성일: 2026-10-16
- 수정일: 2026-10-16

현재 파일을 수정할 때는 [통합 폴더 변경 라우팅](./통합_폴더_정리_변경_라우팅.md)의 현재 경로·이동 매핑을 먼저 확인합니다. 아래 기존 인계는 원문/이력이며 예전 경로를 담고 있을 수 있습니다. 원문을 수정하지 않고 변환표로 연결합니다.

| 작업 | 기준/인계 | 현재 코드 |
|---|---|---|
| 제품/담당 | [AGENTS](../../AGENTS.md), [구현 설계](../product/카페_음악_서비스_구현_설계도.md) | [루트 폴더 안내](../../README.md) |
| 추천·음악 | [C 작업 라우팅](./C_코드초안_정리기준과_작업라우팅.md), [C 실행 인계](../runbook/C_구현과_연결_인계.md) | backend/recommendation, backend/music, pipeline/music, frontend/src/features/recommendation |
| 날씨 | [수령·차이 라우팅](./날씨_코드_수령과_연결_라우팅.md), [제공 원문](../handoff/weather/received/20261014/) | backend/weather, pipeline/weather, frontend/src/features/region-weather |
| 광고 | [광고 코드 색인](../backend-routing/README.md), [광고 실행 인계](../runbook/광고_서버_개발_준비.md) | ad-server/backend, frontend/src/features/ad-banners |
| 환경/실행 | [서비스별 환경 위치](../../config/environments/README.md), [통합 변경/검증](./통합_폴더_정리_변경_라우팅.md) | frontend/vite.config.ts, 각 실행 단위의 의존성/설정 |
| develop 문서 전체 | [develop 문서 목록](./develop_문서_목록.md) | 기준 커밋의 원본 Markdown과 계약/고정 자료 JSON |

루트 frontend는 공개 앱이며 광고의 정식 관리자 React 화면 연결은 대기입니다. ad-server의 presentation/templates는 기존 로컬 sandbox 도구입니다. 경로 정리를 화면/인증/DB 구현 완료로 해석하지 않습니다.
