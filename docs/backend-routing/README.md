# 광고 백엔드 코드 인계 색인

- 작성일: 2026-10-15
- 수정일: 2026-10-16
- 대상: 광고 관리·공개 API·MongoDB 원자 저장·MongoDB 내장 로그와 로컬 검증 도구. Python 파일별 문서는 AST 시그니처와 대조합니다.
- 상세 설계: [광고 데이터와 로직](../development/ads/광고_데이터와_로직_설계.md)
- 실행: [광고 서버 개발 준비](../runbook/광고_서버_개발_준비.md)

광고 관리3컬렉션·공개5컬렉션에 예산 검증/일일 집계2컬렉션을 연결했습니다. 관리/공개 API·이미지 원본·30분 배달의 표시/보고 분리·소재 이력·최초 판정/반복/예상 원장과5분 예산 검증/물리 통계를 구현했습니다. 관리·측정·소진 로그는 MongoDB log_record에 업무와 원자 저장합니다. 공통 SQL 로그 규격/외부 전달은 사용하지 않습니다.

5분 검증에서 합계가 한도 이상이면 예산 종료로 표시하고 신규·기존 배달 재확인·이미지를 차단합니다. 검증 시각 전 발생한 정상 보고는300초 안에서 초과분도 기록하고, 검증 시각과 같거나 이후의 발생은 제외합니다. 이는 예약/초과0 보장이 아니며 실제 결제·잔액 차감은 하지 않습니다. 수동 paused/기간/관리 수정 버전은 보존하고 기술 검증 지연은503으로 구분합니다.

기본 runtime provider는 채택한 정책을 연결하며 광고별 예산은 양의 정수2개와 서버 budget_version으로 명시합니다. 미설정/미검증 광고에는 임의 예산을 주지 않습니다. 표시 마감은30분/광고 종료, 보고 마감은 표시 뒤300초이며 재확인은 같은 delivery를 유지합니다. 배달 자체의 자정 단축은 cap_at_midnight=False입니다. 이전 배달의 필드/서명/최초 응답과 마커 없는 예산 판정은 소급 변경하지 않습니다.

정식 관리자·공개 배너 화면과 운영 배포는 기존 광고 로직 구현에 포함하지 않습니다. 이후 사용자 요청으로 [로컬 임시 도구](../development/ads/임시_광고_관리_도구.md)를 추가했습니다. sandbox 전용 설정/URLconf·loopback·ads_sandbox_dev/is_test=True에서 기존 API와5분 worker를 확인하는 예외이며 정식 React 관리자·공유 guest/ADMIN·AWS 운영 연결 완료를 뜻하지 않습니다. [정책 결정 가이드](../development/ads/광고_미정_정책_결정_가이드.md), [공개 선정/측정 인계](../development/ads/공개_선정과_측정_로직_인계.md)와 실제 구현 경계를 구분합니다.

## 적용 계약과 코드 경계

[ADS01 화면/API/측정](../handoff/ads/01_광고_화면_API와_측정_계약.md), [ADS05 최신 간소화 통합](../handoff/ads/05_광고_간소화_통합과_추가_인계.md), [공통 개발 계약](../product/3차_공통_개발_계약과_검증_기준.md), [공통 API/이벤트 JSON](../contracts/3차_공통_API_이벤트.schema.json)을 연결합니다. 3차는 카페 전용이며 업종/태그 입력을 거절합니다. 이미지/광고는 MongoDB, 사용자·세션 원본은 공유 환경, 광고 로그도 MongoDB에 저장하며 공유 사용자 인증은 별도로 유지합니다. 광고 예산/보관 기한 등 미정 운영값을 이 코드 문서에서 새로 확정하지 않습니다.

HTTP 오류는 `api/ads.py:error_response`에서 code/message/request_id 및 필요한 details.fields로 반환합니다. OpenAPI에도 ErrorResponseSerializer의 400/401/403/404/409/422/503 응답을 연결하고 저장 변경 요청의 Idempotency-Key 헤더를 명시합니다. 요청 컴포넌트는 추가 필드 불허와 multipart binary를 표시하며 x-shared-admin-required 마커로 공유 ADMIN 경계를 표시합니다. 미정 공통 쿠키 이름이나 인증 발급 프로토콜은 추가하지 않습니다. 실제 strict 입력은 validation.py, 권한/CSRF는 ads_auth.py, 멱등/version/감사는 service.py, 저장 원자성은 ads_mongo.py가 담당합니다. 인증 미설정은 AUTH_UNAVAILABLE(503), 광고 로그 저장 실패는 MongoDB 업무 트랜잭션을 롤백합니다. 새 인증/계정/로그 원본을 광고 도메인에서 만들지 않습니다.

