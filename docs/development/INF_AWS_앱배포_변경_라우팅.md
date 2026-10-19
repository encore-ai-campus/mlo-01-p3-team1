# INF AWS 앱 배포 변경 라우팅

- 작성일: 2026-10-16
- 수정일: 2026-10-17
- 담당: INF, 사용자 승인에 따른 AWS 연결 준비 및 호환성 보완
- 범위: D-03, I-01~04, Q-03의 앱 실행/접속 준비와 사용자 확인에 따른 초기 검수 승인·카탈로그 발행. 추천 정책·검수 기준 변경 없음.
- 앱 작업 위치: `<앱 develop 체크아웃>`, `develop`
- 기준 커밋: `e2b7d62a2161856714b14de8f56ca32611886969`
- 실제 인프라 운영 위치: `<기반 인프라 feature/infra 체크아웃>`, `feature/infra`, 설치 코드 `aws-infra/VERSION=0.3.19`
- 앱 checkout에 포함된 기반 설치 코드는 `0.3.2`다. 이번 작업은 현재 설치 세대를 연결하며, 해당 오래된 기반 설치기로 AWS 생성/삭제를 다시 실행하지 않는다. 기반 설치 코드의 별도 동기화는 남은 인계다.
- 최초 배포 당시에는 커밋/푸시/PR 생성을 수행하지 않았다. 2026-10-17 사용자 요청에 따른 공개·브랜치 반영 범위는 [배포 코드 공개 라우팅](./INF_배포코드_공개_변경_라우팅.md)을 따른다.

## 기준 → 실제 흐름 → 실행 근거

| 기준과 확인 버전 | 실제 코드와 연결 | 이번 적용·검증 |
|---|---|---|
| 기준 커밋의 `docs/handoff/infra/` 수령 문서와 기존 운영 저장소의 최신 AWS 인계 | 서울 5계정·5VPC·14EC2·3물리 AZ. 기존 EC2에 systemd로 설치 | 새 EC2/VPC 없음. 앱 통신용 ingress 변경 세트 2개와 CloudFront 배포 1개/함수 1개 추가 |
| 기준 커밋의 서비스 기능/사용자 흐름, 구현 설계도, 컬럼 기반 추천 로직 가이드, 구현 태스크 | 실제 공통 API는 `backend/cafe/asgi.py`의 Django 6.1.2, 광고 API는 `ad-server/backend/config/wsgi.py`의 Django 5.2.18 | 사용자 지시대로 실제 소스와 호출 관계를 우선. 두 앱의 가상환경 분리. 수령 문서의 FastAPI 표현은 수정하지 않음 |
| 기준 커밋의 `docs/handoff/music/` CSV와 분류 규격 | CSV → `import_music_catalog_source` → PostgreSQL Track/Review/TrackOrigin → 검수 → Catalog 발행 → 추천 작업자 | CSV 원본 SHA-256 고정, 오류 1행 격리 허용을 명시. 초안 적재와 승인·발행을 구분. CSV를 요청마다 직접 읽는 운영 구조가 아님 |
| 사용자 결정: 음악 원본 S3는 대기 | `backend/common/music_archive.py`, `check_runtime.py` | `MUSIC_S3_ARCHIVE_DEFERRED=1`일 때 지정한 절대 로컬 원본 경로의 파일·해시를 확인하고 `S3_DEFERRED`로 기록. 기본값은 0. 다른 DB/권한/스키마 실패는 계속 차단 |
| 기준 커밋의 광고 MongoDB 인계와 실제 repository | 광고 API → TLS/인증 → MongoDB `ads-rs` | 데이터/config 백업 후 기존 노드를 단일 멤버 replica set으로 전환. 스키마·인덱스 검사 및 실제 transaction abort 확인. 단일 노드이므로 DB HA는 아님 |
| 실제 설치 Spark 4.1.3 / Scala 2.13 / Hadoop 3.4.2 | `pipeline/weather/submit_spark.py` → 설치된 spark-submit → Kafka → 정규화 → ES | 온라인 Maven 해석 제거. 배포판 286개 JAR와 추가 8개 JAR의 고정 해시 확인. Control 2대와 Spark 3대에 같은 잠금 적용. Python 3.14.8 일치 |
| 기준 커밋의 `pipeline/weather/` 실제 호출 관계 | KMA 수집 → `weather.v1` → Spark → ES 최신 읽기 모델 → 공통 날씨/추천 API | 날씨 MongoDB 저장 모듈은 활성 Spark 작업에 연결되지 않았고 날씨 원문 보관도 미연결. 광고 MongoDB와 구분. PostgreSQL에는 지역/도로 매핑 사용 |
| 기준 커밋의 공통/광고 인증 계약 | 브라우저 → HTTPS CloudFront → ALB → Control nginx → 공통 또는 광고 API. 광고 → Control A의 private TLS 8443 → 공통 인증 | 동일 origin으로 쿠키/CSRF 처리. 공개 `/api/internal/` 차단. 광고 bridge는 기존 사설 CA로 서버 인증서를 검증 |

