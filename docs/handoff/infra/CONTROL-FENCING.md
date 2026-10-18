# Control fencing 실행기와 적용 전 검토

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- 코드 기준: 0.3.14. 구현·로컬 검사 안내이며 실제 설치/활성화·EC2 중지·S3 승계 성공 기록은 아니다. 실행 원문은 `.state`, 비밀 payload는 `.private`에 둔다.

## 1. 구현과 적용 경계

`aws-infra/lib/control_coordinator.py`는 기존 ZooKeeper의 TLS 서버 이름/CA·클라이언트 인증과 필수 SASL을 유지한다. 별도 digest identity가 Control 전용 경로의 ACL을 소유한다. ephemeral-sequential 선출과 영속 epoch/owner의 버전 CAS를 사용하며 연결이 한 번 상실되면 재연결돼도 같은 실행 권한은 복원하지 않는다. 재시도에서 경로·epoch·owner·offset·checkpoint를 초기화하지 않는다.

`control_runtime.py`는 검토한 세대의 정확한 Control peer instance/ENI/VPC와 태그를 대조하고, 필요하면 그 peer만 StopInstances로 중지한다. stopped/terminated를 실제 확인하기 전에는 승계하지 않는다. 강제 중지·종료·자동 시작은 제공하지 않는다. 이 방식은 이전 Control 전체를 중지하므로 해당 호스트의 웹/다른 프로세스에도 영향을 준다.

`control_observation.py`는 세 Spark 노드 각각의 고정 관측 문서를 호출한다. 실제 document version/SHA256·새 nonce·CommandId/InstanceId·전체 성공 상태를 대조하고 로컬 Master/Worker UI와 잔여 Driver/executor/Python worker를 검사한다. 세 Worker와 단일 Master의 membership이 일치하고 클러스터 전체가 idle이어야 한다. 관측 누락·스키마 변경·시간 초과·다른 앱 실행은 승계를 차단한다. 과거 JSON 영수증을 승계 권한으로 사용하지 않는다.

`control-runner.py`는 승계 허가 후 foreground 프로세스 그룹을 감독하며 lease 상실 시 SIGTERM/SIGKILL로 종료한다. systemd의 `KillMode=control-group`, `Restart=no`를 함께 사용한다. 기존 owner는 로컬 종료와 Spark idle이 확인된 정상 종료에서만 CAS로 해제한다. 불확실하면 영속 owner를 보존한다.

0.3.14의 `TimeoutStopSec=180`은 로컬 프로세스 종료·최대75초의 실제 Spark 관측·owner CAS가 정상 종료 중 완료될 시간을 확보한다. lease 상실 시 로컬 프로세스 그룹 종료는 즉시 진행한다. 기존 설치본에 종료 대기만 보완할 때는 별도 drop-in과 영수증으로 추적하며 설치 source identity를 바꾸지 않는다. 시험 중 추가한 실행시간 제한과 임시 unit은 시험 종료 후 별도로 정리한다.

현재 패키지 생성기는 **인프라 canary만** 준비한다. 업무 소스·migration·업무 systemd unit은 배포하지 않는다. 기본 create/setup/verify는 fencing을 적용하거나 활성화하지 않는다. 병렬 query의 선택적 fencing은 구현하지 않았으며 업무 적용 전 Control 전체 writer를 한 감독 범위에 묶는 계약이 필요하다. 여러 query가 서로 다른 Control을 중지하는 구성으로 확대하지 않는다.

## 2. 별도 IAM/SSM 변경안

`bin/control-fencing.py render-proposal`은 Git 제외 `.state`의 새 디렉터리에 템플릿·파라미터·적용 순서 4개를 생성한다. AWS 호출/변경 세트/배포는 하지 않는다.

| 순서 | 계정 | 변경 |
|---|---|---|
| 1~3 | encore2~4 | 해당 Spark 한 대의 고정 읽기 전용 SSM Document와 observer 역할 |
| 4 | encore1 | 기존 Control A/B runtime 역할에 정확한 peer ARN의 중지 권한과 observer 역할 AssumeRole 권한 추가 |