공개 정책 설정 ADS_PUBLIC_POLICY_PROVIDER의 기본값은 domains.ads.runtime_policy.get_public_policy입니다. 외부 필수값은 공유 guest provider·배달 서명 키·공개 HTTPS 주소이며 미연결/잘못된 구성은 해당 경계에서503입니다. 상단 신규 조회만 guest 부트스트랩을 요청하고 쿠키 불가 표시의 운영 측정은 제외합니다. 요청은 클라이언트 사용자 ID/판정/회계 필드를 받지 않으며 proof와 서버 문맥을 사용합니다. 예산 검증 상태가300초를 넘기면 ADS_POLICY_UNAVAILABLE/503이고 새 ENDED를 만들지 않습니다.

## 실제 API 연결

아래 경로는 [config/urls.py](../../ad-server/backend/config/urls.py)의 실제 등록과 구현 메서드에 대응합니다. 기본 서버의 광고 관리 URL은 공통 ADMIN·광고 권한을 확인합니다. POST/PUT은 세션 CSRF도 확인하며 저장 변경 요청에는 Idempotency-Key가 필요합니다. 저장 전 미리보기 POST는 읽기 권한을 사용하고 저장·배달·측정을 만들지 않습니다. 별도 sandbox 설정으로 실행하면 같은 API를 개발 로그인으로 보호하며 공유 인증 성공으로 설명하지 않습니다.

| 메서드·경로 | 구현 view | 실행 연결/결과 |
|---|---|---|
| `GET /api/health` | `HealthView.get` | 프로세스 응답만 확인, DB 미조회 |
| `GET /api/ads` | `PublicAdsView.get` | 공유 guest → AdsPublicService.provide → 현재 자격/원자 delivery·순환 또는 동일 delivery 재확인 |
| `POST /api/ad-events` | `PublicAdEventsView.post` | CSRF/Origin·guest/proof → record_event → 최초 판정/claim/반복/예상 항목 원자 저장 |
| `GET /api/ad-deliveries/<delivery_id>/image` | `PublicAdImageView.get` | query proof·현재 게시/정책 자격 → 원본 FileResponse, guest 발급 없음 |
| `GET /api/admin/ads` | `AdsCollectionView.get` | query_filters → repository.list_ads → serialize_ad, 필터 유지 서명 커서·광고별 보관 범위 주기 지표 |
| `POST /api/admin/ads` | `AdsCollectionView.post` | AdsService.create_ad → repository.run, 광고+감사 원자 기록 |
| `PUT /api/admin/ads/<ad_id>` | `AdUpdateView.put` | AdsService.update_ad → 멱등 재생/version 조건부 갱신 |
| `POST /api/admin/ads/<ad_id>/stop` | `AdStopView.post` | AdsService.stop_ad → paused/중단 감사 기록 |
| `POST /api/admin/ad-assets` | `AdAssetUploadView.post` | AdsService.upload_asset → 이미지 Binary+감사 원자 기록 |
| `GET /api/admin/ad-assets/<asset_id>` | `AdAssetReadView.get` | verified_asset → 원본/metadata 무결성 확인 → FileResponse |
| `POST /api/admin/ads/preview` | `AdPreviewView.post` | validate_ad_input/verified_asset → 미리보기 자료, operational_delivery=false |
| `GET /api/admin/ads/summary` | `AdsSummaryView.get` | repository.summary/metrics_summary → 실제 상태 개수·오늘 주기 집계·범위/시각/지연, null/PENDING과 실제0 구분 |
| `GET /api/schema` (DEBUG) | `SpectacularAPIView` | 등록된 view의 OpenAPI schema |

정식 관리자 프런트엔드와 `/admin/ads` 화면은 이 구현에 없습니다. 아래 별도 개발 화면은 기존 API를 확인하는 임시 도구입니다. 통계의 null/연동 대기는 0건/토큰 0을 의미하지 않습니다. 서버는 활성 재확인에 최대3초 표시 기한을 제공하고 중단/종료에는 ad=null을 반환합니다. 실제3초 공개 배너 제거는 브라우저에서 별도로 검증해야 합니다.

### 별도 sandbox URLconf

[config/sandbox_urls.py](../../ad-server/backend/config/sandbox_urls.py)는 다음 개발 경로와 기존 API를 함께 등록합니다. 일반 config.urls에는 이 파일을 포함하지 않습니다. middleware가 요청의 실제 loopback IP/Host·테스트 설정/DB·실행별 서명 쿠키를 확인하고, 기존 관리/공개 API도 미로그인 접근을 차단합니다. CSRF/Origin·응답별 nonce CSP는 유지합니다.

