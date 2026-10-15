# 광고 서버 — 첫 관리 단계

- 작성일: 2026-10-15
- 브랜치: `feature/ad-logic`
- 범위: 광고 로직·MongoDB 컬렉션 설계와 서버 개발 기반. 관리자 화면은 별도 담당자가 제작합니다.

Python 3.12.13, Django/DRF, PyMongo를 사용합니다. 실제 설치 버전은 `uv.lock`에
고정했습니다. Django는 PostgreSQL 공통 업무에, 별도 PyMongo 어댑터는 광고 MongoDB에
사용합니다. 이미지 업로드·광고 등록/수정/중단·목록/요약/미리보기와 감사·멱등·로그 relay를
구현했습니다. 공유 ADMIN 인증과 PostgreSQL 로그 sink는 담당자의 연결이 필요합니다.
공개 delivery·노출/클릭·토큰 집계는 후속 단계입니다.

## 준비와 실행

PowerShell에서 저장소의 `backend` 폴더로 이동합니다.

```powershell
uv sync --locked
if (-not (Test-Path -LiteralPath .env)) { Copy-Item -LiteralPath .env.example -Destination .env }
$env:PYTHONIOENCODING='utf-8'
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py run_ads_dev
```

`GET http://127.0.0.1:8000/api/health`는 프로세스만 확인하고
`database_checked=false`를 반환합니다. DEBUG에서 `/api/schema`로 구현된 health 명세를
확인할 수 있습니다. 관리 API는 매 요청 공유 ADMIN을 검증하며 미설정이면 503으로 차단합니다.
Django admin/관리 화면은 만들지 않았습니다. `run_ads_dev`는 loopback 개발 서버이며 운영 명령이 아닙니다.
일반 `runserver`는 공통 PostgreSQL 접속·migration 확인이 필요합니다.

실제 `.env`와 `.venv`는 Git 추적 대상이 아닙니다. `.env.example`의 비밀값은 로컬 예시이며,
공유 환경의 주소·계정·권한을 받기 전에는 공통 DB에 migration을 실행하지 않습니다.

## 폴더와 설계

| 경로 | 역할 |
|---|---|
| `config/` | Django settings·URL·WSGI |
| `api/` | 관리 API·공유 인증 어댑터·요청/응답 명세·health |
| `domains/ads/` | strict 입력·이미지 검증·관리 서비스·개발 명령 |
| `domains/ads/schemas/management_manifest.json` | 세 관리 컬렉션 BSON validator·인덱스 |
| `repositories/` | MongoDB 트랜잭션·version 조건 갱신·목록/요약 |
| `workers/` | PostgreSQL sink로 전달하는 로그 relay |
| `tests/` | 개발 기반 검증 |

MongoDB에서는 `ads`, `ad_assets`, `ad_admin_changes` 세 컬렉션을 먼저 사용합니다.
원본 이미지는 Binary, 계정·세션 원본은 공유 환경 참조입니다. 3차 업종 태그는 제외합니다.

스키마는 unknown 필드·기본 BSON 타입·기간·고유키를 검사하며, 서비스는 논리 참조·이미지
디코딩/실제 바이트 크기·version·불변 snapshot·멱등을 검사합니다. 서로를 대체하지 않습니다.
Mongo schema와 API/OpenAPI의 JSON 형식은 구분합니다. 실제 MongoDB 8.0.34 통합 검증 결과는
아래 검증 문서에 있습니다.

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
```

`ADS_API_CONTRACT_VERSION`은 공통 담당자 확인 후 설정하며 지정한 값만 X-Contract-Version으로
반환합니다. 기존 피드백 이벤트 버전 불일치를 이 광고 구현에서 자동 통합하지 않습니다.
새 계정/로그 테이블, 공개 이미지 URL·재개·삭제·업종 태그·예산 정책은 추가하지 않았습니다.

구현된 HTTP 경로와 파일/기획 연결은 [라우팅 색인](../docs/backend-routing/README.md)을 따릅니다.
새 `GET /api/admin/ad-assets/{asset_id}`는 인증된 관리 미리보기 이미지 조회용 기술 경로이며,
공개 이미지 URL 정책을 확정하는 경로가 아닙니다. 목록 JSON에는 원본 바이트를 넣지 않습니다.

- [광고 데이터·로직 설계](../docs/development/ads/광고_데이터와_로직_설계.md)
- [실행·설정·팀 브랜치 인계](../docs/runbook/광고_서버_개발_준비.md)
- [실제 확인 결과](../docs/acceptance/광고_개발_준비_검증.md)
- [코드별 인계 문서](../docs/backend-routing/README.md)

기술 호환성 근거는 [Django 5.2 공식 릴리스 노트](https://docs.djangoproject.com/en/5.2/releases/5.2/),
[DRF 릴리스 노트](https://www.django-rest-framework.org/community/release-notes/),
[PyMongo 트랜잭션 가이드](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/crud/transactions/)입니다.
