# backend/config/urls.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../backend/config/urls.py)

현재 구현된 health와 광고 관리 HTTP 경로를 등록합니다. 실제 메서드/view/service 대응은 상위 색인의 API 연결 표에 기록했습니다. DEBUG 환경의 `/api/schema`는 SpectacularAPIView로 연결합니다.

광고 관리 요청은 AdsAdminView의 공통 ADMIN·CSRF 경계를 통과해야 합니다. `/admin/ads` 관리 화면이나 공개 delivery·이벤트·통계 endpoint는 구현하지 않았습니다. 프런트엔드 화면 라우팅은 이 URL 모듈의 구현 범위에 포함하지 않습니다.

정의된 클래스·함수는 없습니다.