| 메서드·경로 | 구현 view | 실행 연결/결과 |
|---|---|---|
| `GET /` | `ads_sandbox.home` | 개발 대시보드로 이동 |
| `GET/POST /dev/ads/login` | `ads_sandbox.login` | 실행별 접근 코드·CSRF 확인 후 instance/kind 서명 쿠키 |
| `GET /dev/ads/` | `ads_sandbox.dashboard` | 기존 API 기반 등록/수정/중단·예산/통계/미리보기 확인 |
| `POST /dev/ads/logout` | `ads_sandbox.logout` | 로컬 쿠키 삭제/CSRF 회전, 광고 게시 상태 유지 |
| `GET /dev/ads/status` | `ads_sandbox.status` | 현재5분 worker 상태·is_test/DB명·log_storage=MONGODB |
| `POST /dev/ads/refresh` | `ads_sandbox.refresh` | 같은 예산/통계 작업1회, 경합409·실패503 |

개발 로그도 MongoDB log_record에 원자 저장하며 이전 log_relay 기록은 보존합니다. is_test=True 공개 측정은 MEASUREMENT_UNAVAILABLE·counted=False/운영 예상량0입니다. 실제 가시성/3초 숨김·공유 인증·AWS 연결은 별도 검증입니다.

## 저장·로그 실행 연결

| 시작점 | 연결 | 완료/실패 경계 |
|---|---|---|
| 광고 관리 HTTP 요청 | AdsAdminView → authorize_admin → validation/AdsService → MongoAdsRepository.run | 공통 신원/CSRF 확인 후 변경+감사/멱등/내장 광고 로그를 한 MongoDB 트랜잭션으로 커밋 |
| 공개 신규 조회/재확인·이미지 | AdsPublicView → 정책/guest 또는 이미지 proof → AdsPublicService → MongoPublicAdsRepository.run | 광고 경합 검사·신규 커서/delivery 원자 저장; 재확인은 같은 delivery/커서 유지 |
| 공개 측정 HTTP 요청 | PublicAdEventsView → CSRF/guest/proof → record_event → judge_event | 최초 응답·delivery/type claim·반복 창·인정 시 예상 원장·내장 광고 로그 원자 커밋 |
| 광고/이미지 목록·읽기 | view → MongoAdsRepository._read | primary/is_test 범위, 실제 상태 계산·원본 검증 |
| `apply_ads_schema` | manage.py → Command → load_manifest | 기본은 출력만; `--apply` 시 loopback `_dev`/ads-rs primary에 validator/index 적용 |
| `apply_ads_public_schema` | manage.py → Command → load_public_manifest | 공개 추가5컬렉션만 출력/선택 로컬 적용; 자동 TTL·운영 정책값 없음 |
| `apply_ads_policy_schema` | Command → load_policy_manifest | 예산 상태/일일 집계 추가2컬렉션, 기본 출력·선택 로컬 strict 적용 |
| `refresh_ads_policy [--watch]` | Command → AdsBudgetService → MongoAdsPolicyRepository.run | 기본 한회; 명시 watch300초, 광고별 지표/최초 cutoff/서버 annotation 원자 갱신 |
| `check_ads_database` | manage.py → Command → local_client/require_primary | 로컬 primary와 세션/트랜잭션 읽기/종료 점검 |
| `check_ads_logs --limit N` | Command → inspect_logs → 광고 MongoDB | 환경별 신규/기존/누락 건수·제한 표본 hash 읽기 점검 |
| `check_ads_runtime --database` | Command → inspect_runtime → 스키마/로그 조회 | 설정/primary/validator/인덱스/내장 로그 점검. 자동 보정 없음 |
| `run_ads_workers [--watch]` | Command → AdsWorkerGroup → AdsBudgetService | 예산/통계300초·시작 상태·실패 재시도·SIGTERM/키보드 제한 종료 |
| `check_ads_retention --limit N` | Command → inspect_retention → 광고 MongoDB |90/365일 기산점/참조 제한 표본 읽기. 삭제/TTL 없음 |
| `run_ads_dev --port N` | Command → WSGI application → urlpatterns | DEBUG의 loopback 서버, 공통 migration은 별도 |
| `sandbox.py [--start-mongo] [--port N]` | sandbox settings → run_ads_sandbox → local guard/10컬렉션 적용·sandbox_runtime → WSGI | loopback 기본8001·시험DB만, 실행별 접근 코드/5분 worker·직접 시작한 MongoDB만 종료 |

