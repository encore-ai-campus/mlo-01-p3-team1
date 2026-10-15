# 광고 서버 — 관리·공개 API와 MongoDB 원자 저장

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- 브랜치: `feature/ad-logic`
- 범위: 광고 로직·MongoDB 컬렉션 설계와 서버 개발 기반. 관리자 화면은 별도 담당자가 제작합니다.

Python 3.12.13, Django/DRF, PyMongo를 사용합니다. 실제 설치 버전은 `uv.lock`에
고정했습니다. Django는 PostgreSQL 공통 업무에, 별도 PyMongo 어댑터는 광고 MongoDB에
사용합니다. 이미지 업로드·광고 등록/수정/중단·목록/요약/미리보기와 감사·멱등·로그 relay를
구현했습니다. 공유 ADMIN 인증과 PostgreSQL 로그 sink는 담당자의 연결이 필요합니다.
공개 delivery 발급/재확인·이미지 제공·노출/클릭 판정과 예상 토큰 원장도 연결했습니다.
5분 원장 예산 검증·주기 통계와 최초 소진 로그 코드를 연결했습니다. 상시 watch와 실제 공유/운영 연결은 후속 검증입니다.

선정·표시 상한·측정 판정의 순수 규칙과 공개 서비스·HTTP·MongoDB 어댑터를 분리했습니다.
서버 입력·원자 저장과 운영 연결 경계는
[공개 선정·측정 인계](../../docs/development/ads/공개_선정과_측정_로직_인계.md)를 따릅니다.
운영 guest·정책·서명·공개 주소가 미설정이면 503으로 차단하며 테스트 fixture로 대체하지 않습니다.

## 준비와 실행

PowerShell에서 저장소의 `ad-server/backend` 폴더로 이동합니다.

```powershell
uv sync --locked
if (-not (Test-Path -LiteralPath .env)) { Copy-Item -LiteralPath .env.example -Destination .env }
$env:PYTHONIOENCODING='utf-8'
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py run_ads_dev
```

`GET http://127.0.0.1:8000/api/health`는 프로세스만 확인하고
`database_checked=false`를 반환합니다. DEBUG에서 `/api/schema`로 구현된 HTTP 명세를
확인할 수 있습니다. 관리 API는 매 요청 공유 ADMIN을 검증하며 미설정이면 503으로 차단합니다.
Django admin/관리 화면은 만들지 않았습니다. `run_ads_dev`는 loopback 개발 서버이며 운영 명령이 아닙니다.
일반 `runserver`는 공통 PostgreSQL 접속·migration 확인이 필요합니다.

실제 `.env`와 `.venv`는 Git 추적 대상이 아닙니다. `.env.example`의 비밀값은 로컬 예시이며,
공유 환경의 주소·계정·권한을 받기 전에는 공통 DB에 migration을 실행하지 않습니다.

## 폴더와 설계

| 경로 | 역할 |
|---|---|
| `config/` | Django settings·URL·WSGI |
| `api/` | 관리/공개 API·공유 ADMIN/guest 어댑터·요청/응답 명세·health |
| `domains/ads/` | strict 입력·이미지 검증·관리/공개 서비스·운영 정책 연결·개발 명령 |
| `domains/ads/selection.py`, `measurement.py` | 순수 공개 선정·표시 상한·최초 측정/반복·예상 토큰 규칙 |
| `domains/ads/schemas/management_manifest.json` | 세 관리 컬렉션 BSON validator·인덱스 |
| `domains/ads/schemas/public_manifest.json` | 다섯 공개 컬렉션 BSON validator·고유키/CAS 조회 인덱스 |
| `domains/ads/schemas/policy_manifest.json` | 정책2컬렉션·예산 버전별 소진/일별 통계 validator·인덱스 |
| `repositories/` | MongoDB 업무 트랜잭션·광고 잠금·배달/이벤트 멱등·커서/claim/반복 창 CAS |
| `workers/` | PostgreSQL sink로 전달하는 로그 relay |
| `tests/` | 개발 기반 검증 |

MongoDB의 관리 상태는 `ads`, `ad_assets`, `ad_admin_changes` 세 컬렉션입니다. 공개 상태는
`ad_rotation_state`, `ad_deliveries`, `ad_events`, `ad_repeat_windows`, `ad_estimated_usage_ledger`입니다.
정책 상태 `ad_budget_states`, `ad_daily_metrics`를 더해 합계10개입니다. claim은 delivery 내부, 관리/측정/소진 로그는 각 문서 내부이며 별도 사용자·claim/outbox/ad_versions 컬렉션은 없습니다.
원본 이미지는 Binary, 계정·세션 원본은 공유 환경 참조입니다. 3차 업종 태그는 제외합니다.

