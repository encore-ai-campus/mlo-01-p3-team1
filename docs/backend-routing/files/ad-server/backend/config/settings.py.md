# ad-server/backend/config/settings.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../../ad-server/backend/config/settings.py)

Django/DRF 환경과 저장소 접속·서버 어댑터 설정을 구성합니다. 입력은 환경변수와 `ad-server/backend/.env`이며 기존 환경변수를 덮어쓰지 않습니다. 비밀값은 문서에 기록하지 않습니다. 비밀키가 없거나 비개발 환경에서 예시 키를 사용하면 로딩을 차단합니다.

공통 인증 DB는 Django PostgreSQL backend, 광고와 광고 로그는 ADS_MONGODB_URI/ADS_MONGODB_DATABASE로 구분합니다. ADS_IS_TEST는 저장 레코드 범위를 분리합니다. ADS_ADMIN_AUTHORIZER는 공유 인증 담당자의 서버 callable 경로이며 미설정 관리 요청은 차단됩니다. ADS_LOG_SINK는 제거했습니다. ADS_API_CONTRACT_VERSION은 합의된 값이 있을 때 응답 헤더에만 연결합니다.

공개 단계는 공통 guest·서명 키·HTTPS 주소의 외부 설정이 필요합니다. ADS_PUBLIC_POLICY_PROVIDER는 기본 domains.ads.runtime_policy.get_public_policy를 연결하여 채택한30분/표시보고분리·5분 검증 상태·소재 이력을 사용합니다. 누락/잘못된 공유 guest/서명/주소는 해당 공개 경계에서503이며 광고별 예산액을 임의 생성하지 않습니다. 실제 키값·공유 서비스·반복 프로세스/배포는 별도 인계입니다.

세션/CSRF 미들웨어, Argon2, UTC와 timezone-aware 시각을 사용합니다. 기본 DRF 인증은 세션/IsAuthenticated이며 광고 API의 공유 어댑터와 공개 health는 각 view의 경계를 사용합니다. 이 모듈은 계정·세션 원본을 생성하거나 공통 migration을 적용하지 않습니다.

정의된 클래스·함수는 없습니다.

COMPONENT_SPLIT_REQUEST=True로 업로드 요청의 binary 파일과 응답 필드를 별도 OpenAPI 컴포넌트로 구분합니다.
현행 로그 구조와 이전 자료 보존은 [광고 로그 저장 계약](../../../../../development/ads/MongoDB_광고_로그_저장_계약.md)을 따릅니다.

## AST 시그니처

```python

```
