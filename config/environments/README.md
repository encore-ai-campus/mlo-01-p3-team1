# 로컬 환경 설정 위치

- 작성일: 2026-10-16
- 수정일: 2026-10-16

이 폴더는 실행 환경의 안내 진입점입니다. 서비스별 의존성·비밀 설정은 해당 실행 단위에서 관리합니다. 추천 Django와 광고 Django는 버전이 다르므로 가상환경과 잠금 파일을 합치지 않습니다.

| 실행 단위 | 코드/의존성 | 설정 파일·적용 방식 | 로컬 포트 |
|---|---|---|---|
| 추천 API·음악·추천 작업자 | `backend/requirements.lock`, 기존 루트 `.venv` | [예시](../../backend/.env.example). 프로세스 환경변수로 전달하며 자동 로드 없음 | API 8001 |
| 광고 API·광고 작업자 | `ad-server/backend/pyproject.toml`·`uv.lock`, 해당 폴더의 `.venv` | [예시](../../ad-server/backend/.env.example)를 `ad-server/backend/.env`로 배치, 광고 settings가 로드 | 기본 개발 API 8000 |
| 날씨 수집·Spark·관리자 ES 발행 | [requirements](../../pipeline/weather/requirements.txt), [Spark 추가 의존성](../../pipeline/weather/requirements-spark.txt), `pipeline/weather/.venv` 권장 | [예시](../../pipeline/weather/.env.example)를 `pipeline/weather/.env`에 보관, 실행 시 프로세스 환경변수로 전달. 자동 로드 없음 | HTTP 서버 없음 |
| 공개 React | `frontend/package.json`·`pnpm-lock.yaml` | [예시](../../frontend/.env.example)를 `frontend/.env.local`로 복사, Vite가 로드 | 5173 |

날씨 `.env`의 새 위치는 `C:/Users/Playdata/Documents/ChatGPT/3th/pipeline/weather/.env`입니다. 실제 키·비밀번호·DSN은 Git이나 문서에 기록하지 않습니다. 설정 이름·DB·컬렉션·권한은 각 예시와 INF 계약을 따릅니다.

Vite는 광고 `/api/ads`, `/api/ad-events`, `/api/ad-deliveries/`, `/api/admin/ads`, `/api/admin/ad-assets`를 광고 API로 보내고, 나머지 `/api`는 추천/공통 호스트로 보냅니다. 두 목적지는 `VITE_ADS_API_TARGET`과 `VITE_RECOMMENDATION_API_TARGET`으로 바꿀 수 있습니다. 경로를 재작성하지 않습니다. 공유 ADMIN·guest·지역 API·날씨 추천 어댑터는 별도 연결 대기입니다.

광고 sandbox는 정식 광고 API와 다른 개발 전용 실행 모드입니다. 기존 안내의 sandbox 8001은 단독 확인용이며 추천 API와 동시에 같은 포트로 실행하지 않습니다. 이 문서는 AWS 배치·공유 인증·실제 DB 접속 완료를 뜻하지 않습니다.

[통합 폴더 변경 라우팅](../../docs/development/통합_폴더_정리_변경_라우팅.md)에서 경로 변환·실행 명령·검증 결과를 확인합니다.
