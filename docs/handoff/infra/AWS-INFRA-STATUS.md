# AWS 인프라 설계·인계 문서

- 수정일: 2026-10-15
- 상태 안내입니다. 원문 실행 기록은 `.state/`, 비밀 payload는 `.private/`에 두고 최종 구성 보고서는 실제 구축 완료 후 작성합니다.

인프라 코드와 실행기는 저장소 루트의 `aws-infra/`, 팀 공유 문서는 `docs/handoff/infra/`에서 관리한다.

- [구축 계획](<AWS 인프라 구축 계획.md>): 확정 아키텍처·예산·배포/삭제 단계와 검증 기준.
- [팀원 배포 규약](TEAM-HANDOFF.md): 기반 서비스와 업무 앱의 책임·접속·DB/TLS·Control HA 계약.
- [실행 방법](../../../aws-infra/README.md), [보안 정책](../../../aws-infra/SECURITY.md), [코드 이력](../../../aws-infra/CHANGELOG.md).

## 현재 상태

공개 문서에 남긴 과거 읽기 기준은 **2026-10-14 18:05 KST**, 당시 코드 0.3.0이다. 최신 저장소 코드는 **0.3.19**이다.
최신 AWS 조회·bootstrap 보완·배포 시도와 계정별 결과는 `.state/`의 영수증을 따른다. 과거 확인을 현재 실시간 상태나 배포 완료로 해석하지 않는다.

| 구분 | 확인 내용 |
|---|---|
| 확정 설계 | 서울, 독립 5계정/5VPC/14EC2/3물리 AZ, T3 Standard/gp3/Ubuntu/systemd |
| 운영 예산 | 96시간 산정; encore1~4 각 $45, encore5 $20, 총 $200; 강제 유지/자동 삭제 아님 |
| 과거 AWS 확인 | 위 읽기 기준의 5계정 IAM bootstrap UPDATE_COMPLETE·CF 속성·리소스·Outputs·읽기 접근 확인. 최신 코드와 실제 권한 일치는 실행 시 재검증 |
| 배포 전 입력 | 18:05 KST의 AWS 읽기/입력 준비 통과. 현재 로컬 오프라인 readiness의 코어/ALB 입력 누락·준비 이슈 0건; AWS 상태 재확인 아님 |
| 외부 접속 | ALB 기본 DNS + 임시 HTTP 80 + 허용 /32; 실제 CIDR은 로컬 config에만 보관 |
| 구현 | 전체 create/status/destroy/recreate, setup/verify, ALB 추가/설정 변경; PG/Mongo 포함 14노드 기반 설치 코드 |
| 실제 워크로드 | 과거 읽기 기준으로 VPC·프로젝트 EC2·SSM 노드·ALB 모두 0개. 최신 생성 상태는 비공개 실행 영수증에서 확인 |
| 실행 수용 범위 | 기반 설치/서비스 smoke, connector, 격리 canary/물리 fencing/S3 checkpoint 승계의 완료 여부는 단계별 비공개 영수증으로 확인. 실제 앱/ALB·앱 HA와 삭제 후 재생성은 별도 수용 |
| 업무 앱 담당 | 제품 기준 FastAPI 웹·Collector·Spark Driver·광고 앱 소스/배포/migration/업무 흐름은 팀원; 앱 소스는 인프라 준비 선행 조건 아님 |

## 0.3.11 구현·정적 검증