observer trust는 두 Control role ARN과 세대별 ExternalId로 제한한다. 호출 입력은 nonce 하나뿐이며 임의 명령·URL·파일·주소를 받지 않는다. Control에는 AWS-RunShellScript/PassRole/IAM 변경/StartInstances/TerminateInstances를 허용하지 않는다. 관측 결과 읽기 API는 리소스 단위 제한을 지원하지 않아 해당 계정·리전의 Run Command 결과를 읽을 수 있다는 범위가 남는다. 실제 업무 secret이 Run Command 출력으로 유출되지 않도록 기존 비밀값 출력 금지를 유지한다.

기존 제한된 CloudFormation 실행 역할은 자신에게 이 권한을 부여할 수 없다. 명시 적용 요청 후 계정 소유자/관리자 권한으로 검토·적용한다. 현재 Mac encore 프로필을 덮어쓰거나 새 장기 키를 요구하지 않는다. 기존 runtime trust와 나머지 권한은 보존한다. EC2 ID가 바뀌면 변경안을 다시 생성·검토한다. 현재 EC2에 없는 Generation 태그를 있다고 가정하지 않으며 정확한 instance/ENI 매핑으로 세대를 고정한다.

## 3. 준비 명령과 실제 적용 순서

명령은 저장소 루트에서 `cd aws-infra` 후 실행한다. 아래 plan만 즉시 실행 가능한 오프라인 검사다.

```bash
./aws-project.sh --config config/project.json control-plan
```

다음은 검토한 입력 경로로 실행하는 준비 명령 형식이다. 기존 상태 파일의 명령을 자동 재실행하지 않는다.

```bash
python3 bin/control-fencing.py --config config/project.json render-proposal \
  --inventory <reviewed-inventory.json> --out .state/<new-proposal-directory>
python3 bin/control-fencing.py --config config/project.json prepare \
  --inventory <reviewed-inventory.json> --bindings .private/<reviewed-bindings.json> \
  --query infra-canary
```

적용 시 먼저 실제 계정/세대/instance/ENI/VPC와 모든 변경 리소스를 재확인한다. observer 3개를 적용한 뒤 실제 Outputs와 document version/SHA256을 조회해 비공개 bindings에 기록하고 Control 권한을 적용한다. bindings에는 generation, 두 Control의 instance/ENI/VPC, 세 Spark의 instance/observer role ARN/document/version/hash, 검토한 Linux AWS CLI v2 절대 경로·정확한 버전이 필요하다. 가짜 버전/hash나 예상 Outputs로 runtime을 만들지 않는다.

Control에는 검토한 AWS CLI v2가 선행 설치돼야 한다. 0.3.13의 `installer/aws-cli.py`와 `aws-cli.lock.json`은 공식 버전별 ZIP/서명·공개 키 SHA256 및 signer fingerprint를 고정한다. 기존 `gpgv`로 서명을 확인한 뒤에만 추출하고 `/opt/music-cluster/aws-cli` 전용 경로에 설치한다. 글로벌 CLI/PATH·Mac 프로필·앱 venv를 바꾸지 않고 부분 설치나 다른 버전은 자동 덮어쓰지 않는다. 설치 전 실제 Control IMDS와 마운트 세대를 확인하며 기본 setup에는 자동 포함하지 않는다.

 runtime은 EC2 instance profile만 사용하고 로컬 AWS 환경 변수·프로필을 상속하지 않는다. 현재 준비는 CLI 설치나 권한 적용 완료를 뜻하지 않는다. wheel은 별도 lock의 SHA256으로 확인하고 전용 venv에 오프라인 설치하며 앱 venv를 변경하지 않는다.

설치기는 Control 사용자가 매 실행에서 세대를 확인할 수 있도록 해당 Control의 `.aws-volume-identity.json` 메타데이터 파일만 root 소유/Control 그룹 읽기 0640으로 설정한다. 내용은 보존하고 그룹 쓰기는 허용하지 않는다. 비밀값/CA 개인키를 이 marker에 넣지 않으며 다른 노드의 marker나 데이터 권한은 변경하지 않는다. AWS CLI 내부 재시도도 1회로 제한해 응답이 불명확한 쓰기 요청을 자동 재전송하지 않는다.