스키마는 unknown 필드·기본 BSON 타입·기간·고유키를 검사하며, 서비스는 논리 참조·이미지
디코딩/실제 바이트 크기·version·불변 snapshot·멱등을 검사합니다. 서로를 대체하지 않습니다.
Mongo schema와 API/OpenAPI의 JSON 형식은 구분합니다. 실제 MongoDB 8.0.34 통합 검증 결과는
아래 검증 문서에 있습니다.

```powershell
# 정의만 확인하며 DB를 바꾸지 않습니다.
.\.venv\Scripts\python.exe manage.py apply_ads_schema
.\.venv\Scripts\python.exe manage.py apply_ads_public_schema
.\.venv\Scripts\python.exe manage.py apply_ads_policy_schema
```

`--apply`는 loopback의 `_dev` DB에만 허용합니다. 관리·공개·정책 manifest는 별도 적용하며
자동 TTL 삭제·운영 DB migration을 실행하지 않습니다. 선택 실행형 실제 MongoDB 시험과 일반
서비스/API 시험의 실행 여부·결과는 검증 기록을 따릅니다.

## 공개 API와 운영 정책 연결

| 경로 | 계약 |
|---|---|
| `GET /api/ads` | placement 필수; 새 delivery 또는 delivery_id와 `X-Ad-Delivery-Token`으로 재확인; 신규 요청의 선택 `Idempotency-Key` |
| `POST /api/ad-events` | event_id·delivery_id·event_type·occurred_at 네 본문 필드와 `X-Ad-Delivery-Token` |
| `GET /api/ad-deliveries/{delivery_id}/image` | delivery_token query로 proof와 현재 게시 자격을 확인한 원본 이미지 |

공개 조회·측정은 `ADS_GUEST_CONTEXT_PROVIDER`의 `(django_request, bootstrap=bool)` 호출로
`api.ads_public_auth.PublicGuestContext`를 받습니다. 최초 상단 조회는 광고가 없어도 bootstrap을
요청하며, 하단·측정은 공유 문맥을 이어받습니다. 쿠키 저장 불가 문맥은 owner=null·측정 불가로
표시할 수 있으나 운영 집계에는 포함하지 않습니다. 광고 코드가 공유 쿠키 원본을 만들거나 저장하지 않습니다.

`ADS_PUBLIC_POLICY_PROVIDER`는 인자 없이 `domains.ads.public_policy.AdsPublicPolicy`를 반환합니다.
필수값은 정책 version·명시한 양수 delivery_ttl_seconds와 세 callback입니다.

- `budget_eligible(repository, ad, now)` → 명시 bool
- `open_delivery_eligible(delivery, current_ad, now)` → 명시 bool
- `occurrence_eligible(delivery, historical_ad, occurred_at)` → 명시 bool

정책 callback은 MongoDB 트랜잭션 안에서 재실행될 수 있으므로 외부 API·PostgreSQL·파일·네트워크
I/O를 수행하지 않습니다. 순수 계산 또는 같은 광고 저장소 읽기로 자격을 판정합니다.
`ADS_DELIVERY_SIGNING_KEY`와 절대 HTTPS `ADS_PUBLIC_BASE_URL`도 필수입니다.
guest 연결 실패는 `GUEST_UNAVAILABLE`/503, 정책/서명/주소 미설정이나 잘못된 정책 판정은
`ADS_POLICY_UNAVAILABLE`/503입니다. 이미지 읽기는 guest 발급 없이 proof와 운영 정책을 검사합니다.

`ADS_PUBLIC_POLICY_PROVIDER=domains.ads.runtime_policy.get_public_policy`를 명시 연결합니다. `.env.example`에 경로를 적었으며 실제 `.env`/공유 연결은 별도입니다. provider는1800초·split_deadlines=True·check_budget_history=True·cap_at_midnight=False를 사용합니다. 신규 배달은 표시30분/광고 종료와 보고+300초를 나누고 예산 정책 marker를 서명합니다. 기존 배달/원응답은 늘리거나 소급 변경하지 않습니다. 소재 수정은 옛 배달 새 표시/이후 발생을 막고 이전 유효 보고는300초 내 검사합니다.

