# Django 관리자 → Kibana Native 로그인 연결 (무료 Basic)

2026-10-19. 이 문서는 기존 Kibana/Elasticsearch를 유지하고 **SSO 없이 두 개의 관리자 전용 URL을 연결**하는 계약입니다. 기존 Keycloak/OIDC 예제는 제거하지 않습니다.

## 화면·권한 경계

- Django 관리자 헤더: `운영 대시보드` → `music-operations-v1`, `사용자 행동 분석` → `music-guest-behavior-v1`.
- Django의 `SUPER_ADMIN`, `OPS_ADMIN`에만 버튼을 표시하고 `view_operations` 서버 권한을 검사합니다. `ADS_ADMIN` 및 비로그인 요청은 URL을 직접 입력해도 거부합니다.
- 외부 URL은 **서버 고정 설정**에서만 가져옵니다. HTTPS, 허용된 호스트명, `/ops/[s/<space>/]app/dashboards#/view/<정해진-ID>`만 통과합니다. 프래그먼트 쿼리는 `_g`, `_a`만 허용합니다. 호스트 허용 목록이 비어 있으면 버튼 비활성화/503 처리합니다.
- 이 이동은 SSO나 로그인 우회가 **아닙니다**. 외부 Kibana는 독립적으로 Native/Basic 인증과 Elastic 역할·인덱스 권한을 반드시 검사합니다. Django 로그아웃은 Kibana 세션을 종료하지 않습니다.
- Kibana 계정은 사용자별로 별도 발급·회수합니다. 애플리케이션 `SUPER_ADMIN`이라도 Elastic `superuser` 권한을 자동 획득하지 않습니다. 공유 `ops_admin` 계정을 개인별 운영 계정 대신 배포하지 않습니다.

## 서버 환경 설정 (실제 비밀값을 Git에 저장하지 않음)

```dotenv
ADMIN_SSO_ENABLED=0
ADMIN_LOCAL_LOGIN_ENABLED=1
ADMIN_KIBANA_ALLOWED_HOSTS=d55cemi1yl53l.cloudfront.net
ADMIN_OPERATIONS_DASHBOARD_URL=https://d55cemi1yl53l.cloudfront.net/ops/app/dashboards#/view/music-operations-v1
ADMIN_LOG_DASHBOARD_URL=https://d55cemi1yl53l.cloudfront.net/ops/app/dashboards#/view/music-guest-behavior-v1?_g=(filters:!())
```

Django 측 HTTPS/CSRF/세션 설정은 기존 운영 값을 유지합니다. 특정 Kibana Space를 사용한다면 URL에 `/ops/s/<space>/app/dashboards`를 사용하고 아래 Elastic 권한도 일치시킵니다.

## 실제 Kibana 설정

1. Kibana가 401/로그인 화면으로 비인증 접근을 차단하는지 검증합니다. 익명 provider·무인증 reverse proxy·공개 링크는 허용하지 않습니다.
2. `roles.example.json`의 `cafe_dashboard_reader`를 기존 관리자 권한으로 Kibana Role API에 신규 등록합니다. 이는 기본 Space에 두 대시보드가 있는 경우의 **읽기 전용 역할 예제**입니다. 실제 Space와 Data View 소유 위치를 확인해 조정해야 합니다.
3. 운영자별 Kibana Native 계정을 생성하여 **이 읽기 전용 역할만** 부여합니다. 기존 `ops_admin` 관리자나 서비스 토큰의 비밀번호/권한은 변경하지 않습니다. `ADS_ADMIN`에게 Kibana 계정을 발급하지 않습니다.
4. 계정별 브라우저에서 운영·행동 분석 화면 정상, 무권한/익명 직접 URL 차단, 데이터 읽기만 가능함을 확인합니다.
5. 기존 Control 앱 릴리스/설정 백업, 새 `frontend/dist` 및 Django 코드 검증 후 Control A/B에 단계적 적용합니다. 서비스 복구 경로를 먼저 확보하고 광고 EC2·ES/Kibana 대시보드 객체·피드백 수집기를 재시작하지 않습니다.

## 주의

- Basic에서 이용할 수 있는 Native 로그인/RBAC만 사용합니다. `ADMIN_SSO_ENABLED=1`인 기존 OIDC 흐름은 이 경로와 별개이며 그대로 보존됩니다.
- Kibana 로그인만 된 사용자가 링크를 직접 입력해 접근하는 것을 Django에서 차단할 수는 없습니다. **최종 접근 통제는 Kibana/Elasticsearch 권한**으로 이루어집니다.
- Kibana Native 계정이나 권한이 변경되면 Django 관리자 역할이 자동 동기화되지 않습니다. 운영 절차로 두 계정을 함께 부여/회수해야 합니다.
