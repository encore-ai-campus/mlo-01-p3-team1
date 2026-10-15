# 광고 백엔드 코드 인계 색인

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- 대상: 첫 광고 관리 단계의 서버 코드와 로컬 검증 도구. Python 파일별 문서는 AST 시그니처와 대조합니다.
- 상세 설계: [광고 데이터와 로직](../development/ads/광고_데이터와_로직_설계.md)
- 실행: [광고 서버 개발 준비](../runbook/광고_서버_개발_준비.md)

광고 이미지 업로드·읽기, 광고 목록·등록·전체 수정·중단·저장 전 미리보기·상태 개수 조회와 MongoDB 3컬렉션의 감사/멱등/pending 로그를 구현했습니다. 관리자 화면·프런트 라우팅, 공개 delivery·노출/클릭 수집·예산/사용량 통계는 구현하지 않았습니다. 공유 ADMIN 어댑터와 공통 PostgreSQL 로그 sink는 해당 담당자의 서버 연결이 필요하며 미설정일 때 각각 관리 요청/로그 전달을 차단합니다.

## 적용 계약과 코드 경계

[ADS01 화면/API/측정](../handoff/ads/01_광고_화면_API와_측정_계약.md), [ADS05 최신 간소화 통합](../handoff/ads/05_광고_간소화_통합과_추가_인계.md), [공통 개발 계약](../product/3차_공통_개발_계약과_검증_기준.md), [공통 API/이벤트 JSON](../contracts/3차_공통_API_이벤트.schema.json)을 연결합니다. 3차는 카페 전용이며 업종/태그 입력을 거절합니다. 이미지/광고는 MongoDB, 사용자·세션 원본은 공유 환경, 공통 로그는 PostgreSQL sink 계약으로 구분합니다. 광고 예산/보관 기한 등 미정 운영값을 이 코드 문서에서 새로 확정하지 않습니다.

HTTP 오류는 `api/ads.py:error_response`에서 code/message/request_id 및 필요한 details.fields로 반환합니다. OpenAPI에도 ErrorResponseSerializer의 400/401/403/404/409/422/503 응답을 연결하고 저장 변경 요청의 Idempotency-Key 헤더를 명시합니다. 요청 컴포넌트는 추가 필드 불허와 multipart binary를 표시하며 x-shared-admin-required 마커로 공유 ADMIN 경계를 표시합니다. 미정 공통 쿠키 이름이나 인증 발급 프로토콜은 추가하지 않습니다. 실제 strict 입력은 validation.py, 권한/CSRF는 ads_auth.py, 멱등/version/감사는 service.py, 저장 원자성은 ads_mongo.py가 담당합니다. 인증 미설정은 AUTH_UNAVAILABLE(503), sink 미설정은 LOG_SINK_UNAVAILABLE로 전달을 차단합니다. 새 인증/계정/로그 원본을 광고 도메인에서 만들지 않습니다.

## 실제 API 연결

아래 경로는 [config/urls.py](../../backend/config/urls.py)의 실제 등록과 구현 메서드에 대응합니다. 광고 관리 URL은 모두 공통 ADMIN·광고 권한을 확인합니다. POST/PUT은 세션 CSRF도 확인하며 저장 변경 요청에는 Idempotency-Key가 필요합니다. 저장 전 미리보기 POST는 읽기 권한을 사용하고 저장·배달·측정을 만들지 않습니다.

| 메서드·경로 | 구현 view | 실행 연결/결과 |
|---|---|---|
| `GET /api/health` | `HealthView.get` | 프로세스 응답만 확인, DB 미조회 |
| `GET /api/admin/ads` | `AdsCollectionView.get` | query_filters → repository.list_ads → serialize_ad, 서명 커서 |
| `POST /api/admin/ads` | `AdsCollectionView.post` | AdsService.create_ad → repository.run, 광고+감사 원자 기록 |
| `PUT /api/admin/ads/<ad_id>` | `AdUpdateView.put` | AdsService.update_ad → 멱등 재생/version 조건부 갱신 |
| `POST /api/admin/ads/<ad_id>/stop` | `AdStopView.post` | AdsService.stop_ad → paused/중단 감사 기록 |
| `POST /api/admin/ad-assets` | `AdAssetUploadView.post` | AdsService.upload_asset → 이미지 Binary+감사 원자 기록 |
| `GET /api/admin/ad-assets/<asset_id>` | `AdAssetReadView.get` | verified_asset → 원본/metadata 무결성 확인 → FileResponse |
| `POST /api/admin/ads/preview` | `AdPreviewView.post` | validate_ad_input/verified_asset → 미리보기 자료, operational_delivery=false |
| `GET /api/admin/ads/summary` | `AdsSummaryView.get` | repository.summary → 실제 상태 개수, 측정 null/연동 대기 |
| `GET /api/schema` (DEBUG) | `SpectacularAPIView` | 등록된 view의 OpenAPI schema |

