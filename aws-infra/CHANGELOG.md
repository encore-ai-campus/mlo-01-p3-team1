# 코드 변경 이력

실제 실행 결과는 `.state/`에 보관한다. 이 파일은 공개 가능한 코드 변경만 기록한다.

## 0.3.19 — 2026-10-15

- 앱 실행 계약의 형식·평문 비밀값·foreground argv·고정 버전/lock 참조·세대/query별 checkpoint 검사를 추가한다. 잘못된 입력과 미정을 구분하고 앱 소스·임의 ASGI 채택 없이 준비한다.
- 로컬 `.state`에 잠금 의존성/설정 참조·담당별 미입력 목록·검토 템플릿을 묶는 인계 도구를 추가한다. 유효한 입력이 모두 있을 때만 두 Control 웹 unit과 supervisor patch 검토안을 생성하며 설치/enable/실행·canary runtime/epoch/checkpoint 변경은 제공하지 않는다.

## 0.3.18 — 2026-10-15

- 기존 MongoDB SG에 두 Control의 정확한 /32·27017만 추가하는 설계를 반영한다. 광고 접근과7쌍 Peering·기존 ENI/EC2/볼륨을 유지한다.
- 별도 weather/weather_app SCRAM-SHA-256·readWrite 프로비저닝과 Control 전용0640 환경 파일, 해시 고정 mongosh 격리 클라이언트·소량 권한 검증을 제공한다. 기존 사용자·설정의 덮어쓰기/회전·업무 데이터/체크포인트 초기화를 금지한다. 기본 setup은 기존14payload를 자동 갱신하지 않는다.

## 0.3.17 — 2026-10-15

- ES Spark JAR 없이 기존 HTTPS/CA·pipeline_writer로 실행하는 별도 Driver-side REST/Bulk probe를 추가한다. 고유 시험 index/18행·동일 ID 재전송·부분 오류 거부를 검사하며 기본 setup/verify나 업무 앱 전송 방식을 바꾸지 않는다.
- 앱 소스 없이 MongoDB의 직접 경로와 목적지 ingress를 각각 검사하는 오프라인 실행 계약 계획기를 추가한다. 광고 전용 DB 권한과 날씨 writer/DB, ASGI·단일 active 실행 인계의 미정을 보존한다.

## 0.3.16 — 2026-10-15

- 비공개 설치 umask0077에서도 새 공개 addon 상위 디렉터리를0755로 설정해 Spark/Control 사용자가 JAR를 읽을 수 있도록 한다. JAR는0644, runtime/인증정보의 비공개 권한은 유지한다.
- 동일 lock/세대의 addon 재검증에서는 최초 설치 source marker를 보존한다. 손상된 파일·다른 세대/lock은 계속 차단한다.

## 0.3.15 — 2026-10-15

- Spark4.1.3/Delta4.3.1의 별도 additive lock과9개 JAR 설치기를 추가한다. 기존286개 Spark/8개 Kafka·S3A JAR를 대조하고 전역 classpath/설정 대신 해시별 addon 경로에 원자적으로 게시한다.
- IMDS/역할/마운트 세대를 확인하고 기존 payload/source marker·비밀값을 보존한다. 작업별 명시 `--jars`와 Delta 세션 설정으로 연결하며 기본 setup/verify에 자동 포함하지 않는다.

## 0.3.14 — 2026-10-15

- Control supervisor의 정상 종료 시 프로세스 종료와 최대 75초의 실제 Spark 관측·owner CAS를 마칠 수 있도록 systemd 종료 대기를 180초로 조정한다. 연결 상실 시 즉시 업무 프로세스 그룹을 종료하는 동작과 Restart=no는 유지한다.
- 기존 설치 source identity는 덮어쓰지 않으며 시험용 unit에도 같은 종료 예산을 명시한다.

## 0.3.13 — 2026-10-15

- Control 전용 AWS CLI v2 설치기를 추가한다. 공식 버전별 ZIP/서명/공개 키의 SHA256과 AWS signer fingerprint를 고정하고 gpgv 검증 후에만 추출·설치한다.
- 전용 `/opt/music-cluster/aws-cli` 경로를 사용하며 기존 CLI·전역 PATH·Mac 프로필·앱 venv를 바꾸지 않는다. 부분 설치/다른 버전은 자동 덮어쓰기·업그레이드하지 않으며 IMDS/Control 역할/디스크 세대를 먼저 확인한다.
- 기본 setup에 자동 포함하지 않는 명시 단계다. 기존 기반/connector 패키지와 배포 source identity를 보존한다.

## 0.3.12 — 2026-10-15

