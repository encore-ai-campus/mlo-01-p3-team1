# AWS 인프라 실행기

작업 PC에서 AWS CLI + CloudFormation + SSM으로 **5개 독립 계정 · VPC 5개 · EC2 14대 · 물리 AZ 3개**를 생성·설치·검증·삭제·재생성한다.
Ubuntu/systemd에 직접 설치하며 Docker Compose는 사용하지 않는다.
기반 서비스와 AWS 운영은 인프라 담당, 제품 계약의 FastAPI 웹·Collector·Driver·광고 앱 배포는 팀원이 맡는다. [팀원 배포 규약](../docs/handoff/infra/TEAM-HANDOFF.md)을 따른다.
수정일: 2026-10-14. 제품·팀 공통 기준은 [루트 AGENTS](../AGENTS.md), AWS 설치·운영 기준은 [aws-infra/AGENTS](AGENTS.md)를 적용한다. ASGI 실행 서버/버전·worker 수는 별도 팀 실행 계약이며 기반 설치기는 업무 앱을 설치/시작하지 않는다.
코드 버전은 [VERSION](VERSION), 변경 내용은 [CHANGELOG.md](CHANGELOG.md)에 기록한다.
확정 설계와 배포 단계는 [배포 전 AWS 인프라 구축 계획서](<../docs/handoff/infra/AWS 인프라 구축 계획.md>)를 참고한다.
**전체 생성 → 설치 → 삭제 → 재생성의 실제 AWS 검증은 아직 완료되지 않았다.**
96시간은 비용 산정 기준이며 강제 유지 기간이나 자동 삭제 예약이 아니다.
확정 예산은 encore1~4 각 $45, encore5 $20, 합계 $200이며 실행기가 지출 상한을 강제로 보장하지는 않는다.

## 디렉터리

```text
저장소 루트/
├── .github/workflows/aws-infra-check.yml  # 코드 검사 CI; AWS 권한 없음
├── .gitignore                           # 저장소 루트에서 비밀/실행물 제외
├── aws-infra/
│   ├── aws-project.sh                   # 작업 PC 진입점
│   ├── bin/, lib/, config/, templates/
│   ├── installer/, tests/
│   ├── README.md, SECURITY.md, AGENTS.md
│   ├── VERSION, CHANGELOG.md
│   └── .state/, .private/, .local/, .tools/  # Git 제외 로컬 전용
└── docs/handoff/infra/
    ├── README.md                        # 문서 안내와 완료/미완료 상태
    ├── AWS 인프라 구축 계획.md
    └── TEAM-HANDOFF.md                   # 팀원 앱 배포 규약
```

공개 Git 이력에는 실행기·템플릿 생성 코드·샘플 설정·테스트·문서·버전을 남긴다.
실제 계정 ID, 인증서 ARN, InstanceId, 설치 비밀값과 실행 기록은 로컬 설정/상태에 남긴다.
기존 자료는 `.local/history/docs/`, `.local/distributions/`에 보존한다.
실행마다 문서를 만들지 않으며, 최종 인프라 구성 보고서는 구축 완료 후 정리한다.

## 로컬 설정

저장소 루트에서 `cd aws-infra`로 이동해 이 문서의 실행 명령을 사용한다. 기존 Git 저장소를 사용하며 aws-infra 안에 별도 Git 저장소를 만들지 않는다.