관리자 프런트엔드 페이지와 `/admin/ads` 화면은 이 구현에 없습니다. 통계의 null/연동 대기는 0건/토큰 0을 의미하지 않습니다. 중단의 3초 공개 배너 제거는 공개 배달 연결 단계에서 별도로 검증해야 합니다.

## 저장·로그 실행 연결

| 시작점 | 연결 | 완료/실패 경계 |
|---|---|---|
| 광고 관리 HTTP 요청 | AdsAdminView → authorize_admin → validation/AdsService → MongoAdsRepository.run | 공통 신원/CSRF 확인 후 변경+감사/멱등/pending 로그를 한 MongoDB 트랜잭션으로 커밋 |
| 광고/이미지 목록·읽기 | view → MongoAdsRepository._read | primary/is_test 범위, 실제 상태 계산·원본 검증 |
| `apply_ads_schema` | manage.py → Command → load_manifest | 기본은 출력만; `--apply` 시 loopback `_dev`/ads-rs primary에 validator/index 적용 |
| `check_ads_database` | manage.py → Command → local_client/require_primary | 로컬 primary와 세션/트랜잭션 읽기/종료 점검 |
| `relay_ads_logs --limit N` | Command → run_configured_relay → get_log_sink → AdsLogRelay.run_once | sink 미설정은 claim 전 차단; 한 batch, durable sink ack 후 SENT |
| `run_ads_dev --port N` | Command → WSGI application → urlpatterns | DEBUG의 loopback 서버, 공통 migration은 별도 |

로그는 MongoDB 감사 기록의 불변 payload를 같은 event ID/hash로 전달합니다. sink의 durable commit 또는 동일 payload 확인 후에만 SENT가 됩니다. sink 실패·MongoDB ack 실패는 원본/응답/payload를 보존해 재시도하며 MongoDB와 PostgreSQL의 단일 트랜잭션을 가정하지 않습니다.

## Python 파일별 인계

