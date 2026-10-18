# 팀원 AWS 전체 인프라 접속

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- 적용 범위: 사용자 요청에 따른 encore1~5 로그인 주체의 5계정 인프라 접근·배포·수정 권한과 개인 PC 접속 방법.

## 권한과 로그인 주체

각 계정의 기존 `student` IAM 사용자가 개인 PC에서 본인 계정으로 로그인한 뒤, 대상 계정의 `mlo-p3-team1-aws-dev-team-admin` 역할로 전환한다. 역할은 5개 계정의 지정된 `student` 사용자만 신뢰한다. 실제 계정 ID·사용자 ARN·역할 ARN은 공개 문서에 적지 않고 개인별 설정 파일에 둔다.

| 로그인 출발 계정 | 전환할 수 있는 대상 | 권한 |
|---|---|---|
| encore1 | encore1~5 | 전체 인프라 관리 |
| encore2 | encore1~5 | 전체 인프라 관리 |
| encore3 | encore1~5 | 전체 인프라 관리 |
| encore4 | encore1~5 | 전체 인프라 관리 |
| encore5 | encore1~5 | 전체 인프라 관리 |

각 역할에는 AWS 관리형 `AdministratorAccess`를 연결한다. EC2·SSM·CloudFormation·S3·IAM을 포함한 AWS 서비스/리소스 관리 권한이며, 삭제와 권한 변경도 포함한다. 조직 SCP·명시적 Deny·서비스별 자원 정책 등의 제한은 계속 적용된다. 역할 세션은 최대 1시간이며 로그인 세션이 유효하면 CLI가 역할 자격 증명을 다시 발급받는다. [AWS 관리자 정책](https://docs.aws.amazon.com/aws-managed-policy/latest/reference/AdministratorAccess.html), [계정 간 역할 접근](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies-cross-account-resource-access.html).

기존 인프라 실행기의 `ProjectInfraRole`과 bootstrap·CloudFormation 실행 역할은 유지한다. 팀원은 아래 `encore1-admin`~`encore5-admin` 프로필을 사용한다. 기존 Mac의 `encore2`~`encore5` 프로필은 운영 역할을 사용하는 기존 의미를 유지한다.

## 개인 PC 준비

AWS CLI v2.32.0 이상과 OS에 맞는 Session Manager 플러그인을 설치한다. AWS CLI 브라우저 로그인은 [공식 로그인 안내](https://docs.aws.amazon.com/signin/latest/userguide/command-line-sign-in.html), 플러그인은 [공식 설치 안내](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html)를 따른다. 현재 작업 Mac에서 확인한 버전은 CLI 2.37.10, 플러그인 1.2.896.0이다. 다른 팀원 PC의 설치·로그인 검증은 별도다.

인프라 담당자가 준비한 본인 계정용 `aws-config.ini`를 개인 PC의 `.aws/mlo-team-config.ini`로 복사한다. 파일에는 본인 로그인 주체와 대상 역할 주소만 있으며 Access Key·세션 토큰·비밀번호는 없다. 실제 계정 정보가 있으므로 Git에 올리지 않고 본인 PC의 AWS 로그인 캐시도 공유하지 않는다.

개인별 원본 파일은 현재 작업 PC의 Git 제외 경로 `aws-infra/.private/team-access/encoreN/aws-config.ini`에 있다. `encoreN`은 본인 로그인 계정이다. 각 파일에는 본인용 `encoreN-login`과 공통 대상 `encore1-admin`~`encore5-admin` 프로필이 들어 있다. 기존 AWS 설정 파일을 덮어쓰지 않고 별도 파일을 선택해 사용한다.

같은 디렉터리의 `console-switch-links.md`에는 AWS 콘솔에서 대상 계정으로 역할을 전환하는 링크 5개가 있다. 본인 계정의 `student`로 콘솔에 로그인한 뒤 대상 링크를 사용한다. 이 파일도 실제 계정 정보가 있으므로 공개 저장소에 올리지 않는다.

macOS/Linux에서 encore2 사용자의 예:

```bash
export AWS_CONFIG_FILE="$HOME/.aws/mlo-team-config.ini"
aws login --profile encore2-login --region ap-northeast-2
aws sts get-caller-identity --profile encore1-admin
```

Windows PowerShell에서 같은 예:

```powershell
$env:AWS_CONFIG_FILE = "$env:USERPROFILE\.aws\mlo-team-config.ini"
aws login --profile encore2-login --region ap-northeast-2
aws sts get-caller-identity --profile encore1-admin
```

브라우저에서는 본인 계정의 `student`로 로그인한다. `encore2-login`은 encore2의 로그인이고 `encore1-admin`은 encore1의 관리자 역할이다. 다른 계정 사용자도 본인의 `encoreN-login`으로 로그인한 뒤 같은 대상 관리자 프로필을 선택한다. 루트 로그인이나 다른 사용자의 자격 증명은 사용하지 않는다.

현재 작업 Mac의 플러그인은 시스템 설정을 변경하지 않고 Git 제외 `aws-infra/.tools/bin/session-manager-plugin`에 준비했다. 이 Mac에서 CLI 세션을 열 때는 저장소 루트에서 다음을 실행한다.

```bash
export PATH="$PWD/aws-infra/.tools/bin:$PATH"
session-manager-plugin --version
```

## 대상 EC2 조회와 SSM 접속

설정 파일을 선택하고 본인 로그인을 마친 뒤, 대상 계정의 관리자 프로필로 프로젝트 EC2를 찾는다. 아래는 encore1의 예이며 다른 계정은 프로필 번호를 바꾼다.

```bash
aws ec2 describe-instances --profile encore1-admin --region ap-northeast-2 \
  --filters Name=tag:Project,Values=mlo-p3-team1 Name=tag:Environment,Values=aws-dev Name=instance-state-name,Values=running \
  --query 'Reservations[].Instances[].{Name:Tags[?Key==`Name`]|[0].Value,Id:InstanceId}' --output table

aws ssm describe-instance-information --profile encore1-admin --region ap-northeast-2 \
  --query 'InstanceInformationList[].{Id:InstanceId,Status:PingStatus}' --output table

aws ssm start-session --profile encore1-admin --region ap-northeast-2 --target <INSTANCE_ID>
```

`<INSTANCE_ID>`는 조회한 실제 값으로 바꾼다. EC2가 `running`이고 SSM 상태가 `Online`이어야 한다. EC2는 public IP나 inbound SSH 없이 관리하며 접속을 위해 22번 포트를 열지 않는다. 인프라 생성·설치 진행 중에는 EC2나 SSM 목록이 비어 있거나 아직 `Online`이 아닐 수 있다.

기본 SSM 셸의 `ssm-user`는 관리자 명령을 실행할 수 있다. 이번 전체 관리 권한 요청에 맞춰 이 동작을 유지하며, 이후 담당별 배포 제한을 도입한다면 IAM과 OS 사용자·sudo 권한을 함께 조정한다. [AWS SSM 사용자 권한](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-getting-started-ssm-user-permissions.html).

## 배포와 검증 범위

앱 위치·서비스 사용자·DB/TLS·Control HA 계약은 [팀원 배포 규약](TEAM-HANDOFF.md)을 따른다. AWS 관리자 역할은 PostgreSQL·MongoDB·Kafka·Elasticsearch의 앱 로그인이나 업무 데이터 권한을 대신하지 않는다. 앱 배포와 서비스 변경은 진행 중인 인프라 설치와 일정을 맞춘다.

IAM 추가·읽기 확인·25개 출발/대상 조합의 역할 전환 결과는 Git 제외 `aws-infra/.state/team-access/`에 기록한다. 역할 전환·자원 조회 성공, 실제 SSM 세션, 기반 서비스 상태와 업무 앱 배포 성공을 각각 구분한다. 현재 인프라 생성·설치 작업의 완료 근거는 해당 실행 영수증을 확인한다.

2026-10-15 확인 결과: 5계정 역할 생성·신뢰 정책·관리자 정책 읽기 확인 완료, 25개 조합의 역할 전환·EC2/SSM 조회 통과, 개인별 CLI 설정 5개의 실제 역할 연결 통과. 이 검증 시점에 프로젝트 EC2·SSM 노드는 0대였으므로 실제 SSM 셸 접속과 앱 배포·수정 실행은 검증하지 않았다. EC2 생성·SSM 등록 후 실제 접속을 추가 확인한다.