| 단계 | 이번 작업 결과/남은 범위 |
|---|---|
| 지침/계획 | 루트 AGENTS는 제품·팀 공통, aws-infra/AGENTS는 AWS 설치·운영. 제품 FastAPI·기능/담당·확정 구성 유지; ASGI 실행 선택과 앱/HA 통합은 TEAM-HANDOFF 5절에 분리 |
| 구현 | `service_ports.web`/기존 별칭 호환, 오프라인 readiness, 기록된 빈 REVIEW_IN_PROGRESS 재개. DescribeEvents 서울 리전 읽기와 encore1 CF 실행 역할의 ALB 계정 속성 읽기 예외. 운영/다른 계정·CF/IAM 쓰기 제한 유지. SSM 전체 invocation 관찰과 대상 식별/미조회/실패 처리. IMDSv2 instanceType 대조와 AWS guest 예약 RAM 판정; 로컬 기준 유지. Spark 설치 전 ZooKeeper TLS 경로 선택. MongoDB 저장소 공개 서명 키의 apt 읽기 권한과 재시도 복구. Kafka/S3A 고정 lock·명시 bundle·격리 checkpoint probe·Control 승계 판정과 offline integration-plan |
| 정적 검증 | 테스트 162개 통과, CF 36개 lint 발견 0건, guard 24 PASS/12 SKIP/0 FAIL, 공개 후보 120개 파일 검사 발견 0건 |
| 설치 원본 | 변경 없는 원본 12개 해시 일치; AWS 패치 9개는 명시된 변경과 현재 코드 해시로 구분. 설치 artifact 다운로드/실행 검증과 별개 |
| 구성 보존 | 기존 실제 로컬 설정·확정 구성 유지. bootstrap의 검증 이벤트/ALB 계정 속성 읽기 보완 외 워크로드 리소스 속성·Parameters·Conditions·Outputs 유지 |
| 실제 배포 | 정적 검증과 별개. IAM 보완과 전체 생성 시도의 계정별 결과·권한 거부·중단 영수증은 `.state`에만 저장 |
| 서비스 검증 | 정적 검사와 구분하며, 각 실행의 기반 설치/health/smoke 결과는 `.state` 영수증으로 확인한다. 별도 fresh verify·앱/ALB target·fencing/connector·실제 S3 단일 writer·삭제 후 새 세대 재생성은 각각 검증 필요 |

현재 로컬 브랜치는 `feature/infra`이고 `origin`과 인프라 CI workflow 파일이 존재한다. 로컬 `main`도 있으나 원격 기본/통합 브랜치·권한/보호·CI 실행은 미검증이다. 공통 pr-gate/이슈·PR 템플릿/CODEOWNERS는 미구성이며 인프라 workflow 파일 존재와 구분한다. Git init/add/commit/push 및 원격 설정 변경을 수행하지 않았다.

## 다음 작업

1. 새 채팅에서는 루트 AGENTS.md·CONTRIBUTING.md, aws-infra/AGENTS.md·README.md·SECURITY.md와 이 디렉터리 문서를 읽고 로컬 config/상태를 확인한다. `readiness`로 AWS 호출 없는 준비 근거를 확인한다.
2. 실제 생성·설치·삭제는 각각 사용자가 명시적으로 요청한 범위에서 수행한다. 진행 중인 명시 요청은 유지하며 과거 명령 기록만으로 새 실행을 시작하지 않는다. bootstrap IAM 보완에는 해당 계정의 소유자/관리자 로그인이 필요하다.
3. 실제 생성 단계에서 CloudFormation 변경 세트와 서비스 사전 검증을 확인하고 network→storage→peering/route→EC2→ALB 순서로 진행한다.
4. 이후 setup/verify와 팀원 앱 배포, HA/단일 writer, 전체 삭제/새 세대 재생성 실증을 단계별로 구분한다.

완료된 로컬 9VM, 음악 원본 S3, 프로젝트 외 데이터를 유지한다. destroy는 bootstrap/IAM/Mac 프로필을 유지한다.
전체 신규 설치에서는 Kafka offset/Spark checkpoint 초기화를 허용하지만 재시도·재시작·Control 승계에서는 자동 초기화하지 않는다.
일반 실행 기록은 aws-infra/.state에만 두고, 최종 인프라 구성 보고서는 실제 구축 완료 후 작성한다.
새 채팅용 복사 프롬프트는 채팅 답변에만 표시하며 파일로 저장하지 않는다.

## 이전 로컬 검증 이력