준비한 두 payload는 기존 14노드 기반 패키지를 덮어쓰지 않는다. `send-install --query infra-canary --node <control-a|control-b> --receipt .state/<new-receipt.json> --execute`는 별도 명시 설치이며 unit을 disabled 상태로 두고 시작하지 않는다. 실행 전 설치 결과/CommandId를 확인하며 응답이 불명확하면 재전송하지 않는다.

그 뒤 실제 Control에서 고정된 runtime과 runner로 **bootstrap → inspect → supervise**를 각각 명시 실행한다. bootstrap은 전용 ZK 경로를 만들지만 기존 owner/epoch를 덮어쓰지 않는다. inspect는 읽기 관측만 하며 선출/앱 시작을 하지 않는다. supervise와 unit 시작은 이전 Control을 실제 중지할 수 있으므로 물리 fencing 시험의 승인·중단/복구 계획을 확인한 뒤 실행한다. 이 문서는 실행 승인이나 unit 자동 시작 명령이 아니다.

최초 활성화/승계 구간에는 우회 Spark 제출과 감독 밖 writer가 없도록 운영 구간을 확보한다. idle 관측 자체는 새 제출을 막는 admission lock이 아니며 S3가 epoch를 검증해 쓰기를 거부하는 기능도 구현하지 않았다. 모든 writer가 이 감독 범위에 속한다는 조건과 실제 동시 writer 차단 시험 전에는 단일 writer 보장을 선언하지 않는다.

## 4. 서비스 수용과 복구 조건

1. 별도 canary로 인증/ACL·단일 선출·CAS·lease 상실 시 프로세스 종료를 확인한다.
2. 물리 peer 중지와 실제 stopped 상태, 남은 Spark 작업 종료, 새 owner/epoch를 확인한다. 요청 수락이나 SSM Success만으로 완료하지 않는다.
3. 고유 S3 시험 query와 동일 checkpoint에서 승계 전후 중복/손실·동시 writer 차단을 확인한다. 순차 checkpoint 재시작 성공과 구분한다.
4. 그 후 팀 앱의 foreground start/stop·health·client-mode Driver·checkpoint/query 소유 계약을 연결한다. 업무 source 확보는 앞선 인프라 준비의 선행 조건이 아니다.

StopInstances로 중지한 peer를 자동 재시작하지 않는다. 운영자가 이전 프로세스·owner·executor 상태와 서비스 영향을 검토한 뒤 복구한다. 같은 노드가 영속 old owner로 남았을 때 자기 자신 중지를 우회하지 않으며, owner/epoch 수동 삭제로 해결하지 않는다. 이전 세대 ACL/상위 경로가 다른 identity에 속하면 자동 재설정하지 말고 소유자를 확인해 명시 정리한다.

원복은 두 supervisor의 종료와 실제 작업 종료를 먼저 확인하고 owner 기록을 보존한 뒤 별도 unit을 비활성화한다. IAM/SSM 스택 제거는 활성 실행기가 없음을 확인한 별도 변경이다. 기본 destroy는 이 opt-in 스택을 자동 추적하지 않으므로 명시 제거가 선행되지 않으면 IAM/SSM 잔여가 생길 수 있다. 전체 삭제/새 세대 재생성의 수용 범위에 이 잔여 확인을 포함한다. 기존 데이터·음악 원본 S3·프로젝트 외 리소스는 삭제하지 않는다.

근거: [ZooKeeper 레시피](https://zookeeper.apache.org/doc/r3.9.4/recipes.html), [Kazoo 인증·TLS 옵션](https://kazoo.readthedocs.io/en/stable/api/client.html), [SSM 파라미터 환경 변수](https://docs.aws.amazon.com/systems-manager/latest/userguide/documents-schemas-features.html).