- TLS·SASL·전용 digest ACL의 ZooKeeper 선출, 영속 owner/epoch CAS, 정확한 이전 Control EC2 중지 확인과 전체 Spark Master/Worker 종료 관측 실행기를 추가한다. 연결 상실은 재연결 후에도 실행 권한을 되살리지 않으며 로컬 프로세스 그룹을 종료한다.
- 정확한 peer 중지 권한 1개와 고정 읽기 전용 Spark 관측 IAM/SSM 3개의 별도 검토안을 렌더링한다. 기본 create/setup에 포함하지 않으며 EC2 생성·보안그룹·업무 앱·checkpoint를 변경하지 않는다.
- 해시를 고정한 별도 Control canary payload와 disabled systemd unit 설치 단계를 제공한다. 설치·ZK bootstrap·활성화는 각각 명시 실행이며 기존 14노드 기반 payload와 실행 영수증을 보존한다.
- `control-plan`으로 구현/준비와 미설치·미검증 상태를 구분한다. 실제 물리 fencing·S3 동시 writer 승계 및 앱 통합은 별도 검증 대상이다.

## 0.3.11 — 2026-10-15

- Kafka/S3A 전이 의존성 lock과 원본 Spark JAR 전체 SHA256을 고정한다. Spark의 SLF4J/Snappy/Scala를 유지하고 Maven Central만 사용하며 변경·중복 JAR와 불완전 bundle을 차단한다.
- connector bundle을 명시한 private package만 connectors/checkpoint-smoke에 사용한다. 기본 setup/verify는 해당 단계를 자동 실행하지 않는다. `integration-plan`은 AWS 호출 없이 준비 상태와 남은 실행 조건을 표시한다.
- 고유 시험 prefix에서 동일 Structured Streaming checkpoint의 순차 재시작을 검증하는 probe와 fail-closed Control 승계 판정 로직을 추가한다. 실제 S3 단일 writer/HA 완료를 선언하지 않으며 live ZK/EC2/Spark 연동은 별도다.

## 0.3.10 — 2026-10-15

- MongoDB 저장소 공개 서명 키에 apt가 읽을 수 있는 0644를 적용한다. 이전 0600 키가 남은 재시도도 첫 저장소 갱신 전에 복구한다. 개인키·runtime·DB 데이터 권한과 서명/패키지 해시 검증은 유지한다.
- 신규 설치와 기존 공개 키를 사용하는 재시도에서 apt 갱신 전에 읽기 권한을 검증하는 회귀 검사를 추가한다.

## 0.3.9 — 2026-10-15

- Spark 설치 전 ZooKeeper quorum 검증에서 이미 설치된 ZooKeeper TLS 디렉터리를 사용. CA·클라이언트 인증·호스트 검증과 leader/follower 판정은 유지.
- Spark 인증서가 없는 상태에서 ZooKeeper 인증서만으로 quorum 검증이 가능한지 회귀 검사. 서비스·저장 데이터·비밀값 재생성 없이 검증 단계를 재개.

## 0.3.8 — 2026-10-15

- AWS의 nominal RAM과 커널 예약 후 guest MemTotal을 구분. AWS guest 최소 93% 검사와 정확한 IMDSv2 instanceType 대조를 적용하며 로컬 VM의 기존 94% 기준·확정 EC2 사양은 유지.
- 정상 4GiB guest의 예약 메모리·실제 용량 부족·잘못된 인스턴스 종류·로컬 기준 보존을 회귀 검증. 성공 단계 재개와 데이터/offset/checkpoint 보호는 유지.

## 0.3.7 — 2026-10-15

- SSM 문서마다 다른 step 이름을 고정하지 않고 CommandId/InstanceId가 일치하는 전체 invocation 상태를 확인. 다운로드와 실행을 포함한 명령 전체가 완료돼야 성공으로 처리.
- eventual consistency의 미조회 상태·실행 중·실패·대상 식별자 불일치 회귀 검증. 관찰 오류로 명령을 자동 재전송하거나 디스크·offset/checkpoint를 초기화하지 않음.

## 0.3.6 — 2026-10-15

- ALB의 EC2 계정 속성 조회에 필요한 `ec2:DescribeAccountAttributes` 한 동작을 encore1 CloudFormation 실행 역할에만 서울 리전 읽기로 추가. 다른 계정·운영 역할·쓰기 권한은 유지.
- 해당 읽기 예외의 계정/역할/리전 범위를 회귀 검증. 실제 적용·실패 원인·재개 기록은 `.state/`에서 관리.

## 0.3.5 — 2026-10-14

- ARN 제한 방식으로 동작하지 않는 DescribeEvents 조회 한 동작을 서울 리전 읽기 예외로 처리. 다른 생성·삭제·PassRole·IAM 권한의 기존 제한은 유지.
- bootstrap 렌더링에서 비공개 과거 변경 세트 ARN에 대한 의존 제거. 실제 템플릿과 실행 영수증은 계속 `.state`에만 보관.
- 태그 없는 중단 CREATE 변경 세트는 동일 영수증·실행 역할·소유 태그·빈 리소스 검증을 유지하며 재개.

## 0.3.4 — 2026-10-14

