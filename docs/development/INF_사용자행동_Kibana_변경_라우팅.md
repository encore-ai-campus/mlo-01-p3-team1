# 사용자 행동 Kibana 대시보드 AWS 연결 작업

- 작성일·수정일: 2026-10-19 (KST)
- 담당: Codex / INF
- 요청: Desktop Commander가 작성한 사용자 행동 분석 4개 파일을 검토하고 기존 AWS Kibana에서 별도 대시보드로 조회
- 현재 상태: 사용자 추가 승인 수령 후 AWS 배포·실데이터·브라우저 검증 완료.

## 기존 작업 보존

수령한 `dashboard_guest_v1.py`, `guest_behavior_export.py`, `guest_behavior_elastic_plan.py`, `GUEST-BEHAVIOR-V1.md`를 기반으로 합니다. 기존 `dashboard.py`, `dashboard_v2.py`, `music-operations-v1`, 기존 수집기와 `ops-mlo-*`는 변경하지 않습니다. 다른 작업자의 dirty 파일을 되돌리거나 Git 커밋·푸시하지 않았습니다.

## 이번 변경

| 파일 | 변경 이유 |
|---|---|
| `aws-infra/observability/dashboard_guest_v1.py` | 정수 매핑인 시간·요일 terms 집계의 문자열 missing 제거, 시각 순서 정렬. 모든 Saved Object ID의 소유권을 첫 쓰기 전에 검사 |
| `aws-infra/observability/guest_behavior_export.py` | 운영 Django 모듈을 `backend.cafe.settings`로 정정. 현재 제외 목록의 family 조회도 상한 초과 시 실패하도록 제한 |
| `aws-infra/observability/guest_behavior_runner.py` | 기존 앱 모델을 쓰되 독립 Django 설정·전용 DB 자격증명만 사용. 동시 실행 잠금. PG 쓰기·민감 컬럼 권한 부재 및 ES writer 격리 검증 |
| `aws-infra/observability/deploy_guest_behavior.py` | 별도 SELECT 역할, 단일 호스트 TLS HBA, 전용 ES 역할/계정, 전용 OS 사용자와 분당 systemd timer를 명시 단계로 설치. 기존 앱 재시작·DB migration 없음 |
| `aws-infra/observability/test_guest_behavior.py` | 숫자 필드 집계, 개인정보 허용 목록, 별점 해제, 타 작업자 객체 충돌 시 쓰기 차단 검증 |

## 확인한 사실과 검증 범위

- 운영 앱은 Django/PostgreSQL이며 두 Control의 릴리스는 조회 시 `muther-e8883da-5b5433f06a3f8b94`입니다.
- 조회 시점 비시험 FeedbackEvent 127건, FeedbackState 39행. 대상 7종 중 실제 존재하는 반응·별점·제외·승인 이벤트 49건입니다. 이후 사용자 이용에 따라 바뀝니다.
- 신설 대시보드 `music-guest-behavior-v1`: 27개 패널, 실제 ES 쿼리 22개, Saved Object 28개. 읽기 전용 사전 검사에서 ID 충돌 없음.
- 로컬 unittest 7개 및 Python 구문 검사 통과. 실제 신규 ES 쿼리·화면 렌더링·분당 수집 검증은 적용 후 수행해야 합니다.
- 기존 PostgreSQL HBA는 앱 계정만 허용하므로 수집기에는 별도 SELECT 계정 및 Control A /32 TLS 허용이 필요합니다.
- 운영 계정 생성 시도가 자동 승인 검토에서 차단되어 사용자에게 DB/ES 전용 접근·기존 ops_admin의 신규 분석 인덱스 읽기·분당 수집기 설치 승인을 요청했습니다. 차단된 작업은 우회 실행하지 않았습니다.

## 배포·재개 순서

운영 권한 변경 승인 후에만 실행합니다. 실행기는 기존 AWS 세대·SSM/S3 private artifact를 사용하며 새 EC2/VPC/IAM 역할을 만들지 않습니다. 자세한 명령과 상태는 Git 제외 `aws-infra/.state/operations/guest-behavior-20261019/CHECKPOINT.md`에 저장합니다.

1. 기존 운영 대시보드 지문·대상 ID 충돌을 확인합니다.
2. 전용 PG SELECT 계정 및 Control A 한 대의 TLS 접근 규칙을 적용합니다.
3. `analytics-mlo-guest-*` 전용 매핑/권한을 설치하고 기존 Kibana 관리자 역할 목록을 보존하며 읽기 역할만 추가합니다.
4. Control A에서 권한 격리 검사, dry-run, 최초 실제 수집 후 분당 timer를 활성화합니다. Control B에는 수집기를 활성화하지 않습니다.
5. 별도 Data View 2개와 Saved Object를 게시합니다. 소유권 ledger 없는 기존 객체를 덮어쓰지 않습니다.
6. 실제 쿼리 22개, SQL/ES 건수, 중복 없는 재실행, 비시험·허용 컬럼, 기존 운영 대시보드 보존, HTTPS 로그인/렌더링을 검증합니다.

## 운영 해석과 중지

이 대시보드는 익명 피드백이며 로그인 사용자 수·순 방문자·음악 실제 재생률이 아닙니다. 현재 상태 카드에는 상단 기간 필터가 적용되지 않으며 이벤트 차트에는 적용됩니다. 초기 이벤트 수집은 최근 30일입니다.

수집기 중지는 Control A의 `music-guest-analytics.timer`와 실행 중 service만 중지합니다. 커서·원본 DB·ES 이력은 삭제하지 않습니다. 운영 대시보드나 앱을 롤백할 필요가 없는 독립 경로입니다. 새 접근권한 회수·인덱스 삭제는 별도 범위를 확인한 뒤 진행합니다.


## 최종 적용·검증

사용자가 전용 PG/ES 접근과 단일 수집기 설치를 모두 승인했습니다. PG 역할/Control A TLS HBA, ES 템플릿2개/전용 writer/기존 ops_admin 읽기 역할, 분당 timer, Data View2개, Saved Object28개를 적용했습니다. PostgreSQL 전용 노드는 공통 runtime.json이 없어 기존 설치기 `aws-state/<세대>/postgresql-identity.json`으로 노드 식별을 검증하도록 보완했습니다. 초기 경로 확인 실패는 DB 변경 전 중단됐고, 최종 PG 단계는 성공했습니다.

SQL/ES 대상 이벤트49건 일치, 시험 문서0, 실제 집계 쿼리22개 통과, 현재 상태 값 일치, 재실행 신규0건·커서 유지, ES writer의 ops-mlo 접근 불가 및 PG 쓰기/민감 컬럼 조회 불가를 확인했습니다. 기존 운영 대시보드/시각화 지문 동일, 앱/추천 서비스 active 유지, 브라우저에서27패널 로딩과 상하단 데이터 표시 확인. Git 커밋·푸시 미실시.
