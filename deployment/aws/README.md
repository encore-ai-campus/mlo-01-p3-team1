# 기존 AWS 세대에 앱 연결

이 폴더는 2026-10-16에 실제 설치한 AWS 세대와 develop 앱의 차이를 연결하는 코드입니다. 실행 결과와 제한은 [INF 변경 라우팅](../../docs/development/INF_AWS_앱배포_변경_라우팅.md)을 확인하세요.

기반 인프라는 별도 운영 checkout의 검증된 `aws-infra 0.3.19`로 생성했습니다. 이 develop checkout의 `aws-infra 0.3.2`를 현재 세대에 다시 적용하는 배포 절차는 아닙니다.

실행 순서는 기존 리소스/세대 확인 → MongoDB replica 전환/앱 Kafka 토픽 준비 → 동일 커넥터를 전체 fleet에 설치 → private 환경·TLS·원본 gateway 헤더 준비 → 앱 초기 설치 → 실제 연결 검사입니다. 모두 사용자가 승인한 기존 세대에 한정합니다.

## 소유자 전용 설치 묶음

`install_app.py`는 EC2에서 명시적으로 `--apply`할 때 설치합니다. AWS 키·앱 비밀값을 CLI 인자로 넘기지 않습니다. SSM에서 검증한 SHA-256의 private artifact를 전달하고 다음 파일을 소유자 전용 디렉터리에 준비합니다.

- `app/`: `.env`, Git 메타데이터, node_modules, 작업 로그를 제외한 앱 코드·운영 잠금 파일·빌드된 frontend/dist·제공 CSV.
- `manifest.json`: `app/` 아래 상대 경로와 SHA-256 매핑.
- `deployment.json`: `node`, `role`(control/advertising), `instance_id`, `generation`, 불변 `release`, `writer_active`, `private_ip`, `mongo_ip`, `controls`, `music_sha256`.
- `application.env`: 노드별 서버 환경. systemd가 데이터를 읽으며 shell source로 실행하지 않음.
- Control 전용 `nginx.conf`, `spark-defaults.conf`, `kafka-options.json`: 검토된 템플릿을 비공개 값으로 렌더. Spark Driver Python 경로는 `@DRIVER_PYTHON@`으로 준비하고 설치기가 실제 분리 venv 경로로 대체.

현재 Mac의 소유자 전용 운영 준비/실행 코드는 운영 checkout의 `aws-infra/.state/operations/application-deployment/`에 있고, 생성물은 `.private/`에 있습니다. 공개 저장소에는 비밀값 없는 검토 대상만 남깁니다.

`install_app.py`는 처음 설치/준비하는 절차입니다. 운영 중인 writer의 무중단 배포·다른 Control로 승계하는 자동화가 아니며, 그런 전환에는 이전 Driver/application 종료 확인과 fencing 연동이 필요합니다. 기존 세대의 보완 적용은 호출자가 이전 writer/Driver 종료와 Spark application 제거를 확인한 다음 `--skip-initialize`로 수행합니다. 이 옵션은 migration·원본 import·광고 스키마 초기화를 다시 실행하지 않습니다. 새 세대의 설치가 아니면 데이터/checkpoint를 지우지 않습니다.

## 개별 도구

- `mongodb_replica.py`: `--generation`, `--instance-id`로 대상 확인. 기본은 조회, `--apply`가 데이터/config 백업과 단일 멤버 `ads-rs` 전환을 실행. 백업을 보존하며 기존 인증/TLS를 끄지 않음.
- `prepare_kafka.py`: 같은 대상 확인 후 `--apply`에서만 앱 토픽/ACL 준비. 기존 토픽의 partition/RF/minISR가 다르면 자동 변경하지 않음.
- `install_connectors.py`: `--plan`에 기존 `generation`, `instance_id`, 세 `master_hosts`를 넣고 `--bundle`에 검토된 8개 JAR와 `connectors.lock.json`을 제공. `--apply` 전 전체 해시와 idle cluster를 확인. Maven을 호출하지 않음.
- `edge_config.py`: 비공개 `--plan`, `--secret`, `--output`으로 실제 적용한 CloudFront 설정을 렌더. AWS API는 호출하지 않음. 소유 도메인이 없는 임시 기본 인증서용이며 origin은 기존 HTTP ALB. 대량 음악 관리 집계를 위해 origin read timeout은 60초이며 실제 외부 응답은 약 34.5초로 확인.
- `*-app-network.template.json`: 매개변수에 실제 소유 SG/prefix list/단일 내부 IP를 전달하는 별도 ingress stack. 생성 전에 대상 SG의 모든 ENI 연결을 확인. 기반 리소스 삭제 전 이 추가 stack을 먼저 제거해야 함.

인증정보·private payload·실행 영수증은 커밋하지 않습니다. 음악 S3 보류는 `MUSIC_S3_ARCHIVE_DEFERRED=1`로 명시하며 `C_LOCAL_DEMO=0`, `INTEGRATION_ENABLED=1`을 유지합니다. 검수 초안과 운영 Catalog 발행은 다른 단계입니다. 대량 CSV 초기 import에는 최대 7,200초를 허용하므로 전달하는 SSM executionTimeout도 전체 설치 시간을 포함해 9,000초 이상으로 지정합니다. 중단돼도 원본 SHA/마지막 track_id 기준으로 재개하며 기존 적재를 초기화하지 않습니다.


## 대량 카탈로그와 추천 탐색

1MiB를 넘는 카탈로그는 기존 JSONField에 `gzip-json-v1` envelope로 저장합니다. worker는 기존 list 형식과 이 형식을 모두 읽고, 복원된 전체 곡 JSON의 SHA-256과 중복 여부를 검증합니다. DB schema migration은 필요하지 않지만, 이 reader가 없는 과거 앱으로 롤백하면 압축 카탈로그를 읽지 못하므로 저장/읽기 코드를 함께 배포해야 합니다. 음악 원본 S3 보류와는 별도입니다.

동일 점수 후보는 정확한 정수 subset-sum으로 계산하며, 정확히 180분 → 가장 가까운 초과 → 가장 가까운 미달 순서와 기존 동점 선택을 유지합니다. 점수가 다르거나 장르 대표 제약이 복잡하면 기존 CP-SAT 경로를 사용합니다. 메모리 상한과 탐색 deadline을 유지하며 운영 SEARCH_SECONDS는 60으로 맞췄습니다.
