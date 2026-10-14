# AWS 인프라 작업 지침

- 수정일: 2026-10-14

루트 [AGENTS.md](../AGENTS.md)는 제품·팀 공통 계약, 이 파일은 AWS 설치·운영 자동화의 세부 기준이다. 제품 기능·담당·React/TypeScript/Vite/FastAPI 기준을 AWS 호스트 설명으로 변경하지 않는다. 수령 원문은 이력으로 보존하고 최신 구축 계획·TEAM-HANDOFF의 정리된 앱 호스트 규약을 따른다.

이 디렉터리와 하위 작업에 적용한다. README.md, SECURITY.md와 저장소 루트의 docs/handoff/infra/README.md·설계/팀원 배포 문서를 읽고 사용자의 최신 지시를 우선한다.
과거 기록은 `.local/history/docs/`에 보존하며 실행 승인으로 사용하지 않는다.
현재 단계는 기반 서비스 자동 설치와 배포 전 준비다. 업무 앱은 팀원이 해당 EC2에 배포한다. 새 배포 요청 없이 리소스나 변경 세트를 생성하지 않는다.

## 목표와 확정 구성

- 작업 PC에서 AWS CLI + CloudFormation + SSM으로 전체 생성·설치·검증·삭제·재생성을 자동화한다.
- 서울 리전, 5개 독립 계정/5 VPC/14 EC2/3 물리 AZ를 유지한다. 실제 계정 ID는 Git 제외 `config/project.json`에서 읽는다.
- encore1: Control A/B, PostgreSQL. encore2~4: 각각 Kafka/Spark·ZooKeeper/ES 한 대씩. encore5: 광고 서비스/MongoDB 각각 독립 EC2.
- 데이터 클러스터별 세 AZ 분산, Control 두 대는 서로 다른 AZ. AZ 이름 대신 AZ ID를 사용한다.
- VPC별 zonal NAT 하나(총 5개), NAT AZ 장애 시 공유 외부 통신 중단을 수용한다.
- Peering 1-2/3/4/5, 2-3/4, 3-4의 7쌍. 중복 없는 CIDR, 고정 사설 IP와 별도 ENI를 검증한다.
- EC2는 private subnet, ALB는 encore1의 두 AZ public subnet. 사용자 결정대로 ALB 기본 DNS에서 임시 HTTP와 제한된 접속 CIDR을 사용한다. 소유 도메인/ACM 준비 후 HTTPS로 전환한다.
- 1안 T3 Standard 예산: encore1~4 각 $45, encore5 $20, 총 $200. 96시간은 비용 산정 기준이며 강제 유지/자동 삭제 요구가 아니다.
- Ubuntu/systemd에 신규 직접 설치한다. Docker Compose/Kubernetes/RDS로 임의 변경하지 않는다.
- 완료된 로컬 9VM을 재설치하거나 기존 네트워크를 변경하지 않는다.

## 인증·공개 파일

- 기존 Mac encore1~5 프로필을 사용한다. encore2~5는 encore1 source profile로 ProjectInfraRole을 AssumeRole한다.
- 장기 Access Key를 수집하지 않는다. 세션 만료와 권한 부족을 구분한다.
- Mac 운영/CF 실행/EC2 runtime/peering 역할을 분리하고 PassRole을 필요한 역할로 한정한다.
- bootstrap은 계정 소유자가 적용한다. trust/boundary는 관리자 범위이며 CF 실행 역할은 boundary로 제한된 peering inline policy만 연결한다.
- SignInSessionArn의 Null=false는 세션 문맥 존재 조건이며 직접적인 MFA 증명이 아니다.
- AWS 키·세션·비밀번호·TLS 개인키·private runtime·실제 설정·실행 기록을 공개 파일이나 도구 출력에 넣지 않는다.
- 공개 샘플은 가상 계정 ID와 example_only=true를 유지한다. 실제 템플릿은 `.state/`에만 생성한다.
- 사용자 지시 없이 git init·commit·push를 하지 않는다. 공개 전 check-public.py와 관련 검증을 실행한다.

## 설치·Control·데이터