구조 변경 전 테스트 95개, CF 36개 lint 발견 0건, guard 24 PASS/12 SKIP/0 FAIL을 확인했다.
0.3.1 구조 변경 후 **테스트 99개 통과**, CF 36개 lint 발견 0건, guard 24 PASS/12 SKIP/0 FAIL, 공개 후보 105개 파일에서 비밀정보 패턴 발견 0건을 확인했다. 문서/템플릿 참조 125개도 정상이며 workflow YAML과 shell/Python 문법을 확인했다. GitHub CI 원격 실행/게시/커밋은 수행하지 않는다.
공개 검사는 AWS 코드·이 디렉터리·루트 인프라 CI 범위이며 저장소의 다른 기존 파일과 과거 Git 이력은 별도 검토한다.

## 새 Git 저장소로의 경로 정정

지정한 새 저장소 루트로 aws-infra와 공유 문서/CI/제외 규칙을 실제 이동했다. 기존 저장소의 제품 지침·README·수령 원문과 로컬 가이드는 보존했다. 기존 인계 README는 문서 안내로 유지하고 이 최신 상태 페이지를 별도로 연결했다.

이동 후 테스트 99개 통과, CF 36개 lint 발견 0건, guard 24 PASS/12 SKIP/0 FAIL, 공개 후보 108개 파일 비밀정보 패턴 발견 0건, 새 경로 문서/템플릿 참조 133개 정상을 확인했다. 경로의 공백을 처리하도록 로컬 검증 도구의 실행 경로를 재연결했고 실제 lint 실행을 확인했다. AWS 상태 기준은 계속 18:05 KST 읽기 기록이며 새 AWS 조회/배포나 Git add/commit/push는 수행하지 않았다.

## 0.3.11 후속 통합 준비

[후속 통합 준비](INTEGRATION-READINESS.md)를 따른다. Kafka/S3A 추가8개/배포본286개 JAR 해시를 고정하고 Spark 제공 logging/native/Scala 의존성을 유지한다. 로컬 클래스 로딩·파일 checkpoint 순차 재시작은 실제 cross-account S3·동시 writer·HA 성공과 구분한다. 현재 배포된 세대의 identity와 package를 자동 변경하지 않으며 live fencing adapter/권한·ES/Delta/앱 통합은 미완료다.


## 0.3.12 Control 실행기 준비

| 단계 | 범위 |
|---|---|
| 계획 | 기존 구성/제품·담당 유지. 앱 소스 없이 canary 기반 준비. 적용 순서는 observer IAM/SSM 3개 → Control peer 권한 → 별도 canary 설치/명시 활성화 |
| 구현 | TLS/SASL/digest ACL 선출·영속 owner/epoch CAS·정확한 peer 중지 확인·고정 문서/nonce 기반 Spark 전체 idle 관측·lease 상실 시 프로세스 그룹 종료. 별도 lock/payload와 disabled unit, offline control-plan |
| 정적 검증 | 테스트 193개 통과. 기존 CF 36개 lint 발견 0건·guard 24 PASS/12 SKIP/0 FAIL. 별도 IAM/SSM 제안 4개 lint 발견 0건; 기존 EC2/S3/SG guard는 이 4개에 SKIP이며 IAM 범위는 회귀 검사로 확인. 공개 후보 134개 파일 발견 0건 |
| 실제 배포 | 이 준비 코드의 IAM/SSM·Control 설치/활성화·EC2 중지를 실행하지 않음. 이전 기반/connector 배포 identity와 새 작업 소스 identity를 분리하고 영수증을 보존 |
| 서비스 검증 | 격리 로컬 quorum/canary와 실제 노드 읽기 관측의 근거는 `.state/preparation/control-fencing`에만 보관. 물리 fencing·S3 동시 writer/승계·업무 앱/ALB·삭제 후 재생성은 별도 수용 필요 |

