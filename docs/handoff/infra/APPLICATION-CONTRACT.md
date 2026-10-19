# ES·날씨 MongoDB·앱 실행 계약

- 수정일: 2026-10-15
- 코드 기준: 0.3.19. 인프라 실행 계약이며 실제 실행 원문은 `.state/operations/service-handoff`·`.state/operations/weather-mongodb`, 로컬 인계 준비물은 `.state/preparation/application-handoff`에서 확인한다.

제품 FastAPI·담당·14노드·7 Peering을 유지한다. 앱 소스는 인프라 준비의 선행 조건이 아니다. 앱 의존성·업무 파이프라인·migration은 팀원이 담당한다. 이 문서는 최종 구성 보고서나 변경 실행 승인이 아니다.

## 1. ES REST/Bulk

인프라 검증 수단으로 ES8.19 HTTPS REST/Bulk를 사용하며 업무 앱 전송 방식을 대신 확정하지 않는다. Spark4.1.3/ES8.19.23을 유지하고 공식 호환 JAR 확인 전 Spark3용 connector나 SNAPSHOT을 설치하지 않는다. 공식 artifact 게시 여부는 실행 시 확인한 비공개 읽기 영수증을 따른다.

`installer/es_bulk_probe.py`는 기존 CA의 HTTPS/hostname 검증과 `pipeline_writer`를 사용한다. 현재 세대·고유 ID를 mapping metadata에 기록한 `cluster-smoke-rest-<test-id>` index에 Spark 결과18행을 Driver에서 전송한다. 같은 ID 재전송과 일부 item의400 mapping 오류 거부를 검사하고 index/증거를 보존한다. 기존 index가 있으면 중단하며 삭제·checkpoint 초기화·자동 HTTP retry를 제공하지 않는다. 기본 setup/verify에 자동 포함하지 않는다.

18행의 bounded collect는 시험용이며 업무 데이터 처리량/메모리·분산 executor 쓰기·업무 exactly-once·늦은 갱신 방지를 검증하지 않는다. ES 비밀값을 Spark closure/executor에 전달하지 않는다. 모든 bulk item의 대상/ID/순서/상태를 확인하고 한 건이라도 실패하면 batch를 실패시킨다. HTTP200만으로 성공 처리하지 않는다.

앱 담당은 안정적인 document ID, 최신성/역순 이벤트 처리, item별 오류·제한된 retry/backoff·재처리, mapping/alias·조회 권한을 정한다. 동일 ID 재전송만으로 늦은 쓰기나 exactly-once가 보장되지는 않는다. 앱 오류 시 batch 성공/offset 확정을 차단한다. 현재 공용 `pipeline_writer`를 앱별 최소 권한 사용자로 나누는 것도 별도로 검토하며 관리자 비밀번호를 앱에 전달하지 않는다.

