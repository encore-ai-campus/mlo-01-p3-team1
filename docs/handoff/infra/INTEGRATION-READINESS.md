# Kafka/S3A·checkpoint·Control fencing 준비

- 수정일: 2026-10-15
- 코드 기준: 0.3.18. 구현/로컬 검증 안내이며 실제 AWS 설치·S3·HA 성공 기록은 `.state`에서 확인한다.

제품 FastAPI/React 기준, 업무 앱 담당, 14노드·7 Peering·T3 Standard·예산과 기존 데이터는 유지한다. 업무 앱 소스는 이 준비의 선행 조건이 아니다.

## 의존성 고정과 설치 조건

`aws-infra/installer/connectors.lock.json`은 Spark 4.1.3/Hadoop 3.4.2 배포본 JAR 286개와 Kafka/S3A 추가 JAR 8개의 SHA256을 기록한다. JAR 자체는 Git 제외 `.local/connectors/4.1.3`에 둔다. 초기 신뢰는 공식 배포본 SHA512와 Maven Central HTTPS이며 lock은 검토한 바이트를 고정한다. 공개 lock에는 실제 설정이나 비밀값을 포함하지 않는다.

SLF4J API 2.0.17·Snappy 1.1.10.8·Scala library 2.13.17은 Spark 배포본이 제공한다. Hadoop/Kafka 전이 의존성이 이를 교체하거나 중복 설치하지 않도록 명시한다. Maven 사용자 설정/주입 인자는 사용하지 않고 전체 repository를 Maven Central로 고정한다. 동일 이름의 다른 JAR, 변경된 배포본, 미검토 추가 JAR, 손상/누락 파일, SNAPSHOT 및 검토 lock과 다른 bundle은 차단한다.

저장소 루트에서 `cd aws-infra` 후 다음 명령으로 **AWS 호출 없이** 준비를 확인한다.

```bash
./aws-project.sh --config config/project.json integration-plan
```

실제 설치는 별도 검토한 설치 세대/소스 업그레이드와 `bin/install.py prepare --connector-bundle <reviewed-directory>`로 명시한 payload가 필요하다. 일반 prepare는 bundle을 포함하지 않는다. 설치 대상은 Spark 3대와 Control 2대이며, 기존 Spark JAR는 교체하지 않는다. 세 Master의 완전한 관측과 active 앱 0개를 확인하지 못하면 classpath 변경을 차단한다. 기본 setup/verify는 connectors/checkpoint-smoke를 자동 실행하지 않는다.

idle 조회는 신규 작업 제출을 막는 admission lock이 아니다. 실제 5대 적용 중에는 새 앱 제출을 막는 운영 구간을 별도로 확보해야 한다.

코드 변경 후 과거 setup identity나 private package의 source hash를 자동 갱신하지 않는다. 성공 영수증·세대·실제 설정·비밀값/PKI·데이터를 보존한 명시적 업그레이드가 먼저다. 원본 해시·현재 소스·배포된 패키지의 버전을 구분한다.

## checkpoint 시험과 입증 범위

`checkpoint-smoke`는 Spark EC2에서 IMDSv2/디스크 세대·기반 health·설치된 connector lock을 확인한다. Spark 사용자로 1개 앱 코어와 고정된 18행을 사용한다. 시험 경로는 현재 환경/설치 세대 아래 `_infra-tests/checkpoint-<unique-run-id>/`의 input/output/checkpoint이며 기존 업무 경로를 사용하지 않는다.

파일 입력 9행 처리 후 동일 checkpoint에서 9행을 추가 처리한다. query ID 동일/run ID 변경, 총 18개 고유 결과와 중복/손실 없음을 확인한다. 시험 prefix가 이미 존재하면 덮어쓰지 않으며 checkpoint 초기화/삭제 명령은 제공하지 않는다. 새 명령을 다시 실행하기 전에 기존 CommandId의 결과와 남은 시험 데이터를 확인한다.

