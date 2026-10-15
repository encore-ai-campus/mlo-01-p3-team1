# ad-server/backend/config/sandbox_urls.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../../ad-server/backend/config/sandbox_urls.py)

로컬 확인 도구에서만 사용하는 URLconf입니다. `/` 이동과 `/dev/ads/` 대시보드·login/logout·status/refresh를 등록하고 기존 `config.urls`의 광고/health API를 함께 연결합니다.

기존 `config.urls`가 이 파일을 포함하는 구조가 아닙니다. 일반 서버에는 `/dev/ads/`가 없으며, sandbox 설정의 middleware가 여기서 호출하는 기존 관리/공개 API도 로컬 로그인으로 보호합니다. 정식 `/admin/ads`나 React·공통 로그인 라우팅을 대체하지 않습니다.

URL 목록 대입으로 구성되며 AST 클래스·함수 심볼은 없습니다.

## AST 시그니처

검사기가 추출한 클래스·함수·메서드 심볼은 없습니다.