근거: [Elastic Bulk API](https://www.elastic.co/guide/en/elasticsearch/reference/8.19/docs-bulk.html), [Elastic Spark 요구사항](https://www.elastic.co/docs/reference/elasticsearch-hadoop/requirements), [Spark foreachBatch](https://spark.apache.org/docs/4.1.3/streaming/apis-on-dataframes-and-datasets.html).

## 2. 날씨 MongoDB 쓰기 위치

기존 설계의 직접 경로와 목적지 보안그룹을 각각 확인한다. 이 표는 live 연결 성공의 증거가 아니다.

| 쓰기 실행 위치 | ES HTTPS9200 | MongoDB27017의 현재 제약 |
|---|---|---|
| Control A/B의 Driver | 직접 Peering·ES ingress 있음 | encore1↔5 Peering 있음. 0.3.18의 MongoDB ingress는 두 Control의 정확한 /32·27017을 추가. 실제 적용/연결은 비공개 영수증 확인 |
| Spark Worker의 executor | 직접 경로·ES ingress 있음 | encore2~4↔5 직접 Peering 없음. MongoDB ingress도 없음 |
| 광고 호스트 | 별도 ES 경로/ingress 합의 필요 | MongoDB까지 같은 VPC 경로·광고 호스트 ingress 있음. 현재 자격 증명은 광고 DB 전용 |

Driver를 Control에서 시작해도 `foreachPartition`/executor 코드의 네트워크 출발지는 Spark 노드다. `foreachBatch` callback 안에서 Driver가 직접 요청하는 경우와 구분한다. Peering은 중계 라우터가 아니며 encore1을 통과하는 전이 경로는 제공하지 않는다.

**2026-10-15 사용자 진행 요청으로 채택한 인프라 범위:** 확정7쌍 Peering을 유지하고 Control Driver에서 날씨 MongoDB에 쓰는 접근을 준비한다. 기존 네트워크 스택에 두 Control의 정확한 사설 /32·27017만 추가하고 `weather` DB의 `weather_app` 사용자·readWrite·SCRAM-SHA-256/authSource를 분리한다. 업무 데이터를 무제한 `collect()`하는 방식은 채택하지 않으며 처리량·메모리·최신성·재시도·실제 writer 프로세스/Driver 계약은 A가 제공한다. 다른 쓰기 서비스나 executor 직접 연결을 선택하면 필요한 배치/네트워크 변경을 먼저 검토한다. 인프라 접근 채택은 업무 앱 배포나 HA 완료를 뜻하지 않는다.

날씨 MongoDB는 광고 DB/사용자를 재사용하지 않는다. 전용 DB의 `readWrite`, 해당 DB의 `authSource`, 검증된 TLS와 서비스 사용자 전용 credential 참조를 인계한다. 광고 환경 파일을 날씨용으로 덮어쓰지 않는다.

별도 `installer/weather_mongodb.py`는 명시 실행에서만 동작한다. 기존 사용자/다른 세대/권한이 다르면 덮어쓰기·비밀번호 회전 없이 중단한다. 두 Control에는 `/etc/music-cluster/control/weather-database.env`를 root:control0640으로 생성하며 `WEATHER_MONGO_HOST/PORT/DATABASE/USER/PASSWORD/AUTH_SOURCE/TLS/TLS_CA_FILE`을 제공한다. CA·호스트 이름 검증을 유지하고 광고·PostgreSQL 환경은 변경하지 않는다. 비밀번호는 `.private`에서 세대별로 한 번 생성하고 호스트 공개키의 RSA-OAEP/SHA256 암호문만 전달한다. 관리자 비밀번호나 CA 개인키를 전달하지 않는다.

인프라 검증용 mongosh2.13.0은 기존 DB 패키지 lock과 같은 SHA256으로 확인한 공식 DEB를 `/opt/music-cluster/mongodb-clients/mongosh/2.13.0`에 추출한다. 시스템 패키지·전역 PATH·업무 앱 venv를 변경하지 않는다. 실제 앱의 Python MongoDB driver/잠금 버전은 A의 앱 의존성 계약이다. 시험은 서비스 사용자 `control`의 TLS 인증·고유 collection9→18행·동일 ID 재전송과 광고/admin DB 접근 거부를 확인하며 업무 파이프라인/중복·최신성 보장을 대신하지 않는다. 기존 데이터와 시험 collection은 삭제하지 않는다.

## 3. 작성할 실행 계약과 오프라인 검사

빈 양식은 [application-contract.example.json](../../../aws-infra/config/application-contract.example.json)이다. 실제 호스트 선택·argv·설정 참조는 Git 제외 `.state/application-contract.json`에 작성한다. 비밀값 자체는 `.private` 또는 EC2 비공개 환경 파일에 두고 이 양식에는 참조만 적는다.

| 담당 연결 | 결정·인계 항목 |
|---|---|
| A·INF | MongoDB writer 호스트/Driver·executor/프로세스, 전용 DB·사용자·authSource·credential 참조, 필요한 정확한 SG/경로 변경 |
| A·INF | ES 전송 방식/실행 위치, document ID·최신성·오류/재시도·credential 참조 |
| B/C·INF | FastAPI ASGI 프로그램/정확한 버전·진입점·worker 수·foreground start argv·작업 경로·의존성 lock 경로/SHA256·종료 예산, 기존8000·`/health/` |
| A/B/C·INF | supervisor가 감독할 프로세스 argv·Driver/app 식별·고정 query/checkpoint·종료 증거. 재시작/승계 때 초기화 금지 |

명령은 저장소 루트에서 실행한다.

```bash
cd aws-infra
python3 bin/application-plan.py --config config/project.json
# 실제 비공개 계약을 정리한 뒤:
# python3 bin/application-plan.py --config config/project.json --contract .state/application-contract.json
```

이 명령은 AWS 호출·SG/DB 변경·앱 설치 없이 설계 경로와 미입력 항목만 출력하며 미정/차단이 있으면 종료코드1을 반환한다. 계약 입력 완료와 실제 서비스/앱 HA 검증을 구분한다. 앱 소스 확보를 준비의 선행 조건으로 요구하지 않는다. ASGI 서버 선택·업무 코드·migration을 인프라 설치기가 대신 구현하지 않는다.

두 Control의 동일 날씨 계정 접속은 DB 권한만으로 단일 active를 강제하지 않는다. 실제 writer는 검증된 supervisor가 감독하도록 start/stop·Driver/app 식별·query/checkpoint를 연결하고 앱 수준의 재시작/승계를 별도로 검증한다. 이번 네이티브 클라이언트의 순차 쓰기 검사는 해당 업무 HA 완료가 아니다.

## 4. 비공개 인계 묶음과 검토안

`.state/application-contract.json`은 담당자가 채울 비공개 실행 계약이다. 비밀번호·토큰·개인키를 넣지 않고 서비스별 환경 파일 경로만 참조한다. 예제 양식의 미정값을 임의의 ASGI 서버/버전이나 가상 업무 명령으로 채우지 않는다. 인계 도구는 앱 소스를 읽거나 import하지 않으며 lock의 경로/SHA256 형식만 검사한다. 실제 파일 내용·의존성 호환성과 프로그램/argv 일치는 앱 연결 때 별도로 검증한다.

저장소 루트에서 다음과 같이 실행한다. 출력 경로는 매번 새 이름을 사용하며 기존 인계 묶음을 덮어쓰지 않는다.

```bash
cd aws-infra
python3 bin/application-plan.py --config config/project.json --contract .state/application-contract.json
# 미입력으로 종료코드1이면 해당 항목을 인계한다. 준비물 생성은 별도 로컬 동작이다.
python3 bin/application-handoff.py --config config/project.json --contract .state/application-contract.json --output .state/preparation/application-handoff/manual-review-01
```

실제 설정에 generation이 없으면 로컬 lifecycle의 ready 상태·입력 해시가 일치할 때만 해당 세대의 resolved config를 사용한다. 샘플 설정은 실제 lifecycle을 읽지 않는다. 현재 AWS 조회를 수행하지 않으며 bindings의 원본은 로컬 설정/공개 의존성 lock이다. 실제 설치 완료 증거는 기존 실행 영수증에서 확인한다.

묶음은 미입력/차단 목록, 설정/CA/서비스별 환경 참조, Delta lock·JAR/세션 설정, 해시 manifest와 HANDOFF.md를 포함한다. `.state`의 새 디렉터리에700/파일600으로 저장하며 감지한 평문 자격 증명이 있으면 생성 전에 중단한다. 진단에는 필드 경로만 표시한다. 검사는 비밀값 검토를 대체하지 않는다.

유효한 입력이 모두 있을 때만 두 Control의 사설 bind 주소를 치환한 웹 unit과 단일 active supervisor patch **검토안**을 만든다. 입력이 미완료면 미해결 표시가 있는 `.service.in` 템플릿만 남긴다. 셸/daemon/cluster Driver·출력 경로 이탈·다른 세대/query/시험 checkpoint·관리자 runtime 참조를 차단한다. systemd argv는 [공식 명령 줄 규약](https://github.com/systemd/systemd/blob/v255/man/systemd.service.xml)과 [인용 규약](https://github.com/systemd/systemd/blob/v255/man/systemd.syntax.xml)에 맞춰 인용하고 환경 변수/퍼센트의 자동 확장을 막는다. 웹 worker 안에서 Collector/Driver/스케줄러를 시작하지 않는다.

기존 `control-fencing.sh`는 격리 canary만 허용한다. 업무 앱 supervisor patch를 여기에 덮어쓰거나 canary unit을 복제해 활성화하지 않는다. 실제 업무용 설치/lifecycle·종료 증거·필요한 서비스별 ES/Kafka 설정 전달을 연결하고 검토한 뒤 명시 배포 요청으로 적용한다. `contract_inputs_complete`는 입력 완성을 뜻하며 앱 배포·ALB 건강 상태·업무 HA·실제 S3 단일 writer 성공을 뜻하지 않는다. 이 도구에는 설치/enable/실행·offset/checkpoint 초기화 기능이 없다.