로컬 `file:` 재시작 시험은 알고리즘/클래스 로딩 검사다. 실제 cross-account S3A 접근·Structured Streaming checkpoint 재사용·장애 승계와 동시 writer 차단을 입증하지 않는다. 단일 프로세스의 순차 재시작 성공도 단일 writer fencing 성공을 뜻하지 않는다. S3 시험 원문은 `.state`, 실행용 runtime은 `.private` 또는 EC2의 권한 제한 파일로 보관한다.

## Control 승계 실행기와 남은 적용

`lib/control_fencing.py`의 판정 로직에 ZooKeeper/EC2/Spark live adapter와 foreground 프로세스 감독 실행기를 추가했다. [Control fencing 적용 전 검토](CONTROL-FENCING.md)의 별도 IAM/SSM 변경안·canary package·비활성 unit 준비 절차를 따른다. 구현은 실제 적용/HA 성공을 뜻하지 않는다.

1. ZooKeeper TLS/인증·Control 전용 ACL과 ephemeral-sequential lease, 영속적인 이전 owner, 단조 증가 epoch 및 원자적 owner CAS.
2. 정확한 이전 Control EC2에만 한정한 중지 권한과 stopped/terminated의 실제 확인. 요청 수락/SSM 성공만으로 중지 완료를 판단하지 않는다.
3. 이전 Driver/Spark application·executor의 종료를 모든 Master/Worker에서 관측. 누락·시간 초과·불명확 상태는 승계를 차단한다.
4. 승계 중 lease 재확인, 실행 중 lease 상실 시 업무 프로세스 중단과 종료 확인. 이전 owner 기록은 실제 종료 확인 전 지우지 않는다.

JSON 영수증을 live fencing 증거로 사용하지 않는다. 다른 프로젝트/환경/세대/query, 오래된 epoch, 자기 자신 중지, 불확실한 EC2/작업 종료, lease 상실, CAS 실패는 차단한다. 현재 실행기는 승계 전 클러스터 전체 idle을 요구하며 병렬 query의 선택적 fencing을 지원하지 않는다. 설치기는 업무 앱 대신 별도 canary만 준비한다. 권한 적용·Control 설치/활성화·물리 EC2 중지·실제 S3 동시 writer 차단은 별도 실행/수용 대상이다. 기본 create/setup/verify나 보안그룹·리소스 사양은 변경하지 않는다.

## 미정인 기술 선택

0.3.17의 인프라 ES 검증에는 별도 JAR 없는 Driver-side REST/Bulk probe를 제공한다. 업무 앱 방식·날씨 MongoDB 쓰기 위치/권한·ASGI/단일 active 실행은 [앱 실행 계약](APPLICATION-CONTRACT.md)을 따른다. `application-plan.py`는 직접 경로와 목적지 ingress를 따로 검사하며 설계상 가능성을 실제 연결 성공으로 표시하지 않는다.