예산/통계는 모두5분입니다. 일일/전체 소진 확인 최초 cutoff부터 신규/재확인/이미지를 차단하고 occurred_at < cutoff 유효 보고는300초 내 초과 인정합니다. 최소 잔여23/20·예약은 없습니다. 자동 종료는 소진/게시 기간이고 수동 paused는 유지합니다. 예산 pair는 관리API에 입력하는 양의 int64이며 미설정은 운영 부적격, 금액 기본값은 없습니다. 새 budget_version은 값 실제 변경에만 만들고 새 검증 뒤 재제공합니다. KST 발생일은 개발 기준이며 자정 배달 단축은 기본 False입니다.

상태 누락은 부적격,300초 초과 stale/future/형식 오류는503 기술 장애입니다. 테스트900초·제목/priority 상세·asset7일은 운영값으로 승격하지 않습니다.

새 delivery는 광고 문서의 실제 쓰기 잠금·위치별 순환·배달을 한 트랜잭션으로 저장합니다.
재확인은 같은 배달을 유지하고 현재 종료 단축도 표시 기한에 반영합니다. 측정은 최초 판정·내장
claim·반복 창·인정 시 예상 원장·내장 PENDING 로그를 함께 커밋하며, 재전송은 최초 응답을 보존합니다.
summary는 오늘, 목록 행 measurement는 보존 범위 누적입니다. as_of·aggregation_status·coverage·coverage_from/coverage_through·is_stale를 표시하고 미연결 null/PENDING과 실제0을 구분합니다.

## 공통 환경 연결과 실행 경계

`ADS_ADMIN_AUTHORIZER`는 서버 callable의 import 경로입니다. `(django_request, action)`을 받아
공유 환경의 현재 세션·활성·ADMIN·광고 권한을 확인한 `api.ads_auth.AdminIdentity`를 반환합니다.
`action`은 read/write 연결 구분이며 실제 공통 DB의 권한 codename을 새로 정의하지 않습니다.
미로그인은 None, 장애는 예외로 처리합니다. 클라이언트 역할·ID 헤더를 인증 근거로 쓰지 않습니다.
상태 변경에는 원본 Django request로 Origin/CSRF를 먼저 검사합니다.

`ADS_LOG_SINK`는 `(log_event_id, payload, payload_hash)`를 받는 서버 callable입니다.
공통 PostgreSQL에서 unique ID 저장 커밋 또는 기존 동일 payload 확인 뒤 **True**를 반환해야 합니다.
설정이 없으면 claim 전에 차단하고, 전달 실패는 MongoDB PENDING으로 남깁니다.

```powershell
.\.venv\Scripts\python.exe manage.py relay_ads_logs --limit 20
.\.venv\Scripts\python.exe manage.py relay_ads_event_logs --limit 20
.\.venv\Scripts\python.exe manage.py relay_ads_budget_logs --limit 20
# 기본 1회 검증·통계 재계산
.\.venv\Scripts\python.exe manage.py refresh_ads_policy
# 상시 실행이 필요할 때: 300초 시작 간격, Ctrl+C 종료
.\.venv\Scripts\python.exe manage.py refresh_ads_policy --watch
```

`ADS_API_CONTRACT_VERSION`은 공통 담당자 확인 후 설정하며 지정한 값만 X-Contract-Version으로
반환합니다. 기존 피드백 이벤트 버전 불일치를 이 광고 구현에서 자동 통합하지 않습니다.
관리·측정·소진 relay는 MongoDB 문서의 PENDING 로그를 각각 처리하며 PostgreSQL 실제 연결 완료를 뜻하지 않습니다. 실제 watch·공유 guest·PostgreSQL·AWS·브라우저/복구도 미실행입니다.
새 계정/로그 테이블·재개·삭제·업종 태그·예산 운영값은 추가하지 않았습니다.

구현된 HTTP 경로와 파일/기획 연결은 [라우팅 색인](../../docs/backend-routing/README.md)을 따릅니다.
새 `GET /api/admin/ad-assets/{asset_id}`는 인증된 관리 미리보기 이미지 조회용 기술 경로이며,
공개 이미지 URL 정책을 확정하는 경로가 아닙니다. 목록 JSON에는 원본 바이트를 넣지 않습니다.

- [광고 데이터·로직 설계](../../docs/development/ads/광고_데이터와_로직_설계.md)
- [실행·설정·팀 브랜치 인계](../../docs/runbook/광고_서버_개발_준비.md)
- [실제 확인 결과](../../docs/acceptance/광고_개발_준비_검증.md)
- [코드별 인계 문서](../../docs/backend-routing/README.md)

기술 호환성 근거는 [Django 5.2 공식 릴리스 노트](https://docs.djangoproject.com/en/5.2/releases/5.2/),
[DRF 릴리스 노트](https://www.django-rest-framework.org/community/release-notes/),
[PyMongo 트랜잭션 가이드](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/crud/transactions/)입니다.
