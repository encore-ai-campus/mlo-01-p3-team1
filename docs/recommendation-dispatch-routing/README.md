# 추천 분산 처리 코드 라우팅

- 작성일/수정일: 2026-10-19
- 담당: Codex / 추천 요청 분산 실행
- [정책·코드·검증 변경 라우팅](../development/추천_분산처리_변경_라우팅.md)
- [인프라 실행 인계](../runbook/추천_분산처리_인프라_인계.md)

독립 호스트의 PostgreSQL 선점·복구와 Gemini 공통 한도, 작업 종류별 프로세스를 연결합니다. AST 목록은 해당 파일의 함수/클래스를 기록하며 실제 운영 연결 완료를 뜻하지 않습니다.

| 코드 | AST·호출 라우팅 |
|---|---|
| `backend/recommendation/dispatch.py` | [선점·제한](./files/backend/recommendation/dispatch.py.md) |
| `backend/recommendation/management/commands/run_recommendations.py` | [워커 실행](./files/backend/recommendation/management/commands/run_recommendations.py.md) |
| `backend/recommendation/management/commands/check_recommendations.py` | [큐 조회](./files/backend/recommendation/management/commands/check_recommendations.py.md) |
| `backend/recommendation/migrations/0006_distributed_dispatch.py` | [마이그레이션](./files/backend/recommendation/migrations/0006_distributed_dispatch.py.md) |
| `backend/recommendation/tests/test_dispatch.py` | [분산 회귀 검사](./files/backend/recommendation/tests/test_dispatch.py.md) |