[Control fencing 적용 전 검토](CONTROL-FENCING.md)의 호스트 전체 중지 영향·전역 idle 제한·AWS CLI/문서 version/hash 선행 조건과 원복 순서를 따른다. 새 코드 생성은 현재 AWS 역할에 권한을 부여하지 않는다. Delta 4.3.1은 기본 전이 의존성이 Spark 제공 버전과 충돌해 미채택이며 별도 pin/lock/검증이 필요하다. ES 공식 Spark 4.1 connector 또는 REST/Bulk 연결은 별도 선택으로 유지한다.


## 0.3.13 명시 AWS CLI 설치 지원

공식 AWS CLI v2의 버전별 ZIP·서명·공개 키 SHA256 및 signer fingerprint를 고정하고 gpgv 검증 후 전용 경로에 설치하는 Control 전용 코드를 추가했다. 글로벌 CLI/PATH·Mac encore 프로필·업무 앱/venv를 변경하지 않으며 부분 설치를 자동 덮어쓰지 않는다. 기본 setup에는 자동 포함하지 않는다.

정적 테스트197개, 기존 CF36 lint 발견0/guard24 PASS·12 SKIP·0 FAIL, 별도 IAM/SSM4개 lint 발견0/기존 EC2·S3·SG guard SKIP, 공개후보138개 발견0을 확인했다. IAM 정책·신뢰 검증과 실제 설치/적용·단위 상태·역할 보존 결과는 `.state/operations/control-fencing`에서 별도로 확인한다. 코드 버전 갱신은 과거 foundation/connector 배포 identity나 영수증을 갱신하지 않는다. 물리 peer 중지·S3 단일 writer 승계는 이 정적 검사의 성공 범위가 아니다.

## 0.3.14 종료 대기와 수용 범위

| 단계 | 범위 |
|---|---|
| 계획 | 기존 제품/담당·확정 구성 유지. 정상 canary → 제한적 장애 → 실제 peer 중지 확인 → 같은 checkpoint 승계 → 운영자 복구를 구분 |
| 구현 | supervisor의 프로세스 종료·최대75초 Spark 관측·owner CAS를 위해 systemd 종료 대기180초. lease 상실 시 프로세스 그룹 종료와 Restart=no 유지 |
| 정적 검증 | 테스트197개 통과, CF36 lint 발견0, guard24 PASS/12 SKIP/0 FAIL, 공개후보139개 발견0. 실제 물리 승계의 증거와 구분 |
| 실제 배포 | 기존 설치 source identity와 별도 unit 설정 보완을 구분. 변경 여부·CommandId·결과는 `.state/operations/control-acceptance`의 영수증 확인 |
| 서비스 검증 | 격리 canary/ACL·정확한 EC2 stopped·Spark idle·S3 query ID/run ID/고유 결과·복구 근거를 단계별 저장. 감독 밖 writer 차단이나 실제 업무 앱 HA로 확대 해석하지 않음 |

실제 시험 기록은 공개 문서에 옮기지 않는다. S3 자체가 epoch를 검사하는 구현은 없으며, 모든 writer가 동일 supervisor의 감독을 받는 계약이 필요하다. ES/Delta 기술 선택·업무 앱 연결·삭제 후 재생성은 별도 단계다.

## 0.3.15 Delta addon

별도 Delta4.3.1 lock·검증/원자적 addon 설치기·고유 S3 시험 실행기를 제공한다. 기존 Spark286/Kafka·S3A8개 JAR와 전역 설정을 보존하며 명시 작업의9개 JAR만 연결한다. 정적 무결성 검사와 실제5대 설치·분산 S3 트랜잭션/체크포인트 검증은 구분하고 실행 결과는 `.state/operations/delta`를 따른다. 기본 setup/verify와 기존 foundation/connector/controller source identity는 자동 갱신하지 않는다. 실제 앱/복수 Driver 동시 쓰기·Unity Catalog 서비스·ES 연결·삭제 후 재생성은 별도 수용이다.

## 0.3.16 addon 서비스 사용자 접근

