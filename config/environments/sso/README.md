# 관리자 3역할·서비스/Kibana SSO 인프라 인계

- 작성일/수정일: 2026-10-19
- 상태: 코드·공개 예제. 실제 IdP/Elastic 라이선스·HTTPS·브라우저 SSO 연결은 미검증이며 배포하지 않았습니다.
- 구현·검증 기록: [변경 라우팅](../../../docs/development/관리자_3역할과_SSO_변경_라우팅.md).

## 역할과 계정 기준

2026-10-19 최신 화면 계약: 관리자 헤더의 **운영 대시보드**, **로그 대시보드**는 별도 버튼입니다. INF는 `ADMIN_OPERATIONS_DASHBOARD_URL`, `ADMIN_LOG_DASHBOARD_URL`에 각각 실제 HTTPS 목적지를 지정합니다. 둘 다 최상위·운영만 표시하고 연결되지 않은 항목만 비활성화합니다. 기존 `ADMIN_KIBANA_URL`은 운영 주소의 이전 설정 호환으로만 사용하고 로그 주소를 자동 복제하지 않습니다. 실제 목적지의 OIDC/역할 권한도 각각 검증해야 하며, 두 화면이 서로 다른 Kibana/서비스 호스트라면 각 호스트의 클라이언트·callback·권한 설정이 필요합니다.

계정 하나에 SUPER_ADMIN(최상위), ADS_ADMIN(광고), OPS_ADMIN(운영) 중 하나를 지정합니다. SUPER_ADMIN은 앱의 모든 관리 메뉴와 Kibana 전체 space, ADS_ADMIN은 광고 관리만, OPS_ADMIN은 음악/YouTube 검수·피드백과 Kibana operations space의 대시보드/Discover 읽기를 허용합니다. 최상위는 Elasticsearch superuser나 AWS 관리자와 다릅니다. 운영 대시보드 수정 권한은 별도 채택 전 부여하지 않습니다.

OIDC 제공자를 공통 계정 기준으로 사용합니다. 앱과 Kibana는 별도 confidential client이며 같은 realm과 groups claim을 신뢰합니다. 구현한 통합 발급 어댑터는 Keycloak Admin REST API를 사용합니다. Keycloak 설치/버전 채택은 인프라 담당의 배포 작업이며 이번 작업에서 리소스를 만들지 않았습니다. 다른 OIDC 제공자는 로그인 계약을 재사용할 수 있지만 발급 어댑터는 별도 구현해야 합니다.

앱의 `role: ADMIN` 응답은 기존 광고 인증 계약을 위해 유지하고, `admin_role`에 구체적인 역할을 추가합니다. 권한은 메뉴뿐 아니라 서버 API에서도 검사합니다. 복수 관리 역할은 거절하고, 이메일/표시 아이디로 기존 계정을 자동 연결하지 않습니다. issuer+sub로만 바인딩하며 SSO 계정의 로컬 비밀번호는 사용할 수 없습니다.

## 적용 순서