Python 3.12 이상, AWS CLI v2, Git을 사용한다. 기존 `encore1`~`encore5` 프로필을 유지한다.
encore2~5는 encore1 source profile로 `ProjectInfraRole`을 AssumeRole한다.
장기 Access Key를 저장소나 `.env`에 넣지 않는다. [AWS 액세스 키 보호 지침](https://docs.aws.amazon.com/IAM/latest/UserGuide/securing_access-keys.html)을 따른다.

새 checkout에서만 샘플을 복사하고 실제 값을 입력한다. 기존 로컬 설정을 덮어쓰지 않는다.

```bash
cp -n config/project.example.json config/project.json
chmod 600 config/project.json
```

로컬 파일의 `example_only`를 `false`로 바꾸고 계정 ID와 encore1의 `operator_principal_arn`을 입력한다.
계정 ID는 앞의 0을 보존하는 12자리 **문자열**이다.
공개 샘플의 `example_only=true`는 AWS 접근을 차단하며 오프라인 렌더링/테스트용이다.
AMI·AZ ID·CIDR 검토·포트·ALB 인증서/접속 CIDR/헬스 경로를 환경에 맞게 확정한다.
AMI 조회는 [Canonical 공식 이미지 조회 방법](https://ubuntu.com/aws/docs/aws-how-to/instances/find-ubuntu-images/)을 따른다.

## 배포 전 오프라인 준비 검사

현재 승인 범위에서는 저장소 루트에서 `cd aws-infra`로 이동한 뒤 다음 명령으로 로컬 준비를 확인한다.

```bash
./aws-project.sh --config config/project.json readiness
```

`readiness`는 AWS 로그인/조회·변경 세트·SSM·설치·삭제를 호출하지 않는다. 실제 설정을 변경하거나 설치 세대를 발급하지 않으며 `.state/readiness/latest.json`에 준비 근거만 기록한다. 입력 누락·설치 원본 해시·검증 도구 존재와 후속 앱/HA 통합을 구분한다. 미준비이면 종료 코드 1을 반환한다. 도구 존재는 lint/guard 통과나 AWS 권한 검증을 뜻하지 않는다.

웹 포트의 공개 키는 `service_ports.web`이다. 기존 `service_ports.gunicorn`도 같은 포트의 호환 별칭으로 읽으며 실제 로컬 설정을 자동 변환하지 않는다. 두 키가 다르면 차단한다. 별칭은 Gunicorn 사용 지시가 아니다. 예제/실제 설정 모두 무제한 CIDR을 차단한다.

## 배포 전 AWS 읽기 검증

```bash
./aws-project.sh --config config/project.json plan
./aws-project.sh --config config/project.json preflight
python3 bin/check-public.py
```

`preflight`는 계정 식별, bootstrap 템플릿/리소스/Outputs, 읽기 권한, AZ/AMI, EC2 사양·쿼터, VPC CIDR을 조회한다.
변경 세트·VPC·EC2·SSM 명령·ALB 생성이나 IAM 수정을 실행하지 않는다.
결과는 `.state/preflight/latest.json`에 저장하고 core 준비 여부와 ALB까지 포함한 준비 여부를 구분한다. 기본 명령은 전체 준비가 미완료면 실패 코드로 종료한다.
core 범위만 확인할 때는 `preflight --without-alb`를 명시한다.
읽기 검증은 실제 쓰기 권한이나 서비스 설치 성공의 증거가 아니다. 서비스 사전 검증은 향후 변경 세트 단계에서 수행한다.

검토한 LAN/VPN CIDR을 명시하면 공통 물리 AZ 3개와 Canonical AMI를 로컬 설정에 반영할 수 있다.
아래 CIDR은 예시이며 실제 접속망 목록으로 바꾼다.

```bash
./aws-project.sh --config config/project.json preflight --resolve-inputs --connected-cidr 192.168.0.0/24
```

## 실제 생성·삭제

아래 명령은 AWS 리소스를 변경한다. 실행 전 `plan`과 `preflight`를 확인한다.

```bash
./aws-project.sh --config config/project.json create --execute
./aws-project.sh --config config/project.json status
./aws-project.sh --config config/project.json destroy --confirm mlo-p3-team1-aws-dev
```

생성 순서는 network → storage → 7 peering/14 route → 14 EC2 → ALB다.
ALB 없이 core 범위만 배포할 때는 `create --execute --without-alb`로 지정한다.
기본 생성은 접속 CIDR·헬스 경로·포트가 미정이면 과금 리소스 생성 전에 중단한다. HTTPS 모드에서만 발급된 ACM 인증서가 추가로 필요하다.
`generation=null`이면 생성 시 새 설치 세대를 자동 지정한다. 실패 재개는 같은 세대를 유지하며 삭제 후 생성은 새 세대를 사용한다.

삭제는 ALB → 두 Control 종료 확인 → 나머지 EC2 → route/peering → 프로젝트 S3 버전·미완료 업로드 → network 순서다.
관리 IAM/bootstrap·Mac 프로필·음악 원본 S3·완료된 로컬 9VM은 유지한다.
AWS 신규 설치에서 기존 데이터 복구는 요구하지 않으며 Kafka offset/Spark checkpoint 초기화를 허용한다.

## 기반 서비스 setup과 ALB 후속 추가

인프라 생성 이후 다음 명령으로 기반 서비스를 설치·검증한다. 앱 소스는 선행 조건이 아니다.

```bash
./aws-project.sh --config config/project.json setup
./aws-project.sh --config config/project.json setup --execute
./aws-project.sh --config config/project.json verify --execute
```

`setup`은 단계 순서만 표시한다. `setup --execute`는 14개 노드 private package를 준비하고 SSM으로 빈 디스크 확인/초기화,
Kafka·Spark/ZooKeeper·ES·PostgreSQL·MongoDB와 Control/광고 호스트 디렉터리·TLS·DB 환경 파일을 준비한다.
전체 환경 lock, ZK/Master 단계 barrier, command receipt 재개를 적용한다. 결과가 불명확하거나 실패한 명령은 자동 재전송하지 않는다.
`verify --execute`는 새 영수증으로 기반 서비스의 health와 Kafka/Spark/ES/DB smoke를 수행한다.
Kafka/S3A connector lock, Spark→ES 앱 연동, 실제 앱 데이터 흐름과 Control fencing은 별도 범위다.
이 코드의 실제 AWS 설치·검증 실증은 아직 하지 않았다.

현재 로컬 설정은 **ALB 기본 DNS + 임시 HTTP 80**이다. 허용할 `/32` CIDR은 Git 제외 `config/project.json`에 확정해 반영했다. 실제 값은 공개 문서에 적지 않는다.
공개 샘플과 템플릿의 기본값은 HTTPS이며, 임시 HTTP는 로컬 `alb.protocol=HTTP`로 명시한다.
ALB 없이 먼저 코어만 만들려면 `create --execute --without-alb`를 사용한다.
이후 **alb 설정만** 확정한 뒤 다음 명령을 사용한다. 코어 설정·포트·설치 세대는 유지한다.

```bash
./aws-project.sh --config config/project.json add-alb --execute
```

`add-alb`는 후속 ALB 추가와 **alb 설정만 바꾸는 업데이트**에 사용한다. 도메인을 준비하면 서울 ACM 인증서를 발급하고
`alb.protocol=HTTPS`, `alb.certificate_arn`을 지정한 뒤 같은 명령으로 변경한다. ALB와 EC2/데이터의 정체성은 유지하며 접속 포트 변경 시 전용 SG ingress rule만 교체를 허용한다.
HTTP→HTTPS 전환 중 접속 변화/짧은 중단이 있을 수 있고 HTTPS에서는 인증서 도메인으로 접속해야 한다.
[AWS 공식 문서](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-troubleshooting.html)에 따르면 ALB 기본 DNS에 ACM 공개 인증서를 발급할 수 없다.
ALB 생성과 팀원 앱의 target health 확인은 구분한다. 허용 CIDR은 확정했고 도메인/인증서는 후속 HTTPS 단계에서 준비한다. 도메인은 HTTP 단계의 선행 조건이 아니다.
PostgreSQL 5432, MongoDB 27017, 웹 8000과 `/health/`를 기본 규약으로 준비했다.

## 구현 상태

최근 AWS 읽기 검증은 **2026-10-14 18:05 KST**에 수행했다. 5계정 bootstrap/Outputs 및 ALB 포함 사전 입력 검증을 통과했다.
당시 VPC·프로젝트 EC2·SSM 노드·ALB는 모두 0개였으며 실제 쓰기 권한·서비스 설치·전체 생성/삭제 실증은 대기 상태다.
최신 코드는 0.3.2이며 18:05 AWS 검증은 0.3.0 설정/코드 기준이다. 0.3.2는 지침/앱 호스트 설명과 오프라인 준비 검사를 정리했고 AWS 재조회·변경 세트·배포는 수행하지 않았다.

| 범위 | 상태 |
|---|---|
| IAM bootstrap, VPC·NAT·ENI·EC2·peering·S3·HTTP/HTTPS ALB | 템플릿·단계 실행기 구현, 로컬 검증 가능 |
| 전체 생성/삭제, 소유권·재개·S3 purge | 코드와 오프라인 테스트 구현; AWS 왕복 실증 대기 |
| Kafka·Spark/ZooKeeper·ES core 설치 | 기존 Ubuntu 코드 기반 AWS 설치기 구현; 실제 설치 검증 대기 |
| PostgreSQL·MongoDB | 버전/hash 고정, TLS/auth/재설치 보호 코드와 오프라인 검사 구현; 실제 설치 대기 |
| FastAPI 웹·Collector·Driver·광고 앱 | 팀원 배포/연동/검증 |
| Control 주/대기·fencing, connector/checkpoint 통합 | 팀 앱 lifecycle과 별도 연동·검증 필요 |

실제 bootstrap과 입력 준비 상태는 해당 PC의 `preflight`로 확인한다. EC2 running/SSM Online을 앱 완료로 해석하지 않는다.
encore2~5 bootstrap은 계정 소유자가 기존 스택에 업데이트한다.
network stack이 실제 VpcId를 boundary로 제한된 peering 역할에 연결하므로 반복 생성에 관리자 콘솔 수작업을 요구하지 않는 설계다.

## 코드 검증과 이력 관리

```bash
python3 bin/infra.py --config config/project.example.json render
python3 -m unittest discover -s tests -v
python3 bin/check-public.py
bash bin/check-local.sh
```

`check-local.sh`는 준비된 cfn-lint 1.57.2와 cfn-guard 3.2.1을 사용한다. 도구는 `.tools/`에 격리하며 자동 설치하지 않는다.
Python 검증 의존성은 `requirements-validation.txt`에 고정한다.
CI는 공개 파일 검사·오프라인 테스트·샘플 템플릿 일치 검사·cfn-lint만 실행하며 AWS 인증을 요구하지 않는다.
워크플로는 저장소 루트 `.github/workflows/aws-infra-check.yml`에 두고 `working-directory: aws-infra`로 실행한다.
공개 검사는 aws-infra와 공유 문서·루트 인프라 CI를 대상으로 한다. 저장소의 다른 기존 자료와 과거 Git 이력은 별도 검토 범위다.

코드 변경 시 테스트 통과 후 `VERSION`/`CHANGELOG.md`로 버전을 구분한다. Git commit/tag·push는 별도 명시 요청 때 수행한다.
실제 실행 영수증에는 코드 버전·Git revision(조회 가능할 때)·설정/템플릿 해시를 `.state/`에 기록한다.
비밀값을 Git에 넣어 배포 이력을 남기지 않는다. 공개 전 검사와 한계는 [SECURITY.md](SECURITY.md)를 따른다.