수령 원문 및 타인의 변경 라우팅 문서는 수정하지 않았습니다. 위 문서 버전은 앱 기준 커밋에 포함된 내용이며, 실제 설치 사실은 별도 실행 영수증으로 확인했습니다.

## 바꾼 코드와 전후 동작

| 파일/함수 | 변경 이유와 결과 |
|---|---|
| `backend/cafe/settings.py`, `backend/.env.example` | 음악 S3 보류를 명시하는 설정 추가. 운영 DB와 통합 모드는 그대로 사용 |
| `backend/common/music_archive.py:store` | 보류 상태에서도 지정된 로컬 원본 보존이 없으면 실패. S3 성공으로 표시하지 않음 |
| `backend/common/management/commands/check_runtime.py` | 명시 보류 항목만 필수 S3 검사에서 제외. 활성 카탈로그가 없으면 `ADMIN_READY_MUSIC_PENDING`, `ready=false` 유지 |
| `pipeline/weather/submit_spark.py:connector_arguments` | 잘못된 Spark 3.5/Scala 2.12 Kafka package 자동 설치를 제거. 검토한 4.1.3/2.13 잠금과 전체 JAR 해시·목록 검사 |
| `pipeline/weather/submit_spark.py:runtime_arguments` | 읽을 수 없는 Spark 설정을 조용히 무시하여 인증 없이 접속하는 문제 방지. 인증/암호화가 켜진 properties 파일을 명시적으로 전달 |
| `backend/common/music_api.py:Readiness`, `backend/music/catalog.py:export_tracks`, `backend/recommendation/policy.py` | 89,740곡의 관리 조회에서 30초 제한이 발생하여 iterator와 순차 집계로 전체 객체 동시 적재를 없앴고, 불변 Fraction 계산을 제한된 LRU에 재사용합니다. 6,048개 날씨 판정의 상세 결과까지 기존 develop과 동일함을 비교했습니다. 점수식·정밀도·기준은 변경하지 않음 |
| `backend/common/music_api.py:Publish` | 명시 S3 보류 모드와 원본 해시 보존이 발행 API에서도 일관되도록 연결. 검수 승인/불변 원본 검사는 유지 |
| `backend/recommendation/catalog_storage.py`, `backend/music/catalog.py:publish`, `backend/recommendation/worker.py:verified_catalog` | 최초 89,740곡 JSONB INSERT에서 PostgreSQL 2GB 메모리 부족과 프로세스 종료를 실제 확인. 1MiB 초과 카탈로그를 gzip/base64 JSON envelope로 무손실 저장하고 worker에서 복원. 기존 list 형식도 읽음. 원본 곡/점수 JSON 기준 SHA-256 및 중복 곡 검사는 유지하며 512MiB 복원 상한·길이/형식/무결성을 검증. DB schema·외부 API·추천 점수/정렬 정책 변경 없음 |
| `pipeline/weather/.env.example`, `requirements-spark.txt` | 설치 Spark·Driver 설정 경로와 PySpark 참조 버전을 맞춤. 서버에는 별도 pip PySpark를 설치하지 않음 |
| `ad-server/backend/config/settings.py`, `.env.example` | `DJANGO_CSRF_TRUSTED_ORIGINS` 연결. 프로덕션 HTTPS origin에서 광고 POST 검증 가능 |
| `deployment/aws/install_app.py` | 인스턴스/세대/소스 해시 확인, 별도 venv, 권한, systemd/nginx, 선택된 한 Control의 writer 초기 설치. 기존 계정·승인·데이터를 초기화하지 않음 |
| `deployment/aws/control-nginx.conf.in` | dev Vite proxy를 대체하는 운영 경로. 공통 loopback 8001, 광고 private 8000, 내부 인증 TLS 8443. 원본 비밀 헤더 및 긴 헤더용 map hash 크기 설정 |
| `deployment/aws/mongodb_replica.py` | TLS/인증/사용자/데이터를 보존하는 명시 전환. 새 MongoDB EC2를 만들지 않음 |
| `deployment/aws/install_connectors.py`, `connectors.lock.json` | 유일한 idle Spark cluster를 확인한 뒤 검토된 JAR만 설치. 공개 lock 파일 읽기 권한도 명시 |
| `deployment/aws/prepare_kafka.py` | 관리자 인증 파일로 앱 토픽 두 개 준비. RF=3, partition=3, minISR=2. 앱 계정에는 토픽 Read/Write/Describe, 정확한 피드백 group 및 Spark group prefix 권한만 부여. 대상 호스트 제한 |
| `deployment/aws/edge_config.py`, `*-app-network.template.json` | 실제 적용한 CloudFront/통신 규칙을 비밀값 없는 코드로 재현. CloudFront 설정 출력은 비공개 파일로 생성. 89,740곡 관리 집계의 응답 시간에 맞춰 origin read timeout 60초 적용 |