비공개 설치 umask0077에서도 새 공개 JAR 상위 디렉터리에0755 통과 권한을 설정한다. JAR0644와 runtime/비밀값의 비공개 권한을 구분하며, 동일 lock의 명시 재검증은 최초 설치 source marker를 보존한다. 회귀 검사를 포함한 오프라인 테스트204개가 통과했다. 실제 서비스 사용자 읽기·원래 JAR/설정 보존·S3 결과는 `.state/operations/delta`의 별도 영수증을 따른다.

## 0.3.17 ES·앱 실행 인계 준비

ES Spark JAR 없이 기존 검증 CA/HTTPS와 pipeline_writer로 실행하는 격리 REST/Bulk probe와 직접 경로·목적지 ingress를 분리한 오프라인 앱 계약 검사기를 제공한다. 부분 bulk 오류/동일 ID 재전송·실제 Spark 결과 전송의 수용 여부는 `.state/operations/service-handoff`의 영수증으로 구분한다. 업무 ES 전송 방식·날씨 MongoDB writer/전용 DB·ASGI/start-stop·단일 active 실행은 [앱 실행 계약](APPLICATION-CONTRACT.md)에 남긴다. Control↔MongoDB Peering만으로 현재 광고 전용 ingress가 열리지 않으며 확정7쌍 Peering/14노드·SG/DB·업무 앱을 자동 변경하지 않는다.

오프라인 테스트215개(새 bulk 오류/설계 경로 검사11개 포함), 공개 후보151개 검사 발견0·변경 문서 참조23개 정상·Python 문법/git diff --check를 확인했다. CF 템플릿 변경은 없으며 과거36개 lint0/guard24 PASS·12 SKIP·0 FAIL과 새 검증 결과를 구분한다.

## 0.3.18 날씨 MongoDB 접근 분리

사용자 요청으로 기존 MongoDB SG에 두 Control의 정확한 /32·27017만 추가하는 설계를 반영했다. 전용 weather/weather_app·readWrite/SCRAM-SHA-256·Control0640 환경 파일과 고정 mongosh 격리 클라이언트를 별도 명시 단계로 제공한다. 기존 광고/PG 환경·사용자·설치 identity/비밀값·7Peering/14노드를 유지하고 실제 CF 변경/DB 생성·두 Control TLS/권한 격리 결과는 `.state/operations/weather-mongodb`에서 확인한다. 앱 프로세스/데이터 흐름·실제 Driver/HA와 전체 삭제/재생성은 별도 수용이다.

## 0.3.19 앱 실행 계약 인계

| 단계 | 범위 |
|---|---|
| 계획 | 제품 FastAPI/담당·확정 구성을 유지하고 팀의 ASGI/Driver·query/checkpoint·ES 업무 계약 입력을 분리 |
| 구현 | 입력 형식/foreground argv·서비스별 credential 참조·세대/query checkpoint 검사, 로컬 비공개 인계 묶음·미입력 목록/검토 템플릿 생성 |
| 정적 검증 | 오프라인 테스트235개 통과, CF36개 lint 발견0·guard24 PASS/12 SKIP/0 FAIL. CF 속성 변경 없이 코드 버전 metadata만 갱신. 공개 검사/문서 참조와 비공개 영수증은 별도 확인 |
| 실제 배포 | 이 단계는 AWS 조회/변경·앱 설치/명령 실행을 수행하지 않음. 기존 foundation/connector/controller/addon 배포 identity를 보존 |
| 서비스 검증 | 실제 앱/ALB·업무 Driver/HA 미검증. canary 전용 설치기와 별도로 업무용 supervisor 설치/lifecycle 연결이 필요 |

[앱 실행 계약](APPLICATION-CONTRACT.md)의 미정 입력을 담당자가 제공한 뒤 검토안을 완성한다. 앱 소스는 기반 인프라 준비의 선행 조건이 아니며 재시작/승계 때 offset/checkpoint를 초기화하지 않는다. 전체 삭제 후 신규 세대 재생성은 별도 명시 요청 범위다.
