# 팀원 애플리케이션 배포 규약

- 수정일: 2026-10-14
- 적용 범위: AWS 앱 호스트 인계와 실행 계약. 제품·팀 공통 기준은 [루트 AGENTS](../../../AGENTS.md), AWS 설치·운영은 [aws-infra/AGENTS](../../../aws-infra/AGENTS.md)를 따른다.

인프라 담당은 AWS 생성·삭제·재생성, Kafka·Spark/ZooKeeper·ES·PostgreSQL·MongoDB 기반 서비스와 운영 접속 경로를 준비한다.
팀원은 제품 계약의 FastAPI 웹·Collector·Spark Driver·광고 앱의 소스, 의존성, DB migration, systemd 앱 실행과 업무 데이터 흐름을 배포·검증한다.
애플리케이션 소스 제출은 코어 인프라 생성·기반 서비스 setup의 선행 조건이 아니다.
Control 주/대기·fencing과 S3 단일 writer는 합의한 방향을 유지하며 앱 시작/종료 계약에 맞춰 별도 연동·검증한다.

이 파일은 접속·배포 규약이다. 2026-10-14 18:05 KST 기준 5계정 bootstrap과 ALB 포함 입력 준비는 통과했지만, 실제 인프라와 기반 서비스는 아직 배포하지 않았다.
실행 방법은 [aws-infra/README](../../../aws-infra/README.md), 현재 완료/미완료 상태는 [문서 안내](README.md)를 참고한다. 허용 /32 CIDR은 Git 제외 로컬 설정에 반영했다.

## 1. 노드와 기본 접속 규약

| 담당 EC2 | 팀원 배포 대상 | 기본 경로·접속 |
|---|---|---|
| control-a / control-b | FastAPI 웹용 앱 호스트, Collector, Spark Driver, 배치 스케줄러 | 소스 `/opt/music-apps/control`, 사용자 `control`, 웹 8000 |
| advertising | 광고 서비스 | 소스 `/opt/music-apps/advertising`, 사용자 `advertising`; API 포트/공개 경로는 추가 합의 |
| postgresql | PostgreSQL 기반 서비스 | `<POSTGRES_HOST>:5432`, DB `music`, 앱 사용자 `music_app` |
| mongodb | MongoDB 기반 서비스 | `<MONGO_HOST>:27017`, DB/authSource `advertising`, 앱 사용자 `advertising_app` |
| kafka-01~03 | Kafka 기반 서비스 | `<KAFKA_01_HOST>:9092`, `<KAFKA_02_HOST>:9092`, `<KAFKA_03_HOST>:9092`; SASL_SSL/PLAIN |
| spark-01~03 | Spark Master/Worker + ZooKeeper | `spark://<SPARK_01_HOST>:7077,<SPARK_02_HOST>:7077,<SPARK_03_HOST>:7077`; 인증·암호화 RPC |
| es-01~03 | Elasticsearch 기반 서비스 | HTTPS `<ES_01_HOST>:9200`, `<ES_02_HOST>:9200`, `<ES_03_HOST>:9200` |

실제 InstanceId와 SSM 접속 대상은 AWS 태그/Outputs/inventory로 확인한다. 이 문서는 실제 주소를 포함하지 않는다. 배포 후 private inventory와 DB 환경 파일에서 주소를 확인한다.
웹은 두 Control의 사설 주소에서 8000 포트로 수신한다. ALB health 경로 기본 규약은 `/health/`이며 정상 시 인증 없이 HTTP 200을 반환한다.
외부 접속은 허용 CIDR로 제한한 ALB 기본 DNS의 임시 HTTP를 사용한다. 도메인과 서울 ACM 인증서는 준비 후 HTTPS로 전환한다. 이 규약을 바꾸면 설정과 preflight도 함께 갱신한다.
광고 API는 현재 외부 ALB target에 자동 포함되지 않는다. Control 경유 또는 별도 공개 경로가 필요하면 포트·route·security group을 먼저 합의한다.

## 2. 접속과 파일 업로드

EC2는 public IP와 inbound SSH 없이 SSM으로 관리한다.
계정 소유자는 본인 계정에서 필요한 Session Manager 권한이 있는 로그인으로 해당 EC2에 접속한다.
AWS 콘솔의 EC2 → 인스턴스 선택 → 연결 → Session Manager 또는 Systems Manager의 Session Manager를 사용한다.
AWS 운영 CLI의 Run Command 권한과 팀원별 interactive session 권한은 구분한다. 팀원이 사용할 IAM 주체의 권한은 실제 접속 시 확인한다.

SSM 세션에서 접근 권한을 갖춘 Git checkout 또는 팀의 비공개 artifact 경로로 앱 파일을 배포한다.
앱 저장소 인증값·AWS 키·DB 비밀번호를 공개 저장소, 설치 명령 출력, 채팅이나 배포 문서에 기록하지 않는다.
AWS 접근은 instance profile을 사용한다. 팀원의 장기 Access Key를 EC2에 복사하지 않는다.

## 3. 비공개 DB 설정과 TLS

setup은 Control과 광고 호스트에 아래 환경 파일을 생성한다. 해당 서비스 사용자/그룹만 읽을 수 있는 `0640` 파일이다.

| 호스트 | 환경 파일 | 제공 값 |
|---|---|---|
| Control A/B | `/etc/music-cluster/control/database.env` | PostgreSQL host/port/database/user/password, `sslmode=verify-full`, CA 경로 |
| 광고 서비스 | `/etc/music-cluster/advertising/database.env` | MongoDB host/port/database/user/password/authSource, TLS 사용 및 CA 경로 |