광고 로그는 관리·측정·최초 소진 문서의 log_record에 업무와 원자 저장합니다. 외부 전달/ACK와 공통 PostgreSQL 로그 규격은 제거했습니다. 기존 log_relay는 원본 그대로 보존하며 최초 응답·판정·cutoff를 다시 쓰지 않습니다.

## Python 파일별 인계

후속 배치/점검은 `run_ads_workers`(기본 단발/명시 독립 반복)와 `check_ads_runtime`(기본 설정만/
선택 MongoDB 읽기)을 사용합니다. 자세한 실패/종료/검증 범위는
[광고 남은 작업·연결 계획](../development/ads/광고_남은_작업과_연결_계획.md)을 따릅니다.
공개 URL/이벤트/스키마/단가·보관 정책은 변경하지 않습니다.

| 원본 파일 | 1:1 문서 | 역할 |
|---|---|---|
| [ad-server/backend/domains/ads/management/commands/check_ads_runtime.py](../../ad-server/backend/domains/ads/management/commands/check_ads_runtime.py) | [문서](files/ad-server/backend/domains/ads/management/commands/check_ads_runtime.py.md) | 읽기 점검 명령 |
| [ad-server/backend/domains/ads/management/commands/run_ads_workers.py](../../ad-server/backend/domains/ads/management/commands/run_ads_workers.py) | [문서](files/ad-server/backend/domains/ads/management/commands/run_ads_workers.py.md) | 예산·세 로그 작업 실행 진입점 |
| [ad-server/backend/tests/test_ads_jobs.py](../../ad-server/backend/tests/test_ads_jobs.py) | [문서](files/ad-server/backend/tests/test_ads_jobs.py.md) | 작업 실패·재시도·독립 실행 단위 시험 |
| [ad-server/backend/tests/test_ads_runtime_check.py](../../ad-server/backend/tests/test_ads_runtime_check.py) | [문서](files/ad-server/backend/tests/test_ads_runtime_check.py.md) | 읽기 점검·비밀값·스키마 불일치 단위 시험 |
| [ad-server/backend/tests/test_ads_workers_mongo_integration.py](../../ad-server/backend/tests/test_ads_workers_mongo_integration.py) | [문서](files/ad-server/backend/tests/test_ads_workers_mongo_integration.py.md) | 격리 MongoDB의 점검·작업 복구 시험 |
| [ad-server/backend/workers/ads_jobs.py](../../ad-server/backend/workers/ads_jobs.py) | [문서](files/ad-server/backend/workers/ads_jobs.py.md) | 독립 배치·실패 격리·재시도와 종료 |
| [ad-server/backend/workers/ads_runtime_check.py](../../ad-server/backend/workers/ads_runtime_check.py) | [문서](files/ad-server/backend/workers/ads_runtime_check.py.md) | 읽기 전용 설정·스키마·로그 대기 점검 |
| [ad-server/backend/api/__init__.py](../../ad-server/backend/api/__init__.py) | [문서](files/ad-server/backend/api/__init__.py.md) | Python 패키지 경계; 업무 동작 없음 |
| [ad-server/backend/api/ads.py](../../ad-server/backend/api/ads.py) | [문서](files/ad-server/backend/api/ads.py.md) | 광고 HTTP 관리 API·공통 오류 |
| [ad-server/backend/api/ads_auth.py](../../ad-server/backend/api/ads_auth.py) | [문서](files/ad-server/backend/api/ads_auth.py.md) | 공유 ADMIN·권한·CSRF 어댑터 경계 |
| [ad-server/backend/api/ads_public.py](../../ad-server/backend/api/ads_public.py) | [문서](files/ad-server/backend/api/ads_public.py.md) | 공개 조회·측정·proof 이미지 HTTP 경계 |
| [ad-server/backend/api/ads_public_auth.py](../../ad-server/backend/api/ads_public_auth.py) | [문서](files/ad-server/backend/api/ads_public_auth.py.md) | 공유 guest·명시 운영 정책 provider |
| [ad-server/backend/api/ads_public_serializers.py](../../ad-server/backend/api/ads_public_serializers.py) | [문서](files/ad-server/backend/api/ads_public_serializers.py.md) | 공개 요청/응답 OpenAPI 형식 |
| [ad-server/backend/api/ads_sandbox.py](../../ad-server/backend/api/ads_sandbox.py) | [문서](files/ad-server/backend/api/ads_sandbox.py.md) | 임시 화면·loopback/로컬 로그인·CSRF·개발 문맥/상태 |
| [ad-server/backend/api/ads_serializers.py](../../ad-server/backend/api/ads_serializers.py) | [문서](files/ad-server/backend/api/ads_serializers.py.md) | OpenAPI 요청/응답 필드 |
| [ad-server/backend/api/health.py](../../ad-server/backend/api/health.py) | [문서](files/ad-server/backend/api/health.py.md) | DB 없는 프로세스 확인 |
| [ad-server/backend/config/__init__.py](../../ad-server/backend/config/__init__.py) | [문서](files/ad-server/backend/config/__init__.py.md) | Python 패키지 경계; 업무 동작 없음 |
| [ad-server/backend/config/sandbox_settings.py](../../ad-server/backend/config/sandbox_settings.py) | [문서](files/ad-server/backend/config/sandbox_settings.py.md) | 기존.env·공유DB와 분리한 시험 설정 |
| [ad-server/backend/config/sandbox_urls.py](../../ad-server/backend/config/sandbox_urls.py) | [문서](files/ad-server/backend/config/sandbox_urls.py.md) | 일반서버 미등록의 /dev/ads 경로/기존API 연결 |
| [ad-server/backend/config/settings.py](../../ad-server/backend/config/settings.py) | [문서](files/ad-server/backend/config/settings.py.md) | 환경·기본 runtime provider·외부 공유 어댑터 |
| [ad-server/backend/config/urls.py](../../ad-server/backend/config/urls.py) | [문서](files/ad-server/backend/config/urls.py.md) | health/광고 관리·공개 URL 등록 |
| [ad-server/backend/config/wsgi.py](../../ad-server/backend/config/wsgi.py) | [문서](files/ad-server/backend/config/wsgi.py.md) | WSGI 앱 로딩 |
| [ad-server/backend/domains/__init__.py](../../ad-server/backend/domains/__init__.py) | [문서](files/ad-server/backend/domains/__init__.py.md) | Python 패키지 경계; 업무 동작 없음 |
| [ad-server/backend/domains/ads/__init__.py](../../ad-server/backend/domains/ads/__init__.py) | [문서](files/ad-server/backend/domains/ads/__init__.py.md) | Python 패키지 경계; 업무 동작 없음 |
| [ad-server/backend/domains/ads/apps.py](../../ad-server/backend/domains/ads/apps.py) | [문서](files/ad-server/backend/domains/ads/apps.py.md) | Django 광고 앱 등록 |
| [ad-server/backend/domains/ads/budget_service.py](../../ad-server/backend/domains/ads/budget_service.py) | [문서](files/ad-server/backend/domains/ads/budget_service.py.md) | 5분 검증/통계·최초 cutoff·당시 예산 자격 |
| [ad-server/backend/domains/ads/delivery_policy.py](../../ad-server/backend/domains/ads/delivery_policy.py) | [문서](files/ad-server/backend/domains/ads/delivery_policy.py.md) | 표시/보고 마감 분리·명시 자정 cap·현재/과거 소재 자격 |
| [ad-server/backend/domains/ads/errors.py](../../ad-server/backend/domains/ads/errors.py) | [문서](files/ad-server/backend/domains/ads/errors.py.md) | 도메인 오류·HTTP 상태 |
| [ad-server/backend/domains/ads/management/__init__.py](../../ad-server/backend/domains/ads/management/__init__.py) | [문서](files/ad-server/backend/domains/ads/management/__init__.py.md) | Python 패키지 경계; 업무 동작 없음 |
| [ad-server/backend/domains/ads/management/commands/__init__.py](../../ad-server/backend/domains/ads/management/commands/__init__.py) | [문서](files/ad-server/backend/domains/ads/management/commands/__init__.py.md) | Python 패키지 경계; 업무 동작 없음 |
| [ad-server/backend/domains/ads/management/commands/apply_ads_policy_schema.py](../../ad-server/backend/domains/ads/management/commands/apply_ads_policy_schema.py) | [문서](files/ad-server/backend/domains/ads/management/commands/apply_ads_policy_schema.py.md) | 예산/집계2컬렉션 미리보기·선택 로컬 적용 |
| [ad-server/backend/domains/ads/management/commands/apply_ads_public_schema.py](../../ad-server/backend/domains/ads/management/commands/apply_ads_public_schema.py) | [문서](files/ad-server/backend/domains/ads/management/commands/apply_ads_public_schema.py.md) | 공개5컬렉션 미리보기·선택 로컬 적용 |
| [ad-server/backend/domains/ads/management/commands/apply_ads_schema.py](../../ad-server/backend/domains/ads/management/commands/apply_ads_schema.py) | [문서](files/ad-server/backend/domains/ads/management/commands/apply_ads_schema.py.md) | 스키마 미리보기·로컬 적용 |
| [ad-server/backend/domains/ads/management/commands/check_ads_database.py](../../ad-server/backend/domains/ads/management/commands/check_ads_database.py) | [문서](files/ad-server/backend/domains/ads/management/commands/check_ads_database.py.md) | 로컬 primary/트랜잭션 읽기 점검 |
| [ad-server/backend/domains/ads/management/commands/refresh_ads_policy.py](../../ad-server/backend/domains/ads/management/commands/refresh_ads_policy.py) | [문서](files/ad-server/backend/domains/ads/management/commands/refresh_ads_policy.py.md) | 한회/명시300초 반복의 예산 검증·집계 |
| [ad-server/backend/domains/ads/management/commands/run_ads_dev.py](../../ad-server/backend/domains/ads/management/commands/run_ads_dev.py) | [문서](files/ad-server/backend/domains/ads/management/commands/run_ads_dev.py.md) | loopback 광고 API 개발 서버 |
| [ad-server/backend/domains/ads/management/commands/run_ads_sandbox.py](../../ad-server/backend/domains/ads/management/commands/run_ads_sandbox.py) | [문서](files/ad-server/backend/domains/ads/management/commands/run_ads_sandbox.py.md) | 임시도구·로컬 스키마/프로세스 소유·기동/종료 |
| [ad-server/backend/domains/ads/measurement.py](../../ad-server/backend/domains/ads/measurement.py) | [문서](files/ad-server/backend/domains/ads/measurement.py.md) | 순수 최초 측정·재전송/반복·예상 토큰 |
| [ad-server/backend/domains/ads/mongo.py](../../ad-server/backend/domains/ads/mongo.py) | [문서](files/ad-server/backend/domains/ads/mongo.py.md) | 로컬 스키마 점검 연결 |
| [ad-server/backend/domains/ads/public_policy.py](../../ad-server/backend/domains/ads/public_policy.py) | [문서](files/ad-server/backend/domains/ads/public_policy.py.md) | 미정 수명·소재·예산의 명시 서버 정책 경계 |
| [ad-server/backend/domains/ads/public_schema.py](../../ad-server/backend/domains/ads/public_schema.py) | [문서](files/ad-server/backend/domains/ads/public_schema.py.md) | 공개 validator/index manifest 진입점 |
| [ad-server/backend/domains/ads/public_service.py](../../ad-server/backend/domains/ads/public_service.py) | [문서](files/ad-server/backend/domains/ads/public_service.py.md) | 공개 제공·측정·예상 항목 원자 저장 |
| [ad-server/backend/domains/ads/runtime_policy.py](../../ad-server/backend/domains/ads/runtime_policy.py) | [문서](files/ad-server/backend/domains/ads/runtime_policy.py.md) | 기본 공개 정책·저장된 검증/차단 상태 연결 |
| [ad-server/backend/domains/ads/sandbox_runtime.py](../../ad-server/backend/domains/ads/sandbox_runtime.py) | [문서](files/ad-server/backend/domains/ads/sandbox_runtime.py.md) | sandbox guard·5분 worker·수동갱신/실패 상태 |
| [ad-server/backend/domains/ads/selection.py](../../ad-server/backend/domains/ads/selection.py) | [문서](files/ad-server/backend/domains/ads/selection.py.md) | 순수 후보/priority/순환·표시 상한 |
| [ad-server/backend/domains/ads/service.py](../../ad-server/backend/domains/ads/service.py) | [문서](files/ad-server/backend/domains/ads/service.py.md) | 관리·선택 예산/버전·멱등/감사·자동 종료 조회 |
| [ad-server/backend/domains/ads/validation.py](../../ad-server/backend/domains/ads/validation.py) | [문서](files/ad-server/backend/domains/ads/validation.py.md) | strict 입력·시간·이미지·BSON 검증 |
| [ad-server/backend/manage.py](../../ad-server/backend/manage.py) | [문서](files/ad-server/backend/manage.py.md) | Django 명령 진입점 |
| [ad-server/backend/repositories/__init__.py](../../ad-server/backend/repositories/__init__.py) | [문서](files/ad-server/backend/repositories/__init__.py.md) | Python 패키지 경계; 업무 동작 없음 |
| [ad-server/backend/repositories/ads_mongo.py](../../ad-server/backend/repositories/ads_mongo.py) | [문서](files/ad-server/backend/repositories/ads_mongo.py.md) | 3컬렉션 트랜잭션·조건부 갱신/조회 |
| [ad-server/backend/repositories/ads_policy_mongo.py](../../ad-server/backend/repositories/ads_policy_mongo.py) | [문서](files/ad-server/backend/repositories/ads_policy_mongo.py.md) | 예산 revision CAS·원장별 집계·범위/지연 요약 |
| [ad-server/backend/repositories/ads_public_mongo.py](../../ad-server/backend/repositories/ads_public_mongo.py) | [문서](files/ad-server/backend/repositories/ads_public_mongo.py.md) | 공개5컬렉션·CAS·당시 자격·원자 경합 |
| [ad-server/backend/sandbox.py](../../ad-server/backend/sandbox.py) | [문서](files/ad-server/backend/sandbox.py.md) | 별도 sandbox 설정/개발 명령 진입점 |
| [ad-server/backend/tests/__init__.py](../../ad-server/backend/tests/__init__.py) | [문서](files/ad-server/backend/tests/__init__.py.md) | Python 패키지 경계; 업무 동작 없음 |
| [ad-server/backend/tests/policy_fixtures.py](../../ad-server/backend/tests/policy_fixtures.py) | [문서](files/ad-server/backend/tests/policy_fixtures.py.md) | 정책/지표 포함 메모리 원자 rollback fixture |
| [ad-server/backend/tests/public_fixtures.py](../../ad-server/backend/tests/public_fixtures.py) | [문서](files/ad-server/backend/tests/public_fixtures.py.md) | 메모리 원자 rollback·테스트 전용 정책 |
| [ad-server/backend/tests/test_ads_api.py](../../ad-server/backend/tests/test_ads_api.py) | [문서](files/ad-server/backend/tests/test_ads_api.py.md) | HTTP·인증·CSRF·미리보기·목록 검증 |
| [ad-server/backend/tests/test_ads_budget_service.py](../../ad-server/backend/tests/test_ads_budget_service.py) | [문서](files/ad-server/backend/tests/test_ads_budget_service.py.md) | 검증/과거 보고·최초 cutoff·증액/수동중단·rollback |
| [ad-server/backend/tests/test_ads_delivery_policy.py](../../ad-server/backend/tests/test_ads_delivery_policy.py) | [문서](files/ad-server/backend/tests/test_ads_delivery_policy.py.md) | 배달 마감·명시 자정 cap·소재 자격21개 검증 |
| [ad-server/backend/tests/test_ads_domain.py](../../ad-server/backend/tests/test_ads_domain.py) | [문서](files/ad-server/backend/tests/test_ads_domain.py.md) | 서비스·멱등·원본/감사 검증 |
| [ad-server/backend/tests/test_ads_measurement.py](../../ad-server/backend/tests/test_ads_measurement.py) | [문서](files/ad-server/backend/tests/test_ads_measurement.py.md) | 측정/시간/재전송·표시/보고 분리35개 검증 |
| [ad-server/backend/tests/test_ads_mongo_integration.py](../../ad-server/backend/tests/test_ads_mongo_integration.py) | [문서](files/ad-server/backend/tests/test_ads_mongo_integration.py.md) | 격리 DB의 실제 MongoDB 검증 |
| [ad-server/backend/tests/test_ads_policy_api.py](../../ad-server/backend/tests/test_ads_policy_api.py) | [문서](files/ad-server/backend/tests/test_ads_policy_api.py.md) | 정책 HTTP·예산 종료·주기 요약 연결 시험 |
| [ad-server/backend/tests/test_ads_policy_mongo_integration.py](../../ad-server/backend/tests/test_ads_policy_mongo_integration.py) | [문서](files/ad-server/backend/tests/test_ads_policy_mongo_integration.py.md) | 실제 정책 트랜잭션·경합·소진 로그/ENDED 페이지 |
| [ad-server/backend/tests/test_ads_policy_repository.py](../../ad-server/backend/tests/test_ads_policy_repository.py) | [문서](files/ad-server/backend/tests/test_ads_policy_repository.py.md) | 정책 driver·CAS·집계/schema 대역 검증 |
| [ad-server/backend/tests/test_ads_public_api.py](../../ad-server/backend/tests/test_ads_public_api.py) | [문서](files/ad-server/backend/tests/test_ads_public_api.py.md) | 공개 HTTP·CSRF·guest/proof·안전 오류 검증 |
| [ad-server/backend/tests/test_ads_public_mongo_integration.py](../../ad-server/backend/tests/test_ads_public_mongo_integration.py) | [문서](files/ad-server/backend/tests/test_ads_public_mongo_integration.py.md) | 격리 DB 실제 공개 트랜잭션·경합/relay 검증 |
| [ad-server/backend/tests/test_ads_public_repository.py](../../ad-server/backend/tests/test_ads_public_repository.py) | [문서](files/ad-server/backend/tests/test_ads_public_repository.py.md) | 공개 driver/session·CAS·스키마 대역 검증 |
| [ad-server/backend/tests/test_ads_public_service.py](../../ad-server/backend/tests/test_ads_public_service.py) | [문서](files/ad-server/backend/tests/test_ads_public_service.py.md) | 공개 서비스·최초 판정/원장·과거 자격 검증 |
| [ad-server/backend/tests/test_ads_repository.py](../../ad-server/backend/tests/test_ads_repository.py) | [문서](files/ad-server/backend/tests/test_ads_repository.py.md) | driver 대역·경합/트랜잭션 검증 |
| [ad-server/backend/tests/test_ads_runtime_policy.py](../../ad-server/backend/tests/test_ads_runtime_policy.py) | [문서](files/ad-server/backend/tests/test_ads_runtime_policy.py.md) | runtime 자격·배치/watch/relay 명령 대역 검증 |
| [ad-server/backend/tests/test_ads_sandbox.py](../../ad-server/backend/tests/test_ads_sandbox.py) | [문서](files/ad-server/backend/tests/test_ads_sandbox.py.md) | 임시 인증/CSRF·운영격리·시험측정 제외/worker·프로세스 소유 검증 |
| [ad-server/backend/tests/test_ads_selection.py](../../ad-server/backend/tests/test_ads_selection.py) | [문서](files/ad-server/backend/tests/test_ads_selection.py.md) | 선정/표시 상한·BSON Int64 priority 검증 |
| [ad-server/backend/tests/test_scaffold.py](../../ad-server/backend/tests/test_scaffold.py) | [문서](files/ad-server/backend/tests/test_scaffold.py.md) | health·미인증 관리 요청 차단 |