1. Elastic OIDC/SAML SSO는 구독 기능입니다. 실제 라이선스가 OIDC를 지원하는지 확인합니다. 무료 체험 시작·결제·라이선스 변경은 자동화하지 않습니다. Basic 등 미지원 환경에서는 `ADMIN_SSO_ENABLED=0`을 유지합니다.
2. IdP·서비스·Kibana·Elasticsearch의 HTTPS와 인증서 신뢰를 먼저 준비합니다. 현재 인프라 문서의 임시 HTTP 구성을 SSO 운영 준비 완료로 간주하지 않습니다. 프록시가 HTTPS를 종료하면 신뢰할 수 있는 프록시만 forwarded 정보를 설정하게 하고 Django CSRF trusted origin/allowed host도 실제 도메인으로 맞춥니다.
3. `keycloak-realm.example.json`의 example.org 도메인을 실제 주소로 바꿔 새 realm/client를 준비합니다. 기존 realm을 통째로 덮어쓰지 않습니다. 두 client의 서로 다른 secret은 IdP에서 발급해 서버 비밀 저장소에 넣습니다. 예제에는 계정/비밀번호/secret을 넣지 않았습니다. 웹 client는 PKCE S256이며 두 client 모두 표준 code flow를 사용합니다. `groups` mapper는 full.path=false, ID token claim=true가 필요합니다.
4. `elasticsearch-oidc.example.yml`을 관련 ES 노드의 기존 설정에 병합하고, Kibana client secret은 `elasticsearch-keystore`의 `xpack.security.authc.realms.oidc.cafe_sso.rp.client_secret`에 넣습니다. realm 이름 cafe_sso와 claims.principal=sub는 토큰 회수 코드와 고정 계약입니다. 기존 native 서비스 인증은 보존합니다.
5. `kibana-roles.example.json`의 각 항목을 Kibana `PUT /api/security/role/<이름>`에 적용합니다. `elastic-role-mappings.example.json`은 ES `PUT /_security/role_mapping/<이름>`에 적용합니다. realm 조건과 단일 그룹 조건을 함께 사용하며 ADS_ADMIN 또는 복수 역할은 Kibana 역할을 받지 않습니다. 기존 광범위 OIDC 자동 매핑이 있으면 제거/조정해야 합니다.
6. Kibana operations space를 만들고 기존 music-operations-v1 대시보드와 필요한 saved object/data view를 복사합니다. 기존 저장 객체·대시보드·space를 삭제하지 않습니다. 최상위는 모든 space, 운영은 operations만 접근하게 합니다.
7. `kibana-oidc.example.yml`을 병합합니다. 일상 사용에 공유 ops_admin/basic 로그인 우회 경로를 노출하지 않습니다. 인증 전환 전에 INF가 별도 제한된 복구 경로를 확보해야 합니다. `ADMIN_OPERATIONS_DASHBOARD_URL`은 운영 대시보드, `ADMIN_LOG_DASHBOARD_URL`은 로그 대시보드의 실제 URL로 각각 지정합니다. Kibana 목적지에는 필요시 `auth_provider_hint=oidc1`을 포함합니다. `ADMIN_KIBANA_URL`은 이전 운영 주소의 호환용으로만 남깁니다.
8. `backend/.env.example`의 SSO 항목을 서버 비밀 설정에 채웁니다. `ADMIN_SESSION_SECONDS`는 양수여야 하며 앱 세션은 ID token 만료와 이 값 중 짧은 시간을 따릅니다. `ADMIN_SSO_ENABLED=1`이면 비밀번호 로그인은 기본 차단입니다. 브라우저를 통한 별도 native 계정 발급은 제공하지 않습니다.
9. 설치: `python -m pip install -r backend/requirements.lock`. DB 백업 후 `python -m backend.manage migrate`로 새 common 0006을 적용합니다. 기존 로컬 계정을 운영 DB에 복사하지 않습니다. SSO 환경에서는 BOOTSTRAP_ADMIN_USERNAME을 비워 두고 아래 발급 명령을 사용합니다.
10. 실제 3역할 계정으로 앱 로그인 → Kibana 이동 → 다른 대시보드 차단 → 역할 하향/회수 → 기존 열린 세션 차단을 확인합니다. 이 검증 전에는 연결 완료로 표시하지 않습니다.

## 계정 한 번에 발급·변경·회수

비밀값은 환경변수 또는 승인된 비밀 저장소로 전달하며 명령 인자에 넣지 않습니다. `ADMIN_SSO_PROVISION_TOKEN`은 해당 realm의 계정/그룹/세션 관리에 필요한 최소 권한의 단기 관리 토큰입니다. `ADMIN_SSO_INITIAL_PASSWORD`는 발급/초기화에만 필요하며 최초 로그인 시 변경하는 임시 비밀번호입니다.