`common-runtime.lock`은 공통 앱 잠금 파일에 ASGI 실행기만 보완합니다. `advertising-runtime.lock`은 광고 `uv.lock`의 배포 의존성과 Gunicorn을 고정합니다.

## 진입점과 통신

- 임시 진입점: `https://d55cemi1yl53l.cloudfront.net/`
- `/`, `/admin/ads`, `/admin/music` 등은 같은 프론트엔드 SPA입니다.
- `/health/`, `/api/auth/*`, 음악·추천·날씨·피드백 API는 해당 Control의 공통 ASGI 서버로 전달합니다.
- `/api/health`, `/api/ads`, `/api/ad-events`, `/api/ad-deliveries/*/image`, `/api/admin/ads*`, `/api/admin/ad-assets*`는 광고 호스트로 전달합니다.
- 광고의 관리자/guest 검증은 Control A의 private HTTPS 8443을 이용합니다. 외부에서 내부 인증 API를 호출할 수 없습니다.
- viewer는 현재 배포 담당자 Mac의 단일 IPv4 /32로 제한합니다. 재접속 중 공인 IP가 변경되어 이전 IP를 새 IP로 교체했으며 전체 IP 공개는 하지 않았습니다. ALB에는 CloudFront 원본 prefix list를 허용하고 nginx에서 비밀 origin header를 확인합니다. 애플리케이션 API는 캐시하지 않습니다.
- 임시 구성의 브라우저→CloudFront는 HTTPS이고 CloudFront→기존 ALB는 HTTP입니다. 소유 도메인/ACM 인증서가 준비되면 origin TLS 구성은 별도 교체해야 합니다.

## 환경변수·초기 운영값