## 검증과 갱신

시그니처는 routing-doc-auditor의 구조화 AST 결과를 기준으로 기록합니다. 심볼은 보고서의 qualified name과 기본값·annotation을 그대로 기록합니다. 파일 추가·삭제·시그니처 변경 후 같은 검사기로 색인과 짝 문서를 갱신합니다. AST 일치 검사는 동작 테스트와 구분합니다.

일반 시험은 HTTP/도메인/driver/로그 대역으로 권한·형식·멱등·경합·원본·재전달을 검증합니다. 명시 실행형 MongoDB 시험은 관리/공개/정책 모듈이 loopback ads-rs의 격리 UUID _dev DB에서 실제 트랜잭션·validator·동시 요청을 검증합니다. 최신 실행 결과/명령/미실행 범위는 [광고 검증 기록](../acceptance/광고_개발_준비_검증.md)을 따릅니다. 이 색인의 시그니처 목록은 실행 통과 수치나 실제 공유 인증/브라우저/배포 검증을 대신하지 않습니다.

폴더 재배치를 커밋한 현재 검사 명령은 저장소 루트에서 `ad-server/backend/.venv/Scripts/python.exe C:/Users/이해나/.codex/skills/routing-doc-auditor/scripts/audit_routing.py --repo . --routing-dir docs/backend-routing --include-all --format json --output .cache/routing-sandbox.json`입니다. 이전 이동 단계의 임시 rename index helper를 더 이상 필요로 하지 않으며 실제 Git index를 변경하지 않습니다. 공통 guest/ADMIN·공개 배너의 가시성/3초 숨김·운영 장애 복구는 별도 확인합니다.

