# 관리자 3역할과 서비스·Kibana SSO 변경 라우팅

- 작성일/수정일: 2026-10-19
- 작성자/담당: Codex, 사용자 지시에 따른 공통 관리자 역할·통합 발급·SSO 연결 코드
- 작업 범위: I-05/D-02, 관리자 공통 인증·광고 인증 브리지·운영 대시보드 인계
- 브랜치/기준 커밋: develop / 183ea87, 업로드 브랜치 codex/admin-sso-dashboards
- 상태: 로컬 구현·검증 후 2026-10-19 사용자 지시로 GitHub 업로드 준비. 운영 DB migration/IdP/Elastic 설정은 적용하지 않았으며 배포하지 않았습니다. 아래 각 단계의 커밋·푸시 없음은 당시 실행 이력입니다.

## 기준과 결정

사용자가 계정 하나에 최상위(전체), 광고(광고 관리), 운영(운영 관리)을 요구했고 최상위·운영의 Kibana 접근과 SSO 코드 수정을 지시했습니다. [기능/흐름](../product/카페_음악_서비스_기능_및_사용자_흐름_정리.md), [설계도](../product/카페_음악_서비스_구현_설계도.md), [추천 가이드](../product/카페_음악_추천_서비스_3차_컬럼_기반_추천_로직_가이드.md), [태스크](../product/카페_음악_추천_서비스_3차_구현_태스크.md), 공통 계약과 기존 INF 운영 대시보드 라우팅을 확인했습니다. 수령 원문 docs/handoff/infra/README.md(2026-10-14 수령), 날씨·음악·광고 인계는 변경하지 않았습니다. 이전 세 기능별 권한과 별도 Kibana 계정 설명은 이 구현의 변경 전 상태입니다.

OIDC는 표준 연결이고 통합 발급 어댑터는 Keycloak을 대상으로 구현했습니다. 실제 Keycloak 설치/운영 제품 채택·서버 설정은 INF 연결 대기입니다. Kibana OIDC 라이선스·HTTPS가 필요하며 무료 체험이나 유료 기능을 자동 활성화하지 않습니다. 설정을 켜지 않은 기존 로컬 환경은 기존 기능 권한 계정을 유지합니다. 운영 환경은 명시 역할이 필요하며 기존 계정은 자동 승격/분류하지 않습니다.

## 기준 → 코드 → 검증 연결