- 검증 버전/원본 해시는 installer/core/versions.json과 installer/source-manifest.json을 따른다.
- Hyper-V/WinNAT/WireGuard/로컬 Netplan/Windows ProxyJump 코드를 EC2에 적용하지 않는다.
- 설치기는 preflight, 환경/노드 식별, lock, 버전/checksum, 단계 상태와 재개 기능을 갖춘다.
- Control 양쪽에 팀의 FastAPI 웹 앱을 배포할 호스트를 준비한다. ASGI 서버/버전·worker 수·실행 명령은 B/C와 INF의 별도 실행 계약으로 정하며 기반 설치기가 업무 앱을 설치/시작하지 않는다. Collector/Driver/스케줄러는 하나의 active에서 실행한다.
- ZooKeeper Control 전용 경로/ACL과 리더 선출을 쓰되, 이전 프로세스/Driver/Spark application 종료를 확인한 뒤 승계하는 fencing을 구현·검증한다.
- Spark Master HA와 Driver/Control HA 완료 상태를 구분한다. PG/Mongo 기반 설치는 인프라 담당, FastAPI 웹·Collector·Driver·광고 앱 배포/연동은 팀원 담당이다. 앱 소스 확보를 인프라 준비의 선행 조건으로 두지 않는다. Control fencing은 팀 앱 lifecycle과 별도 연동·검증한다.
- checkpoint는 S3 Standard의 환경/설치 세대/query별 prefix. 동시 writer는 하나이며 runtime 역할/bucket policy로 접근한다.
- AWS 재설치에서 데이터 복구는 필수 요구가 아니다. 전체 신규 설치의 Kafka offset/checkpoint 초기화를 허용한다.
- 재시도·재시작·Control 승계가 데이터를 자동 초기화하지 않도록 초기화 모드를 명시한다.
- ENI 해제 전에 동일 ENI로 새 EC2를 선생성하지 않는다. IP 변경 시 설정/인증서 SAN을 갱신하고 TLS 검증을 끄지 않는다.
- 음악 원본 S3와 프로젝트 외 데이터는 삭제하지 않는다. 피드백 중복/offset/JDBC 정합성은 앱 로직에서 검증한다.

## 검증·운영 기록

- 계획·구현·정적 검증·실제 배포·서비스 검증을 구분한다. EC2 running/SSM Online을 서비스 성공으로 간주하지 않는다.
- 실제 성공 검증에는 quorum/membership/TLS, Kafka 생산·소비, Spark 작업, ES 읽기·쓰기, S3 checkpoint 쓰기, 앱 흐름, 삭제 후 신규 설치가 필요하다.
- 기존 사용자 변경을 덮어쓰지 않는다. 삭제는 소유권/태그/allowlist, 의존성 역순, 실제 잔여 조회로 한정한다.
- destroy는 관리 IAM/프로필을 유지한다. VpcId 연결을 매번 소유자 콘솔 수작업으로 요구하지 않는다.
- 실행 영수증은 `.state/`, 비밀 payload는 `.private/`. 실행마다 docs 결과를 만들지 않는다.
- 공개 코드 이력은 VERSION/CHANGELOG와 Git으로 추적한다. 최종 구성 보고서는 구축 완료 후 작성한다.

## 저장소 구조

- 기존 Git 저장소 루트 아래 aws-infra에서 명령을 실행한다. 공유 문서는 ../docs/handoff/infra, CI는 ../.github/workflows/aws-infra-check.yml에 둔다.
- 최근 AWS 읽기 검증(2026-10-14 18:05 KST)은 ALB 포함 입력 준비 통과, 워크로드 0개다. 새 배포 지시 전까지 실제 생성/설치 완료로 표현하지 않는다.
- 실제 CIDR은 config/project.json에만 보관한다. 현재 코드의 0.0.0.0/0 차단을 질문만으로 해제하지 않는다.
- `readiness`는 로컬 준비 검사이며 AWS 로그인/조회·변경 세트·SSM·배포를 호출하지 않는다. `preflight`의 AWS 읽기 검증과 실제 변경 단계의 서비스 사전 검증을 구분한다. 결과는 `.state/`에 기록한다.
- 웹 포트의 공개 키는 `service_ports.web`이다. 기존 `gunicorn`은 호환 별칭이며 Gunicorn 채택을 뜻하지 않는다. 기존 실제 설정을 자동 변환하지 않고 두 키가 충돌하면 차단한다.