- DescribeEvents 조회는 스택 적용용 Tags 대신 프로젝트/계정 이름이 들어간 change-set ARN과 서울 리전으로 제한.
- 변경 세트 이름에 프로젝트/계정 prefix 적용; 기존 중단 변경 세트는 비공개 영수증의 계정/리전/프로젝트 일치 ARN만 정확한 읽기 예외로 인계. 공개 샘플은 실제 상태를 읽지 않음.
- REVIEW_IN_PROGRESS의 실행 역할은 실제 API가 제공하는 Stack.RoleARN으로 검증; change set 역할 필드가 있으면 충돌도 차단.
- 실제 관리 권한을 확인한 계정만 bootstrap 보완을 실행하고 다른 계정의 권한 거부는 기록/보존.

## 0.3.3 — 2026-10-14

- DescribeEvents의 stack/changeset 리소스를 구분하고 프로젝트/환경 태그·서울 리전으로 제한한 변경 세트 조회 권한 추가.
- bootstrap 관리 정책은 계정별 적용 상태를 실제 확인하며 운영 역할/신뢰/경계를 자동 확대하지 않음.
- 태그 없는 REVIEW_IN_PROGRESS의 재개는 저장된 change set ID·stack ID/이름·실행 역할·프로젝트 태그·빈 리소스 목록을 모두 확인한 경우만 허용.
- 생성 재시도는 기존 generation과 change set 영수증을 유지하며 검증을 생략하거나 스택을 자동 삭제하지 않음.

## 0.3.2 — 2026-10-14

- 루트 제품/팀 공통 지침과 AWS 설치/운영 지침의 범위를 구분; FastAPI 계약을 유지한 앱 호스트/ASGI 인계 문구로 정리.
- 실제 로컬 브랜치/원격 등록·인프라 workflow 파일 상태에 맞춰 오래된 협업 상태 문구 정정; 원격 CI/보호 검증과 구분.
- 프레임워크 중립 `service_ports.web`과 기존 `gunicorn` 별칭 호환; 실제 설정 자동 변환 없이 키 충돌 차단.
- AWS를 호출하지 않는 `readiness` 준비 검사와 `.state` 영수증; 입력/검증 도구/설치 원본 해시와 앱/HA 미완료 분리.
- 로컬 준비 단계에서도 무제한/잘못된 CIDR, 잘못된 health 경로·리전/계정 인증서 차단.
- 업무 앱·Control fencing·connector/S3 단일 writer는 별도 팀 통합/실증 대상으로 유지. AWS 재조회·생성·설치·삭제·변경 세트 미실행.

## 0.3.1 — 2026-10-14

- 인프라 코드는 저장소 루트의 aws-infra, 공유 설계/배포 문서는 docs/handoff/infra로 정리.
- GitHub 검사 workflow를 저장소 루트로 이동하고 aws-infra 작업 경로와 변경 필터 적용.
- 저장소 루트 제외 규칙, 공유 문서/CI까지 포함한 공개 검사 및 문서 참조 연결.
- 18:05 KST 읽기 검증 결과로 문서 갱신; 실제 AWS 배포·설치는 계속 미실행.

## 0.3.0 — 2026-10-14

- 업무 앱 배포는 팀원 담당으로 분리; 기반 서비스 준비에서 앱 소스 의존 제거.
- PostgreSQL 16.15/MongoDB 8.0.34 및 client 패키지 버전/SHA, 공식 서명 키 고정.
- DB TLS/auth, 빈 디스크/세대 보호, node별 비밀값 및 DB client 환경 파일.
- 14개 노드 private package, 기반 서비스 setup/verify 단계 실행·SSM 재개.
- 코어를 유지한 ALB 추가/설정 변경, 임시 HTTP 기본 DNS와 허용 CIDR, 추후 ACM HTTPS 전환.
- 공통 encore1 로그인 토큰 갱신을 5계정 병렬 조회 전에 수행해 OAuth refresh 요청 중첩 방지.
- 실제 인프라 생성·설치·업무 앱·fencing 검증은 미실행.

## 0.2.0 — 2026-10-14

- 전체 생성·삭제·재생성 실행기와 재개/소유권/S3 버전 정리 검사.
- peering permissions boundary와 network stack의 VpcId 정책 연결.
- HTTPS ALB 템플릿과 T3 Standard 절약형 설정.
- 리소스를 생성하지 않는 5계정 배포 준비 검증.
- 실제 계정 설정/공개 샘플 분리와 예제의 AWS 접근 차단.
- 공개 파일 검사, Git 제외 규칙, 코드 버전 및 오프라인 CI.
- 실제 배포·전체 설치·Control fencing·삭제 후 재생성 검증은 대기 상태.

## 0.1.0 — 2026-10-14

- 5계정·5VPC·14EC2·3물리 AZ 템플릿과 단계 실행기.
- 기존 Ubuntu 코드 기반 AWS core 설치기.
