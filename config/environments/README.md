# 로컬 환경 설정 위치

- 작성일: 2026-10-16
- 수정일: 2026-10-19

이 폴더는 실행 환경의 안내 진입점입니다. 서비스별 의존성·비밀 설정은 해당 실행 단위에서 관리합니다. 추천 Django와 광고 Django는 버전이 다르므로 가상환경과 잠금 파일을 합치지 않습니다.

| 실행 단위 | 코드/의존성 | 설정 파일·적용 방식 | 로컬 포트 |
|---|---|---|---|
| 추천 API·음악·추천 작업자 | `backend/requirements.lock`, 기존 루트 `.venv` | [예시](../../backend/.env.example)의 지원 이름을 `backend/.env`에서 자동 로드. 프로세스 환경 우선 | API 8001 |
| 광고 API·광고 작업자 | `ad-server/backend/pyproject.toml`·`uv.lock`, 해당 폴더의 `.venv` | [예시](../../ad-server/backend/.env.example)를 `ad-server/backend/.env`로 배치, 광고 settings가 로드 | 기본 개발 API 8000 |
| 날씨 수집·Spark·ES 최신 저장 | [requirements](../../pipeline/weather/requirements.txt), [Spark 추가 의존성](../../pipeline/weather/requirements-spark.txt), `pipeline/weather/.venv` 권장 | [예시](../../pipeline/weather/.env.example)의 지원 이름을 Collector/Spark/준비 명령에서 자동 로드. 프로세스 환경 우선 | HTTP 서버 없음 |
| 공개 React | `frontend/package.json`·`pnpm-lock.yaml` | [예시](../../frontend/.env.example)를 `frontend/.env.local`로 복사, Vite가 로드 | 5173 |

날씨 `.env`의 새 위치는 `C:/Users/Playdata/Documents/ChatGPT/3th/pipeline/weather/.env`입니다. 실제 키·비밀번호·DSN은 Git이나 문서에 기록하지 않습니다. 설정 이름·DB·컬렉션·권한은 각 예시와 INF 계약을 따릅니다.

Vite는 광고 `/api/ads`, `/api/ad-events`, `/api/ad-deliveries/`, `/api/admin/ads`, `/api/admin/ad-assets`를 광고 API로 보내고, 나머지 `/api`는 추천/공통 호스트로 보냅니다. 두 목적지는 `VITE_ADS_API_TARGET`과 `VITE_RECOMMENDATION_API_TARGET`으로 바꿀 수 있습니다. 경로를 재작성하지 않습니다. 공유 ADMIN·guest·지역 API·날씨 추천 어댑터의 코드를 연결했습니다. 실제 PostgreSQL/ES/MongoDB 및 호스트 간 인증 통합은 환경 설정 후 검증해야 합니다.

광고 sandbox는 정식 광고 API와 다른 개발 전용 실행 모드입니다. 기존 안내의 sandbox 8001은 단독 확인용이며 추천 API와 동시에 같은 포트로 실행하지 않습니다. 이 문서는 AWS 배치·공유 인증·실제 DB 접속 완료를 뜻하지 않습니다.

[통합 폴더 변경 라우팅](../../docs/development/통합_폴더_정리_변경_라우팅.md)에서 경로 변환·실행 명령·검증 결과를 확인합니다.

기상청 키의 초기 연결 이력은 [날씨 환경설정 변경 라우팅](../../docs/development/날씨_환경설정_변경_라우팅.md)을 확인합니다. 현재는 예시에 있는 서비스별 설정 이름을 추가로 읽으며 파일 실행·변수 치환은 하지 않습니다.

설정만으로 접속 대상을 바꾸는 현재 진입점은 [설정 기반 서비스 전환](../../docs/runbook/설정_기반_서비스_전환.md)입니다. 빈 저장소의 준비와 데이터 검수·실제 연결 검증은 구분합니다.

통합 호스트의 새 설정·실행 순서와 검증 경계는 [서비스 통합 라우팅](../../docs/development/서비스_통합_구현_변경_라우팅.md)을 확인합니다. 날씨에 MongoDB 설정을 전달하지 않습니다.

추천 API/작업자의 두 Control 배치·종류별 큐·전역 호출 제한·systemd 예시는 [추천 분산 실행 설정](./recommendation/README.md)과 [인프라 인계](../../docs/runbook/추천_분산처리_인프라_인계.md)를 확인합니다. 실제 운영 적용은 별도입니다.