`ADMIN_SSO_ELASTIC_API_KEY`는 cafe_sso 대상 사용자의 access/refresh token 무효화 API를 호출할 수 있어야 합니다. 권한·유효기간·호스트 접근을 제한해 별도 보관하고 브라우저에 전달하지 않습니다. 앱 로그아웃 서버와 발급 명령에서 사용하며, 실제 클러스터에서 요구 권한과 회수 성공을 확인해야 합니다.

```sh
# 먼저 계획만 확인: 외부 호출·DB 쓰기 없음
python -m backend.manage provision_sso_admin operator --role OPS_ADMIN

# IdP 계정 + 앱 바인딩 + 단일 역할 발급 (Kibana 계정 별도 발급 불필요)
python -m backend.manage provision_sso_admin operator --role OPS_ADMIN --apply
python -m backend.manage provision_sso_admin owner --role SUPER_ADMIN --apply
python -m backend.manage provision_sso_admin advertiser --role ADS_ADMIN --apply

# 역할 교체 / 회수 / 임시 비밀번호 재발급
python -m backend.manage provision_sso_admin operator --action set-role --role ADS_ADMIN --apply
python -m backend.manage provision_sso_admin operator --action revoke --apply
python -m backend.manage provision_sso_admin operator --action reset-password --apply
```

발급 명령은 IdP 로그인 이름을 받습니다. 앱 내부 username은 issuer+sub 해시이므로 운영자가 수동으로 이름을 맞추지 않습니다. 기존 IdP 사용자는 cafe_managed 표시와 앱 바인딩을 검사하고 임의로 채택하지 않습니다. 신규 발급은 비활성 IdP 계정 → 비활성 앱 바인딩 → IdP 세션 만료 및 ES 사용자 토큰 무효화 → 단일 그룹/앱 권한 → 임시 비밀번호 → 활성화 순서입니다.

역할 변경·회수·초기화도 로컬 세션, IdP 세션, ES/Kibana access/refresh token을 회수합니다. 실패 시 계정을 비활성 상태로 유지하고 성공을 보고하지 않습니다. 원격 복구도 실패하면 `partial_failure_local_disabled_remote_recovery_required`를 반환하므로 INF가 원격 상태를 확인해야 합니다. 분산 트랜잭션은 아니며 실패를 숨기거나 기존 열린 Kibana 세션 차단을 가정하지 않습니다. 중단된 신규 발급은 동일 사용자에 create를 재실행할 수 있지만 이미 활성 계정은 명시 변경만 허용합니다. 비활성 계정의 set-role/reset-password는 재활성화하지 않습니다. 재발급이 필요하면 비활성 상태를 확인하고 create로 임시 비밀번호까지 다시 지정합니다.

사용자가 앱에서 로그아웃하면 해당 subject의 Kibana 토큰을 무효화한 뒤 IdP 종료 화면으로 이동합니다. IdP에 따라 종료 확인이 필요할 수 있습니다. 서버 연결 실패 시 앱 세션부터 지우고 `/login?sso_logout=incomplete`에서 다른 대시보드 로그아웃 미확인을 안내합니다. IdP 콘솔에서 수동으로 바꾼 역할은 앱/ES 기존 세션에 즉시 반영된다고 보장하지 않으므로 일상 회수는 이 명령을 사용합니다.

## 공식 근거

- [Authlib Django OIDC](https://docs.authlib.org/en/latest/oauth2/client/web/django.html)
- [Elastic OIDC 설정·그룹 매핑·로그아웃](https://www.elastic.co/docs/deploy-manage/users-roles/cluster-or-deployment-auth/openid-connect)
- [Elastic SSO 구독 조건](https://www.elastic.co/docs/deploy-manage/users-roles/cluster-or-deployment-auth/kibana-authentication)
- [Elasticsearch 사용자/realm 토큰 무효화](https://www.elastic.co/guide/en/elasticsearch/reference/8.19/security-api-invalidate-token.html)