| 변경 코드/설정 | 변경 전 → 변경 후, 이유 |
|---|---|
| backend/common/admin_roles.py: role_for/permitted/assign_role/revoke_sessions | 기능별 직접 권한 → SUPER_ADMIN/ADS_ADMIN/OPS_ADMIN 중 하나. 기능 권한·슈퍼유저 플래그를 추가해도 역할 경계를 넘지 못함. 역할 변경 시 세션 회수 |
| common/models.py, migrations/0006* | view_operations 추가, AdminSSOIdentity로 issuer+sub와 앱 계정 유일 바인딩. 이메일/표시 이름 자동 연결 없음 |
| common/identity.py: admin, common/api.py: account_data_for_user/account_data/Login/Logout | 매 API 역할 검사, admin_role·SSO 설정·운영 메뉴 응답 추가. role=ADMIN·기존 allowed_menus 형태 유지. 광고 브리지는 기존 ADMIN 계약 그대로 역할별 manage_ads 검사 |
| common/sso.py: oidc_client/claims_role/sync_identity/SSOLogin/SSOCallback/KibanaDashboard/logout_url | Authlib authorization code + PKCE S256, state/nonce/RS256 서명/issuer/audience/만료 검사. HTTPS 고정 callback·서버 지정 Kibana 경로, 복수 역할 거절. 토큰을 응답/로그/브라우저 저장소에 쓰지 않음 |
| common/sso_provision.py: KeycloakAdmin/provision, commands/provision_sso_admin.py | 발급·역할 교체·회수·임시 비밀번호 초기화를 하나의 명령으로 처리. 기본 dry-run. 외부 IdP 계정과 앱 바인딩을 만들며 별도 Kibana native 계정은 만들지 않음 |
| common/sso_tokens.py: invalidate_kibana | IdP 세션 종료만 믿지 않고 cafe_sso realm + 해당 sub의 ES access/refresh token 무효화. 부분 실패는 성공으로 보고하지 않음 |
| commands/bootstrap_admin.py / prepare_runtime.py / check_runtime.py | 명시 --role/BOOTSTRAP_ADMIN_ROLE·역할 변경 추가, SSO 계정은 통합 명령 사용 강제. 과거 로컬 테스트 권한 발급은 유지하되 운영은 역할 필수. 준비 점검도 실제 permitted로 확인 |
| backend/cafe/settings.py, backend/.env.example, requirements.lock | SSO 기본 OFF, 켜면 로컬 비밀번호 로그인 기본 OFF. 서버 전용 IdP/Elastic 설정, Authlib 1.9.1·joserfc 1.7.7 추가 |
| frontend AdminPages.tsx / YoutubeAdmin.tsx / AdsAdmin.tsx | 통합 로그인 버튼·로컬 폼 조건부 표시·운영 메뉴 연결, 로그아웃 후 IdP 종료로 이동, 미확인 로그아웃 안내 |
| frontend/scripts/admin-sso-smoke.cjs | 외부 API를 가로채는 격리 브라우저 검사. 실제 발급/게시 없이 통합 로그인·로컬 폼 표시·운영 메뉴·IdP 로그아웃 이동 확인 |
| common/test_admin_sso.py / test_youtube_admin.py / test_runtime.py | 실제 RSA 서명 토큰과 가짜 HTTP 응답으로 프로토콜 검증, 역할 매트릭스·API 차단·발급 실패/회수 검증. 기존 운영 테스트 2곳은 명시 OPS_ADMIN을 사용하도록 조정 |
| config/environments/sso/* | Keycloak 2-client/3-group, ES realm, Kibana provider/space 권한, 단일 역할 매핑 예제와 발급/복구 인계. 기존 aws-infra bootstrap·원격 리소스는 변경하지 않음 |
| .gitignore | 검증 도구가 생성한 .pnpm-store/ 패키지 캐시를 제외. 비밀값/환경 파일 정책은 유지 |

## API와 저장·발급 순서

- GET /api/auth/me: 기존 authenticated/role/allowed_menus/csrf_token 유지, admin_role/sso_enabled/local_login_enabled 추가. SUPER_ADMIN은 앱 전체, ADS_ADMIN은 광고만, OPS_ADMIN은 음악·YouTube·피드백·운영 화면. 기존 allowed_menus의 운영 경로는 주소가 있을 때만 반환하지만, 아래 후속 구현은 별도 kibana_dashboard 상태로 주소가 없어도 권한자의 버튼을 표시합니다.
- GET /api/auth/sso/login → IdP code 승인 → GET /api/auth/sso/callback → 토큰 검증 → issuer/sub 바인딩 → 단일 그룹 동기화 → Django 세션 → 역할 첫 메뉴. IdP 미설정/연결 실패 503, state/서명/토큰 실패 401, 잘못된 역할/비활성 계정 403. API 오류에 원격 응답·secret을 넣지 않습니다.
- GET /api/admin/operations/kibana: 로그인·view_operations·SSO 세션을 검사하고 설정된 HTTPS 주소로 이동. Kibana 직접 URL은 ES의 cafe_sso 그룹 매핑으로 다시 검사합니다. 앱 메뉴 숨김만으로 접근 제한을 대신하지 않습니다.
- POST /api/auth/login: SSO 모드의 로컬 로그인 차단 시 SSO_REQUIRED 403. 허용된 로컬 계정도 역할 기반 메뉴가 있어야 로그인합니다.
- POST /api/auth/logout: CSRF 검사 → 해당 sub의 Kibana 토큰 무효화 → 앱 세션 삭제 → logout_url에 IdP 종료 주소. 실패 시 앱 세션을 먼저 지우고 incomplete 안내. IdP 종료 확인 여부는 실제 제공자 설정에 따라 검증합니다.
- provision_sso_admin: 기본 dry-run. --apply일 때 비활성 계정/바인딩 → 기존 로컬·IdP·ES 세션 회수 → IdP 단일 그룹과 앱 역할 → 임시 비밀번호 → 활성화. 실패 시 비활성 유지, 원격 차단 복구 실패 시 명시 오류. 로컬·원격을 하나의 트랜잭션으로 표시하지 않습니다.
- 앱 계정·역할·바인딩·세션은 공통 PostgreSQL(테스트 SQLite), 사용자 인증/임시 비밀번호/SSO 세션은 IdP, Kibana 권한/토큰은 Elasticsearch입니다. Kafka/outbox·음악/날씨/광고 데이터 저장에는 변경 없습니다.

SSO API에는 인증 redirect의 code/state가 포함되므로 운영 프록시/접근 로그에서 /api/auth/sso/callback의 쿼리와 Authorization/Cookie를 마스킹해야 합니다. 서비스 코드가 token을 출력하지 않아도 프록시 설정 검증은 별도입니다.

## 검증과 인계

검증은 로컬 가상환경·격리된 테스트 DB, C_LOCAL_DEMO=1/INTEGRATION_ENABLED=0으로 진행했습니다. signed token 검증은 Authlib/joserfc의 실제 암호 검증을 사용하고 외부 HTTP는 테스트 응답으로 대체했습니다. 실제 Keycloak·Kibana 연결 완료를 의미하지 않습니다. 결과는 아래 최종 검사 기록으로 갱신합니다.

- `python -B -m backend.manage test backend.common backend.music backend.recommendation backend.weather tests --noinput --verbosity 0`: **266건 통과**, system check 오류 없음. 새 관리자/SSO 회귀 18건 포함.
- `pnpm --dir frontend test`: **52건 통과**. `pnpm --dir frontend build`: TypeScript/Vite 성공.
- `python -B -m backend.manage makemigrations --check --dry-run`: No changes detected. common 0006 파일을 추가했으며 실제 서비스 DB에는 적용하지 않았습니다.
- `python -B scripts/check_routing.py`: 기존 3범위와 새 docs/admin-sso-routing 전체 통과. 기존 담당의 문서는 덮어쓰지 않고 별도 선언 색인을 작성했습니다.
- `python -B -m backend.manage provision_sso_admin handoff-example --role OPS_ADMIN`: applied=false, service/identity_provider 계획만 반환. 실제 발급 없음.
- `node frontend/scripts/admin-sso-smoke.cjs`: 빌드 미리보기(127.0.0.1:19175)와 격리 Edge 브라우저에서 통합 로그인 링크, SSO-only 비밀번호 폼 숨김/명시 허용 시 표시, 운영 메뉴, IdP 로그아웃 이동 모두 통과. pageerror 0. 외부 API는 가로챘으며 실제 IdP/Kibana 로그인 시험은 아닙니다. 임시 미리보기 서버는 검증 후 종료했습니다.
- `git diff --check`: 통과. 추천 계산·날씨 수집/조회 코드의 변경 없음.

같은 작업 트리에서 진행 중인 관리자 디자인 변경을 확인했고 해당 공통 AdminLayout은 기존 allowed_menus와 logout_url을 수용합니다. 그 작업의 신규 화면·목업·라우팅·공개 YouTube 검수 스타일은 본 작업으로 되돌리거나 덮어쓰지 않았습니다. 이번 SSO 인계는 관리자 화면 변경의 저작/완료 선언을 대신하지 않습니다.

인프라 적용 순서·비밀 설정 이름·명령·오류 복구·공식 근거는 [SSO 인프라 인계](../../config/environments/sso/README.md)를 따릅니다. 남은 항목은 실제 OIDC 지원 라이선스, HTTPS/IdP 배포, client secret과 발급 토큰·ES 회수 권한, operations space에 기존 dashboard 복사, 3역할 실제 로그인/직접 URL/열린 세션 회수 검증입니다. 기존 로컬 계정·미커밋 광고 이미지·타 작업 목업은 그대로 보존했습니다.

## 후속: 권한별 Kibana 버튼과 연결 대기 표시 — 2026-10-19

사용자가 관리자 화면의 명시적인 이동 버튼과 주소 미설정 시 비활성 표시를 요청했습니다. `common.api.account_data`에 `kibana_dashboard={allowed,configured,path}`를 추가했습니다. allowed는 서버의 view_operations 권한이며 configured는 SSO 사용 및 유효한 HTTPS 주소 여부입니다. 권한이 있고 설정됐을 때만 path=/api/admin/operations/kibana이고 나머지는 null입니다. 실제 Kibana 주소/비밀값을 클라이언트에 노출하지 않습니다.

`frontend/src/features/admin/KibanaDashboardButton.tsx`를 공통 `AdminHeader`에 연결해 SUPER_ADMIN/OPS_ADMIN에는 **Kibana 운영 대시보드** 버튼을, 연결 설정 미완료면 disabled와 **연결 준비 중** 표시를 제공합니다. ADS_ADMIN과 비로그인은 숨깁니다. enabled 버튼은 고정 내부 경로로 이동하며 서버의 역할·SSO 검사와 Kibana의 역할 검사는 유지합니다. nav의 기존 운영 링크는 필터링해 중복 표시하지 않습니다. 광고 화면도 이미 공통 AdminHeader를 사용하므로 같은 정책을 적용하고 AdsAdmin의 Me 타입은 공통 AdminMe를 재사용합니다. 공통 관리자 CSS에 버튼/비활성/키보드 포커스 스타일만 추가했습니다.

검증: 전체 백엔드 **267건 통과**(새 버튼 상태 회귀 1건 포함), 프론트 **52건 통과** 및 TypeScript/Vite 빌드 성공. 격리 브라우저에서 최상위·운영의 활성 이동/미설정 비활성 표시, 광고 계정 숨김, 좁은 화면 배치와 SSO 로그아웃을 확인합니다. 실제 인프라의 링크·SSO는 여전히 적용 대기입니다. 이번 요청에서도 커밋·푸시·외부 계정/인프라 변경은 하지 않습니다.

## 후속: 운영·로그 대시보드 분리 — 2026-10-19 최신 사용자 결정

사용자가 운영 대시보드와 로그 대시보드는 별도 두 개라고 정정하고 두 버튼으로 분리하도록 지시했습니다. 단일 Kibana 버튼 설명보다 이 절이 우선합니다. 권한은 둘 다 기존 view_operations(SUPER_ADMIN/OPS_ADMIN)이며 ADS_ADMIN은 둘 다 차단합니다.

- `backend/common/admin_dashboards.py`의 target_for/access_for와 공통 API는 각각 ADMIN_OPERATIONS_DASHBOARD_URL, ADMIN_LOG_DASHBOARD_URL을 독립 확인합니다. URL·SSO 미설정, 잘못된 HTTPS/포트는 해당 버튼만 비활성화합니다. 기존 ADMIN_KIBANA_URL은 운영 주소의 이전 설정 호환에만 사용하며 로그 주소로 재사용하지 않습니다.
- GET /api/auth/me에 operations_dashboard, log_dashboard를 각각 {allowed,configured,path}로 제공합니다. kibana_dashboard는 이전 클라이언트 호환용 운영 alias로만 유지합니다. 주소·비밀값은 응답에 넣지 않습니다.
- `sso.OperationsDashboard`의 GET /api/admin/operations/dashboard는 운영 주소, `sso.LogDashboard`의 GET /api/admin/operations/logs는 로그 주소로 이동합니다. 각각 서버 역할·SSO 세션·HTTPS 검사를 거칩니다. 이전 /operations/kibana 경로도 운영 alias로 보존합니다.
- `KibanaDashboardButton.tsx`는 kind=operations/logs로 **운영 대시보드**, **로그 대시보드**를 각각 렌더링합니다. 공통 AdminHeader에 두 개를 연결하고 기존 단일 nav 링크는 중복 표시하지 않습니다. 연결 안 된 항목만 연결 준비 중(disabled)이며, 한쪽 연결이 다른 버튼 상태에 영향을 주지 않습니다.
- `settings.py`와 `.env.example`, SSO 인프라 인계에 두 개의 설정 이름을 추가했습니다. 기존 SSO 역할·Kibana space/인덱스 접근 권한은 유지하며 두 목적지의 실제 인증/대시보드 배치는 INF가 확인해야 합니다.
- 회귀: 전체 백엔드 **268건 통과**, 프론트 **52건 통과**, 타입/Vite 빌드 통과. 3역할×주소 4조합에서 두 API의 독립 상태/이동/거절을 검사합니다. 격리 브라우저도 두 목적지·각각의 미설정 상태·390px 배치·광고 역할 숨김을 확인합니다. 실제 인프라 SSO 검증은 별도입니다.
- 로컬 확인 API(19001)는 기존 preview.sqlite3와 로그인 세션을 유지한 채 재시작했습니다. 실제 주소를 임의 설정하지 않아 로컬 최상위 계정에는 두 버튼 모두 연결 준비 중으로 표시됩니다. 코드 커밋·푸시·외부 설정 변경은 하지 않았습니다.

## 최신 develop 대조와 업로드 — 2026-10-19

사용자 요청으로 원격을 다시 fetch했고 develop@183ea87이 로컬 기준과 동일함을 확인했습니다(앞섬/뒤처짐 0/0). 업로드는 저장소의 develop 직접 푸시 금지 방침에 따라 codex/admin-sso-dashboards에서 수행합니다. 공통 관리자 헤더·음악/YouTube/제외 화면이 이번 역할/SSO UI와 연결돼 있으므로 관련 소스·디자인 라우팅·시안·검증 스크립트를 함께 포함합니다. 별도 광고 이미지 6종과 그 작업 라우팅, .env·로컬 계정·DB·실행 로그는 업로드 대상에서 제외합니다. develop 실제 병합/배포는 이번 업로드 범위에 포함하지 않습니다.

## 병합 전 PostgreSQL CI 보완 — 2026-10-19

사용자의 후속 병합/브랜치 삭제 요청으로 GitHub CI를 확인했고, PostgreSQL 제외 이력 회귀 2건이 403으로 실패했습니다. 테스트 계정이 개별 view_feedback만 갖고 있어 새 운영 환경의 단일 역할 정책을 통과하지 못한 것이 원인입니다. `backend/common/test_exclusion_history.py`의 setUp은 OPS_ADMIN을 명시하도록 바꿨고, 클래스에 LOCAL_DEMO=False를 고정해 로컬 SQLite 회귀에서도 운영 권한 경로를 반드시 검사합니다. revision/as_of 정합성 검사와 운영 권한 요구를 완화하지 않았습니다. 함수 시그니처는 그대로이며 코드 변경 근거는 이 절에 남깁니다. 실제 PostgreSQL 재검증은 GitHub CI로 확인한 뒤에만 병합합니다.

## 병합 전 브라우저 CI 보완 — 2026-10-19

PostgreSQL 재검사는 통과했지만 브라우저 통합은 이전 음악 관리 제목(음악 등록 · 검수)을 기다리다 실패했습니다. frontend/scripts/integration-smoke.cjs의 제목 검사를 현재 화면의 음악 관리로 갱신하고, tests/run_browser_integration.py의 격리 계정은 모든 개별 권한을 부여하는 방식 대신 SUPER_ADMIN 역할을 명시하도록 변경했습니다. 실제 API→worker→테스트 DB 연결 검사와 공개 추천·피드백·지역·관리 이력·로그아웃 검사는 유지합니다. 실제 운영 계정은 이 테스트와 관계없이 INF에서 재발급합니다.

이력 조회 버튼의 접근성 이름도 현재 곡별 '이력 보기'에 맞춰 갱신했습니다. python -B tests/run_browser_integration.py(BROWSER_USE_BUILD=1)에서 실제 공개 추천·반응/평가/제외·지역 선택·관리자 로그인/이력/로그아웃 통합, 광고 레이아웃, 공개 배너 proof/재시도 검사 세 묶음이 모두 통과했습니다. 광고 HTTP 부분은 격리 응답이며 MongoDB 통합은 별도 GitHub CI에서 검사합니다.
