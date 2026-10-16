# AWS 인프라 설계·인계 문서

- 수정일: 2026-10-14
- 상태 안내입니다. 원문 실행 기록은 `.state/`, 비밀 payload는 `.private/`에 두고 최종 구성 보고서는 실제 구축 완료 후 작성합니다.

인프라 코드와 실행기는 저장소 루트의 `aws-infra/`, 팀 공유 문서는 `docs/handoff/infra/`에서 관리한다.

- [구축 계획](<AWS 인프라 구축 계획.md>): 확정 아키텍처·예산·배포/삭제 단계와 검증 기준.
- [팀원 배포 규약](TEAM-HANDOFF.md): 기반 서비스와 업무 앱의 책임·접속·DB/TLS·Control HA 계약.
- [실행 방법](../../../aws-infra/README.md), [보안 정책](../../../aws-infra/SECURITY.md), [코드 이력](../../../aws-infra/CHANGELOG.md).

## 현재 상태

AWS 조회 기준: **2026-10-14 18:05 KST**, 당시 코드 0.3.0. 최신 저장소 코드는 **0.3.2**이다.
0.3.1 경로 이동과 0.3.2 준비 작업에서는 AWS 재조회·변경 세트·생성·설치·삭제를 실행하지 않았다. 과거 확인을 현재 실시간 상태로 해석하지 않는다.

| 구분 | 확인 내용 |
|---|---|
| 확정 설계 | 서울, 독립 5계정/5VPC/14EC2/3물리 AZ, T3 Standard/gp3/Ubuntu/systemd |
| 운영 예산 | 96시간 산정; encore1~4 각 $45, encore5 $20, 총 $200; 강제 유지/자동 삭제 아님 |
| 실제 AWS 완료 | 5계정 IAM bootstrap UPDATE_COMPLETE; 기대한 CF 속성·리소스·Outputs·읽기 접근 확인 |
| 배포 전 입력 | 18:05 KST의 AWS 읽기/입력 준비 통과. 현재 로컬 오프라인 readiness의 코어/ALB 입력 누락·준비 이슈 0건; AWS 상태 재확인 아님 |
| 외부 접속 | ALB 기본 DNS + 임시 HTTP 80 + 허용 /32; 실제 CIDR은 로컬 config에만 보관 |
| 구현 | 전체 create/status/destroy/recreate, setup/verify, ALB 추가/설정 변경; PG/Mongo 포함 14노드 기반 설치 코드 |
| 실제 워크로드 | 조회 VPC·프로젝트 EC2·SSM 노드·ALB 모두 0개; 인프라 생성·EC2 설치 미실행 |
| 미완료 | 실제 쓰기 권한/CF 서비스 사전 검증, 설치/서비스 smoke, 앱/HA/fencing/connector/S3 checkpoint 통합, 삭제 후 재생성 실증 |
| 업무 앱 담당 | 제품 기준 FastAPI 웹·Collector·Spark Driver·광고 앱 소스/배포/migration/업무 흐름은 팀원; 앱 소스는 인프라 준비 선행 조건 아님 |

## 0.3.2 배포 전 준비

| 단계 | 이번 작업 결과/남은 범위 |
|---|---|
| 지침/계획 | 루트 AGENTS는 제품·팀 공통, aws-infra/AGENTS는 AWS 설치·운영. 제품 FastAPI·기능/담당·확정 구성 유지; ASGI 실행 선택과 앱/HA 통합은 TEAM-HANDOFF 5절에 분리 |
| 구현 | 프레임워크 중립 `service_ports.web`, 기존 `gunicorn` 별칭/충돌 차단, AWS 호출 없는 `readiness` 명령/로컬 영수증. 실제 설정 자동 변환 없음 |
| 정적 검증 | 테스트 112개 통과, CF 36개 lint 발견 0건, guard 24 PASS/12 SKIP/0 FAIL, 공개 후보 110개 파일 검사 발견 0건 |
| 설치 원본 | 변경 없는 원본 16개 해시 일치; AWS 패치 5개는 명시된 변경과 현재 코드 해시로 구분. 설치 artifact 다운로드/실행 검증과 별개 |
| 구성 보존 | 기존 실제 로컬 설정 보존. 샘플 CF 36개의 리소스 속성·Parameters·Conditions·Outputs 변경 없음; 버전/앱 설명 Metadata 정리만 반영 |
| 실제 배포 | 미실행. 5계정 bootstrap 완료는 18:05 KST 과거 확인이며 새 쓰기/서비스 사전 검증 없음 |
| 서비스 검증 | 미실행. 기반 설치/smoke·앱/ALB target·fencing/connector·실제 S3 단일 writer·삭제 후 새 세대 재생성 필요 |

현재 로컬 브랜치는 `feature/infra`이고 `origin`과 인프라 CI workflow 파일이 존재한다. 로컬 `main`도 있으나 원격 기본/통합 브랜치·권한/보호·CI 실행은 미검증이다. 공통 pr-gate/이슈·PR 템플릿/CODEOWNERS는 미구성이며 인프라 workflow 파일 존재와 구분한다. Git init/add/commit/push 및 원격 설정 변경을 수행하지 않았다.

## 다음 작업

1. 새 채팅에서는 루트 AGENTS.md·CONTRIBUTING.md, aws-infra/AGENTS.md·README.md·SECURITY.md와 이 디렉터리 문서를 읽고 로컬 config/상태를 확인한다. `readiness`로 AWS 호출 없는 준비 근거를 확인한다.
2. 실행 범위는 배포 전 준비다. 실제 배포는 사용자가 명시적으로 요청한 범위에서 수행하며 과거 명령 기록을 재실행하지 않는다.
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