| 원본 파일 | 1:1 문서 | 역할 |
|---|---|---|
| [backend/api/__init__.py](../../backend/api/__init__.py) | [문서](files/backend/api/__init__.py.md) | Python 패키지 경계; 업무 동작 없음 |
| [backend/api/ads.py](../../backend/api/ads.py) | [문서](files/backend/api/ads.py.md) | 광고 HTTP 관리 API·공통 오류 |
| [backend/api/ads_auth.py](../../backend/api/ads_auth.py) | [문서](files/backend/api/ads_auth.py.md) | 공유 ADMIN·권한·CSRF 어댑터 경계 |
| [backend/api/ads_serializers.py](../../backend/api/ads_serializers.py) | [문서](files/backend/api/ads_serializers.py.md) | OpenAPI 요청/응답 필드 |
| [backend/api/health.py](../../backend/api/health.py) | [문서](files/backend/api/health.py.md) | DB 없는 프로세스 확인 |
| [backend/config/__init__.py](../../backend/config/__init__.py) | [문서](files/backend/config/__init__.py.md) | Python 패키지 경계; 업무 동작 없음 |
| [backend/config/settings.py](../../backend/config/settings.py) | [문서](files/backend/config/settings.py.md) | 환경·저장소·공유 어댑터 설정 |
| [backend/config/urls.py](../../backend/config/urls.py) | [문서](files/backend/config/urls.py.md) | health/광고 관리 URL 등록 |
| [backend/config/wsgi.py](../../backend/config/wsgi.py) | [문서](files/backend/config/wsgi.py.md) | WSGI 앱 로딩 |
| [backend/domains/__init__.py](../../backend/domains/__init__.py) | [문서](files/backend/domains/__init__.py.md) | Python 패키지 경계; 업무 동작 없음 |
| [backend/domains/ads/__init__.py](../../backend/domains/ads/__init__.py) | [문서](files/backend/domains/ads/__init__.py.md) | Python 패키지 경계; 업무 동작 없음 |
| [backend/domains/ads/apps.py](../../backend/domains/ads/apps.py) | [문서](files/backend/domains/ads/apps.py.md) | Django 광고 앱 등록 |
| [backend/domains/ads/errors.py](../../backend/domains/ads/errors.py) | [문서](files/backend/domains/ads/errors.py.md) | 도메인 오류·HTTP 상태 |
| [backend/domains/ads/management/__init__.py](../../backend/domains/ads/management/__init__.py) | [문서](files/backend/domains/ads/management/__init__.py.md) | Python 패키지 경계; 업무 동작 없음 |
| [backend/domains/ads/management/commands/__init__.py](../../backend/domains/ads/management/commands/__init__.py) | [문서](files/backend/domains/ads/management/commands/__init__.py.md) | Python 패키지 경계; 업무 동작 없음 |
| [backend/domains/ads/management/commands/apply_ads_schema.py](../../backend/domains/ads/management/commands/apply_ads_schema.py) | [문서](files/backend/domains/ads/management/commands/apply_ads_schema.py.md) | 스키마 미리보기·로컬 적용 |
| [backend/domains/ads/management/commands/check_ads_database.py](../../backend/domains/ads/management/commands/check_ads_database.py) | [문서](files/backend/domains/ads/management/commands/check_ads_database.py.md) | 로컬 primary/트랜잭션 읽기 점검 |
| [backend/domains/ads/management/commands/relay_ads_logs.py](../../backend/domains/ads/management/commands/relay_ads_logs.py) | [문서](files/backend/domains/ads/management/commands/relay_ads_logs.py.md) | 공통 로그 sink로 한 batch 전달 |
| [backend/domains/ads/management/commands/run_ads_dev.py](../../backend/domains/ads/management/commands/run_ads_dev.py) | [문서](files/backend/domains/ads/management/commands/run_ads_dev.py.md) | loopback 광고 API 개발 서버 |
| [backend/domains/ads/mongo.py](../../backend/domains/ads/mongo.py) | [문서](files/backend/domains/ads/mongo.py.md) | 로컬 스키마 점검 연결 |
| [backend/domains/ads/service.py](../../backend/domains/ads/service.py) | [문서](files/backend/domains/ads/service.py.md) | 관리 변경·멱등·감사/pending 로그 |
| [backend/domains/ads/validation.py](../../backend/domains/ads/validation.py) | [문서](files/backend/domains/ads/validation.py.md) | strict 입력·시간·이미지·BSON 검증 |
| [backend/manage.py](../../backend/manage.py) | [문서](files/backend/manage.py.md) | Django 명령 진입점 |
| [backend/repositories/__init__.py](../../backend/repositories/__init__.py) | [문서](files/backend/repositories/__init__.py.md) | Python 패키지 경계; 업무 동작 없음 |
| [backend/repositories/ads_mongo.py](../../backend/repositories/ads_mongo.py) | [문서](files/backend/repositories/ads_mongo.py.md) | 3컬렉션 트랜잭션·조건부 갱신/조회 |
| [backend/tests/__init__.py](../../backend/tests/__init__.py) | [문서](files/backend/tests/__init__.py.md) | Python 패키지 경계; 업무 동작 없음 |
| [backend/tests/test_ads_api.py](../../backend/tests/test_ads_api.py) | [문서](files/backend/tests/test_ads_api.py.md) | HTTP·인증·CSRF·미리보기·목록 검증 |
| [backend/tests/test_ads_domain.py](../../backend/tests/test_ads_domain.py) | [문서](files/backend/tests/test_ads_domain.py.md) | 서비스·멱등·원본/감사 검증 |
| [backend/tests/test_ads_log_relay.py](../../backend/tests/test_ads_log_relay.py) | [문서](files/backend/tests/test_ads_log_relay.py.md) | claim·sink ack·재전달 검증 |
| [backend/tests/test_ads_mongo_integration.py](../../backend/tests/test_ads_mongo_integration.py) | [문서](files/backend/tests/test_ads_mongo_integration.py.md) | 격리 DB의 실제 MongoDB 검증 |
| [backend/tests/test_ads_repository.py](../../backend/tests/test_ads_repository.py) | [문서](files/backend/tests/test_ads_repository.py.md) | driver 대역·경합/트랜잭션 검증 |
| [backend/tests/test_scaffold.py](../../backend/tests/test_scaffold.py) | [문서](files/backend/tests/test_scaffold.py.md) | health·미인증 관리 요청 차단 |
| [backend/workers/ads_log_relay.py](../../backend/workers/ads_log_relay.py) | [문서](files/backend/workers/ads_log_relay.py.md) | pending claim/전달/재시도 |

## 검증과 갱신

시그니처는 routing-doc-auditor의 구조화 AST 결과를 기준으로 기록합니다. 중첩 commit/fixture/test helper도 보고서의 qualified name 그대로 포함합니다. 파일 추가·삭제·시그니처 변경 후 같은 검사기로 색인과 짝 문서를 갱신합니다. AST 일치 검사는 동작 테스트와 구분합니다.

일반 테스트는 HTTP/도메인/driver/로그 대역으로 권한·형식·멱등·경합·원본·재전달을 검증합니다. `test_ads_mongo_integration.py`는 명시 플래그로 격리 로컬 DB에서 실제 트랜잭션/validator/동시 요청을 검증합니다. 공통 ADMIN·실제 PostgreSQL sink·공개 배너 연결·운영 장애 복구는 후속 담당과 별도 확인합니다.