- [ad-server/backend/domains/ads/management/commands/check_ads_logs.py](files/ad-server/backend/domains/ads/management/commands/check_ads_logs.py.md)

- [ad-server/backend/tests/test_ads_logs.py](files/ad-server/backend/tests/test_ads_logs.py.md)

- [ad-server/backend/workers/ads_logs.py](files/ad-server/backend/workers/ads_logs.py.md)

- [ad-server/backend/domains/ads/management/commands/check_ads_retention.py](files/ad-server/backend/domains/ads/management/commands/check_ads_retention.py.md)

- [ad-server/backend/tests/test_ads_retention.py](files/ad-server/backend/tests/test_ads_retention.py.md)

- [ad-server/backend/tests/test_ads_worker_shutdown.py](files/ad-server/backend/tests/test_ads_worker_shutdown.py.md)

- [ad-server/backend/workers/ads_retention.py](files/ad-server/backend/workers/ads_retention.py.md)

## 2026-10-16 로컬 광고 프레젠테이션

`ad-server/backend/api/ads_sandbox.py`의 문구/허용 에셋 연결과 `ad-server/backend/tests/test_ads_sandbox.py`의 경계 검증을 갱신했습니다. 화면 파일 지도·수정/이식 절차는 [프레젠테이션 가이드](../development/ads/광고_로컬_화면과_프레젠테이션_수정_가이드.md)에 있습니다.