- 인계 경로: `<비공개 환경 인계 디렉터리>/backend/.env`, `pipeline/weather/.env`. 비밀값은 보고서·명령 인자·Git 파일에 넣지 않습니다.
- 기존 인프라의 `POSTGRES_*`를 공통 앱 `PG*`로 매핑합니다. `PGSSLMODE=verify-full`, 기존 역할별 CA 경로를 사용합니다.
- 광고 URI에는 인증 DB, `replicaSet=ads-rs`, TLS 및 CA를 명시하고 클라이언트에서도 멤버 이름 `mongodb`를 해석합니다.
- Kafka는 SASL_SSL/PLAIN, ES는 HTTPS와 pipeline_writer를 사용합니다. JVM Kafka는 공통 공개 CA 파일을 검증합니다.
- 초기 접속 검증값: guest 86,400초, 관리자 세션 3,600초, CSV 업로드 25 MiB, 탐색 60초/초기 후보 200(실제 전체 데이터 검사에서 10→60초로 보완). 사용자가 승인한 실행 준비용 설정이며 제품 보관/운영 정책의 최종 확정을 뜻하지 않습니다.
- Gemini 키는 명시 재설정용 설정에 연결합니다. 자동·시험 유료 호출은 하지 않았습니다.
- 관리자 초기 비밀번호는 daemon 환경에서 제거합니다. 접속 정보는 운영 저장소 `.private/` 안의 소유자 전용 파일에만 보관합니다.

## 검증 결과와 남은 연결

- 공통 Django 전체 98개 테스트 통과(카탈로그 저장 3개, 전수 조합 비교/실제 크기 동점 후보 탐색 2개 추가). .env 작성 후에는 C_LOCAL_DEMO=1, INTEGRATION_ENABLED=0, MUSIC_S3_ARCHIVE_DEFERRED=0, OWNER_RESOLVER/EVENT_SINK 빈 값, GEMINI_ENABLED=0 및 시험용 키로 실행하여 운영 설정과 격리했습니다.
- 광고 Django 테스트 372개 중 368개 통과, 선택 실행하는 MongoDB 통합 테스트 4개 생략. 실제 광고 DB 스키마/인덱스 검사는 별도 통과했고 transaction abort를 실제 replica set에서 확인했습니다.
- Spark 잠금/인증 설정 회귀 테스트 3개 통과. frontend `VITE_C_DEMO=0 pnpm build` 통과.
- 통신 CloudFormation 두 템플릿: cfn-lint, cfn-guard, 서비스 변경 세트 검증 후 CREATE_COMPLETE.
- LIVE CloudFront 함수: 허용 IP 통과, 다른 IP 차단, 내부 경로 차단 모두 확인.
- 실제 HTTPS: 화면/공통 health/광고 health/관리자 로그인·로그아웃/음악 관리 readiness/광고 관리 목록/공개 광고 조회/지역 조회 200. Secure·HttpOnly session/guest cookie 확인. 내부 경로 403.
- 공통 구조 검사: migration, 관리자 권한, PostgreSQL 지역 매핑, ES 스키마, feedback 토픽 통과. 음악 원본 S3는 명시 보류. 아래 사용자 확인 후 카탈로그 발행 절에서 승인·발행 및 실제 기본 추천 생성 결과를 확인했습니다.
- Control A에서만 수집·Driver·추천·피드백 writer를 실행하고 Control B에서는 writer를 비활성화했습니다. 자동 승계/fencing 및 장애 복구는 완료로 표시하지 않습니다. 광고 인증도 현재 Control A에 의존합니다.
- 실제 기본 추천 생성·결과 조회는 아래 세 조건에서 검증했습니다. 실제 Gemini 호출, 평가→집계, 장애 전환은 미검증입니다. 기본 지역 매핑은 준비했지만 도로명 상세 주소 원본 DB는 제공되지 않아 road_data_loaded=false입니다.
- 실제 청구액은 조직 SCP가 Cost Explorer 호출을 거부하여 확인하지 못했습니다. 조직 정책과 IAM을 변경하지 않았습니다. 새 EC2/VPC 증설 없이 CloudFront 배포/함수와 기존 S3 설치 artifact 저장·요청, NAT/통신의 사용량이 추가 과금 대상입니다. 계정 공용 무료 한도 잔여는 미확인입니다. 대체 CloudWatch 청구 추정 메트릭도 encore1은 접근 거부, encore2~5는 등록 메트릭 0개여서 실제 예산 잔액을 확인하지 못했습니다.

