# backend/config/settings.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../backend/config/settings.py)

Django/DRF 환경과 저장소 접속·서버 어댑터 설정을 구성합니다. 입력은 환경변수와 `backend/.env`이며 기존 환경변수를 덮어쓰지 않습니다. 비밀값은 문서에 기록하지 않습니다. 비밀키가 없거나 비개발 환경에서 예시 키를 사용하면 로딩을 차단합니다.

공통 DB는 Django PostgreSQL backend, 광고는 ADS_MONGODB_URI/ADS_MONGODB_DATABASE로 구분합니다. ADS_IS_TEST는 저장 레코드 범위를 분리합니다. ADS_ADMIN_AUTHORIZER와 ADS_LOG_SINK는 공통 담당자의 서버 callable 경로이며 미설정 관리/로그 전달은 각 경계에서 차단됩니다. ADS_API_CONTRACT_VERSION은 합의된 값이 있을 때 응답 헤더에만 연결합니다.

세션/CSRF 미들웨어, Argon2, UTC와 timezone-aware 시각을 사용합니다. 기본 DRF 인증은 세션/IsAuthenticated이며 광고 API의 공유 어댑터와 공개 health는 각 view의 경계를 사용합니다. 이 모듈은 계정·세션 원본을 생성하거나 공통 migration을 적용하지 않습니다.

정의된 클래스·함수는 없습니다.

COMPONENT_SPLIT_REQUEST=True로 업로드 요청의 binary 파일과 응답 필드를 별도 OpenAPI 컴포넌트로 구분합니다.