systemd의 `EnvironmentFile=` 또는 데이터 전용 환경 파일 로더로 읽는다. 실제 값을 소스에 하드코딩하거나 Git에 커밋하지 않는다.
CA는 각 호스트의 `/etc/music-cluster/<role>/tls/ca.crt`다. 인증서와 호스트 이름/IP 검증을 유지한다.
MongoDB 앱 사용자에는 해당 DB의 readWrite만 부여한다. MongoDB 관리자 비밀번호는 DB 노드에만 전달된다.
PostgreSQL 앱 사용자는 대상 DB owner이며 superuser·role 생성·DB 생성 권한을 부여하지 않는다. remote admin/비암호화 접근은 허용하지 않는다.

Kafka/Spark/ES의 노드별 접속 설정과 비밀값은 SSM으로 전달한 root 전용 runtime에 있다.
권한 있는 담당자가 필요한 앱용 설정만 서비스 사용자에게 분리하여 전달한다. 관리자 비밀값이나 CA private key를 앱에 배포하지 않는다.
Control 앱의 Spark/Kafka/S3A connector 의존성과 ES 연동은 팀의 앱 의존성 및 현재 미해결 connector lock과 함께 검증해야 한다.

## 4. 서비스 운영과 HA

기반 서비스의 systemd 단위는 `music-kafka`, `music-zookeeper`, `music-spark-master`, `music-spark-worker`,
`music-elasticsearch`, `music-postgresql`, `music-mongodb`다.
소스·설정·버전의 자동 변경이나 DB 기존 데이터의 자동 재초기화는 수행하지 않는다.
팀원 앱의 systemd 단위와 dependency/start/stop/health 계약은 앱 담당자가 제공한다.

두 Control은 팀의 FastAPI 웹 앱 배포 대상이다. ASGI 실행 서버·버전·worker 수·systemd unit은 아직 채택하지 않았고 기반 setup은 Python 환경/디렉터리·TLS·DB client 설정만 준비한다. 웹의 health 응답은 실제 앱 담당자가 구현하며 인프라 설치기가 임시 성공 응답을 만들지 않는다. Collector·Driver·스케줄러는 단일 active에서만 실행한다.
ZooKeeper Control 전용 경로/ACL과 이전 프로세스·Driver·Spark application 종료 확인에 기반한 fencing을 연동한다.
실제 fencing과 S3 checkpoint의 단일 writer 확인 전 HA 완료로 선언하지 않는다.
Spark Master HA와 Control/Driver HA는 별개다.

checkpoint 사용 prefix는 `aws/aws-dev/<generation>/<query>/`이며 재생성의 새 generation은 기존 prefix를 복구 없이 분리한다.
일반 재시도·재시작·Control 승계에서 offset/checkpoint를 자동 초기화하지 않는다.

## 5. 남은 기술 선택과 인계

제품 FastAPI 기준을 유지하며 ASGI 실행 프로그램이 필요하다. [FastAPI 공식 실행 문서](https://fastapi.tiangolo.com/deployment/manually/)를 참고해 B/C와 INF가 서버/버전·앱 진입점·worker 수·systemd 시작/종료·사설 bind·프록시 신뢰 범위와 `/health/`를 합의한다. 과거 Django/Gunicorn 표현은 실행 기술 채택을 뜻하지 않는다. 공개 설정의 `service_ports.web`과 기존 `gunicorn` 별칭은 같은 웹 target 포트이며 실제 설정은 자동 변경하지 않는다.

| 항목 | 확정할 계약/남은 검증 | 책임 연결 |
|---|---|---|
| 앱 실행 | FastAPI/ASGI 의존성 잠금, Python 호환성, unit·start/stop/health·웹 8000 | B/C·INF |
| 단일 active | Collector/Driver/스케줄러 lifecycle, ZK 경로/ACL, 이전 프로세스·Spark application 종료 증거와 실패 시 승계 차단 | A/B/C·INF |
| connector/checkpoint | Kafka/S3A/Delta/ES 의존성 호환, query prefix/실제 writer·재시작·승계 중 단일 writer | A/B/C·INF |
| 날씨 MongoDB | Spark 실행 위치와 실제 writer의 도달/반환 경로. 계정5↔2~4 직접 Peering 없음; 계정1 경유/새 Peering을 자동 채택하지 않음 | A·INF |
| DB 분리 | 현재 MongoDB client 설정은 광고 DB/authSource/사용자용. 날씨 DB·사용자·권한을 광고 자격 증명으로 대체하지 않고 별도 합의 | A/B·INF |
| 공개/작업자 배치 | 광고 API 경로·추천 작업자/outbox 실행 위치/개수와 앱 권한 | B/C·INF |

위 항목과 앱 소스 확보는 기반 인프라 준비의 선행 조건이 아니다. 실제 앱 통합·HA 완료 판정 전에 해당 계약과 검증 근거가 필요하다. 확정된 14노드·7 Peering·제품 기능/담당을 이 목록으로 바꾸지 않는다.

## 6. 검증 책임

인프라 `verify --execute`는 실제 inventory/SSM과 기반 Kafka/Spark/ES/DB health·smoke를 확인한다.
업무 앱, ALB target health, 앱 migration·데이터 흐름·Control fencing·실제 앱 checkpoint 정합성은 팀과 별도로 검증한다.
EC2 running이나 SSM Online만으로 앱 배포 완료를 판단하지 않는다.