승인된 인프라·앱 연결 준비를 마무리했습니다. 최종 적재 건수·날씨 저장/조회·실행 결과는 아래와 같습니다. 초기 준비 시점과 후속 카탈로그 발행·추천 검증 결과를 구분하며 운영 HA 완료로 해석하지 않습니다.

## 실행 영수증과 재개

운영 저장소의 `aws-infra/.state/operations/application-deployment/latest.json`이 해당 실행 폴더를 가리킵니다. SSM 명령·변경 세트·검증 영수증은 `.state/`, 비밀 환경/설치 묶음/CloudFront 원본 헤더는 해당 세대의 `.private/`에 있습니다. 이 파일들은 Git에 올리지 않습니다.

같은 영수증의 SSM 명령을 먼저 조회하고, 결과가 불명확할 때 생성 작업을 다시 제출하지 않습니다. 음악 import는 원본 SHA와 `MusicImportRun.last_track_id` 체크포인트로 재개하며 검수 상태를 자동 승인하지 않습니다. 기존 EC2를 종료하거나 데이터 디스크·checkpoint·DB를 초기화할 필요가 없습니다.

## 2026-10-16 초기 준비 시점의 실행 확인

- PostgreSQL: 고유 곡 89,740건, Review 초안 89,740건, 오류 1행(65,902행) 격리, import checkpoint completed=true. 승인 Review 0건/활성 Catalog 0건. 초기 30분 제한에서 62,500곡으로 중단된 뒤 체크포인트로 재개해 완료했습니다. 설치 import 제한은 7,200초로 보완했습니다.
- 실제 날씨: KMA 수집→Kafka(3 partitions)→Spark(한 active Master/두 standby, 3 workers/3 cores)→ES 1,631 격자 문서 발행을 확인했습니다. 실제 지역 3곳의 API에서 관측 valid, 6개 예보 구간, is_test=false, recommendation_ready=true를 확인했습니다.
- 배포 화면에서도 지역 검색 후 기상청 관측값/기온/예보가 표시됐습니다. 가상 날씨를 붙이지 않았습니다.
- HTTP GET은 HTTPS로 301. 광고 POST는 정상 origin에서 입력 검증 422, 다른 origin은 403으로 확인했습니다. 잘못된 입력을 이용해 시험하여 실제 광고 캠페인은 생성하지 않았습니다.
- 전체 IP 공개 없이 현재 Mac의 단일 /32를 사용합니다. 원본 ALB 직접 접속은 SG로 제한되고 nginx도 비밀 헤더를 검사합니다. Mac의 외부 IP가 다시 변경되면 viewer 허용값 갱신이 필요합니다.
- 두 Control에 동일한 앱 release `e2b7d62-2c764cd6d0b37a43`을 적용했습니다. Control A의 이전 Spark application이 모든 Master에서 종료된 것을 확인한 뒤 다시 시작했습니다. 기존 DB·검수 상태·체크포인트를 유지했으며, Control B의 writer는 비활성 상태입니다.
- 음악 관리 readiness는 실제 전체 PostgreSQL 데이터에서 서버 내부 cold 30.750초/warm 31.353초였습니다. CloudFront origin read timeout을 30→60초로 변경한 배포가 Deployed인 것을 확인했습니다. 최종 외부 HTTPS 조회는 HTTP 200, 34.480초였습니다. 오류는 해소했지만 대량 집계가 즉시 응답하는 상태는 아니며, 추가 성능 개선은 후속 과제입니다. [AWS origin timeout 기준](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/DownloadDistValuesOrigin.html)을 확인해 적용했습니다.
- 최종 HTTPS 화면/공통 health/광고 health/관리자 로그인·로그아웃/광고 관리·공개 광고/지역 조회는 모두 200, 내부 인증 공개 경로는 403입니다. Secure·HttpOnly session/guest 쿠키와 두 Control의 ALB target healthy를 확인했습니다.
- 최종 시점에도 실제 날씨 3개 지역은 valid/예보 6구간/is_test=false였고, Spark는 ALIVE Master 1개/STANDBY 2개, worker 3개와 RUNNING weather-stream 1개/3 cores였습니다. 최근 Driver 오류는 없었습니다.
- 최종 `check_runtime --connect --allow-pending-music`은 두 Control에서 성공했으며, status는 의도대로 `ADMIN_READY_MUSIC_PENDING`, ready=false입니다. 89,740곡 적재 완료와 승인 0/활성 카탈로그 0을 다시 확인했습니다.
- 변경/신규 파일 29개 검사에서 전달된 실제 비밀값 일치 0건, Python 파일 15개 구문 검사와 git diff --check 통과. 서버용 세 .env는 Git 제외·0600이며 커밋/푸시는 하지 않았습니다.
- AWS 공식 [CloudFront 요금표](https://aws.amazon.com/cloudfront/pricing/pay-as-you-go/)의 무료 한도는 월 인터넷 전송 1TB, HTTP(S) 요청 1,000만, 함수 호출 200만입니다. 공유 한도 잔여·origin 전송·설치 artifact/NAT 등 모든 청구를 포함한 금액을 무료로 확정하지 않았습니다. 대체 메트릭 위치·제공 조건은 [CloudWatch 청구 추정 공식 안내](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/gs_monitor_estimated_charges_with_cloudwatch.html)를 참고했습니다.


## 사용자 검수 완료 확인 후 초기 카탈로그 발행 — 2026-10-16

- 최신 사용자 결정: “이미 검수된 데이터야. 그러면 웹에서 조회될수있도록 카탈로그 발행해봐”. 이를 근거로 CSV 원본 SHA `b202fa49909b2d5cef71a04b1d21243cfeb36414535f2ca9272aa646721177bd`에 속한 89,740곡을 승인했습니다. 사용자 확인을 기록한 reason과 곡별 revision/ReviewChange 89,740건을 생성하고 AdminAction에 소스 단위 실행 키를 보관했습니다. 기존 곡 특성·태그·검수 값은 재작성하지 않았습니다.
- 승인 전 Review 상태는 Control A의 `/var/lib/music-cluster/control/operations/initial-reviewed-catalog/reviews-before-<source-sha>.json.gz`에 소유자 전용으로 보존했습니다. 승인·발행은 별도 멱등 키를 사용하므로 발행 실패가 승인 이력을 중복 생성하지 않습니다.
- 최초 대량 JSONB 발행은 DB INSERT 중 실패했고 커널에서 postgres 프로세스 OOM 종료를 확인했습니다. PostgreSQL은 정상 복구됐으며 기존 적재·승인 이력을 확인했습니다. 해당 실패 영수증과 로그를 보존하고 같은 저장 형식으로 재시도하지 않았습니다.
- 증설 없이 위 저장 형식 보완을 적용했습니다. 두 Control의 앱 release는 `e2b7d62-a3bcc7358a8d2036`이며, 기존 Driver 종료 확인 후 writer를 재시작했습니다. Control B의 상시 writer는 계속 비활성입니다.
- 초기 발행의 대량 사전 계산은 Control B에서 실행합니다. 원본 CSV는 같은 SHA로 로컬 보존하며 음악 원본 S3 보류는 유지합니다.

### 발행·선곡표 생성 최종 결과

- 운영 카탈로그 `aws-reviewed-20261016-b202fa49909b`: 89,740곡, ready=true, is_test=false, 원본 SHA 위와 동일. 복원한 곡·점수 JSON SHA는 `23e0e4d0d7070952542509702bcb1884a77e2a508b9c556bc28848c3a60a71f6`입니다. 저장 JSON 15,181,669 bytes, 발행 검증 78.503초.
- PostgreSQL 승인 Review 89,740건/활성 운영 Catalog 1개, `check_runtime --connect`의 active_catalog=true, ready=true, `STORAGE_READY_ARCHIVE_DEFERRED`를 확인했습니다. 음악 원본 S3 보류는 그대로 유지합니다.
- 압축 발행 이후 PostgreSQL은 active/running이며 재시작 횟수는 최초 실패 후의 1회에서 증가하지 않았습니다. 당시 MemoryCurrent=297,684,992 / MemoryPeak=380,686,336 bytes로 확인했습니다.
- 실제 최초 생성에서 10초 및 60초 제한의 CP-SAT 탐색 실패가 확인됐습니다. `backend/recommendation/solver.py:_equal_score_window`에 동일 점수 후보용 정수 subset-sum 경로를 추가했습니다. 시간 우선순위(정확 180분→최소 초과→최소 미달), 정수 밀리초, 고정 시간에서의 동점 순서와 장르 제약을 보존합니다. 서로 다른 점수·복잡한 장르 대표 조건·메모리 상한 초과는 기존 CP-SAT 경로를 사용합니다.
- 작은 후보의 모든 조합과 비교해 기존 시간·동점 결과를 검증했고, 200곡 동점 후보에서 일반 최적화기를 반복 호출하지 않는 회귀 검사를 통과했습니다. 실제 실패 후보는 서버 안에 둔 채 비교했으며 세 조건에서 정확히 10,800,000ms, 정수 조합 0.357~0.567초였습니다.
- 최종 두 Control 앱 release: `e2b7d62-a0ae4b0f78e9c290`. writer는 Control A에만 있으며 Control B의 상시 writer는 비활성입니다. SEARCH_SECONDS=60은 두 서버 및 로컬 Git 제외 backend/.env, 후속 운영 준비 코드에 반영했습니다. 카탈로그를 재발행하거나 승인 이력을 중복 생성하지 않고 탐색 수정본만 적용했습니다.

| 실제 HTTPS 기본 추천 조건 | 결과 곡 수 | 총 재생시간 | 요청~결과 조회 | 결과 |
|---|---:|---:|---:|---|
| 날씨 미반영·선택 없음 | 45 | 180.000분 | 5.011초 | SUCCEEDED, 운영 자료 |
| 실제 강남 지역 날씨 반영·맑음 | 52 | 180.000분 | 3.810초 | SUCCEEDED, 운영 자료 |
| 날씨 미반영·밝은 테마·팝 | 48 | 180.000분 | 3.597초 | SUCCEEDED, 팝 시간 비율 100% |

모두 RULE_BASED, is_test=false, validation_passed=true이며 중복 곡이 없고 같은 발행 카탈로그를 사용합니다. Gemini 유료 호출·자동 선곡표 승인은 하지 않았습니다. 다른 모든 취향 조합의 성공률·부하/장애 전환·평가 집계는 이 세 사례의 검증 범위에 포함하지 않습니다.

진단 중 운영 후보 200곡의 ID·재생시간·장르를 로컬에 반출하는 명령은 별도 반출 승인이 없다는 자동 승인 검토로 거부됐으며 실행되지 않았습니다. 후보를 서버 안에 둔 상태에서 비식별 성공·곡 수·총 시간·계산 시간만 확인하는 검증으로 대체했습니다.

- 최종 브라우저에서도 실제 지역의 날씨 반영 상태로 [선곡표 받기]를 눌러 52곡 목록·첫 곡·평가/제외/승인 조작이 표시되는 것을 확인했습니다. 선곡표 승인·평가 저장은 실행하지 않았습니다. 두 ALB target은 healthy입니다.
- 최종 변경/신규 파일 34개에서 전달된 실제 비밀값 일치 0건, Python 20개 구문 검사·git diff --check 통과. 세 .env는 0600·Git 제외이며, 커밋·푸시·PR은 수행하지 않았습니다.