- Spark 4.1용 Elasticsearch connector의 공식 artifact/호환성을 확인해야 한다. [Elastic 포럼 안내](https://discuss.elastic.co/t/elasticsearch-hadoop-spark-4-compatible-release-timelines/389906)는 Spark 4.1 지원을 9.6.0 대상으로 설명하므로 기존 ES 8.19 버전의 호환성을 별도로 판단한다. Spark 3용 JAR나 SNAPSHOT으로 자동 대체하지 않는다. REST/Bulk 방식 또는 버전 조정은 팀과 선택할 별도 사항이다.
- [Delta 공식 호환표](https://docs.delta.io/releases/)의 4.3.x는 Spark4.1.x를 지원한다. 0.3.15의 별도 `installer/delta.lock.json`은 `delta-spark_4.1_2.13:4.3.1`과 추가9개 JAR를 고정하고 기존 Spark 제공 logging/Jackson/native 버전을 유지한다. 실제 앱 트랜잭션·Unity Catalog 서비스 연결은 별도 검증 대상이다.
- 업무 query별 자원 배분, Control 앱 start/stop·Driver/app 식별 계약, 날씨 MongoDB는 Control Driver 접근·전용 DB/권한을 채택하고 실제 writer/메모리·재시도 계약은 A가 인계한다.
- S3 서버 액세스 로그·CloudTrail data events·CloudWatch 지표는 관측성 보완 권고이며 자동 적용하지 않는다. 기존 암호화/TLS·역할별 prefix·최소 inbound 범위를 유지하고 추가 로그 저장소도 암호화한다.

근거: [Spark Kafka 4.1.3](https://spark.apache.org/docs/4.1.3/streaming/structured-streaming-kafka-integration.html), [Hadoop S3A 3.4.2](https://hadoop.apache.org/docs/r3.4.2/hadoop-aws/tools/hadoop-aws/index.html), [Elastic 요구사항](https://www.elastic.co/docs/reference/elasticsearch-hadoop/requirements), [ZooKeeper 레시피](https://zookeeper.apache.org/doc/r3.9.4/recipes.html), [Maven mirrors](https://maven.apache.org/guides/mini/guide-mirror-settings.html), [SLF4J 호환성](https://www.slf4j.org/faq.html#compatibility).

## Delta 별도 설치와 S3 시험

`installer/delta.py`는 기본 setup과 분리된 명시 설치기다. 실제 IMDS/역할/마운트 세대와 기존286개 Spark/8개 Kafka·S3A JAR를 대조한 뒤 `/opt/music-cluster/spark-addons/delta/<lock-sha256>/`에9개 파일을 원자적으로 게시한다. 기존 `jars`·전역 Spark 설정·기존 설치 source marker·비밀값을 바꾸지 않는다. 손상/미검토 bundle과 기존 addon의 다른 내용은 덮어쓰지 않는다.

0.3.16은 새 공개 addon 상위 디렉터리의0755/JAR0644를 명시해 서비스 사용자가 읽을 수 있게 한다. runtime/인증정보의 비공개 권한을 넓히지 않는다. 과거 설치본의 경로 권한을 보완한 경우에도 최초 설치 source marker는 보존하고 별도 영수증에 구분한다.

업무 앱은 해당 addon의9개 JAR를 쉼표로 연결한 `--jars`와 `spark.sql.extensions=io.delta.sql.DeltaSparkSessionExtension`, `spark.sql.catalog.spark_catalog=org.apache.spark.sql.delta.catalog.DeltaCatalog`를 명시한다. 기본 `spark-submit`에 자동 활성화하지 않으며 앱 의존성/세션 계약에 포함한다.

`installer/delta_probe.py`는 세대 내 고유 `_infra-tests/delta-<test-id>` 경로만 사용한다. batch 생성/추가/수정/MERGE/삭제·과거 버전·잘못된 스키마 거부와 streaming9→18행 체크포인트 재시작·입력 없는 재시도를 구분한다. 기존 입력/결과/checkpoint는 초기화하지 않는다. 실제 노드 설치·Ubuntu/분산 Worker·S3 결과는 실행별 `.state/operations/delta` 영수증을 따른다.

[Delta S3 공식 저장 규약](https://docs.delta.io/delta-storage/)의 기본 모드에서는 같은 테이블의 쓰기가 한 Driver에서 이뤄져야 한다. 이 시험은 Driver를 순서대로 실행한다. 여러 Driver의 동시 쓰기·업무 HA·DynamoDB 기반 LogStore를 자동 채택하거나 보장하지 않는다.

0.3.18의 Control 날씨 MongoDB 접근/전용 권한·비공개 환경 분리는 [앱 실행 계약](APPLICATION-CONTRACT.md)을 따른다. 실제 변경/검증은 비공개 영수증에서 확인하며 업무 앱/Driver HA는 별도다.
