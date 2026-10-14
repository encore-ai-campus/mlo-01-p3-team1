# 인프라 인계 문서 — 로컬 개발에서 AWS 구축으로

- 작성일: 2026-10-14
- 수정일: 2026-10-14
- 상태: 인계 자료 연결입니다. 실제 서비스 배치·AWS 생성·설치·운영 검증 완료를 뜻하지 않습니다. 현재 AWS 실행 코드와 최근 준비 상태는 아래 4절에 연결했습니다.

## 1. 읽는 순서

1. [로컬 개발 인프라 가이드](./local%20infra%20guide.md): Windows PC 3대·Hyper-V Ubuntu VM 9대, WireGuard·WinNAT·SSH ProxyJump 기반 개발 접속 구조입니다.
2. [AWS 인프라 구축 계획서](./AWS_인프라_구축_계획서.md): 5계정·5VPC·14EC2·3AZ, CloudFormation·SSM·systemd와 ALB 기반 AWS 구축 계획입니다. 로컬 문서를 대체하지 않고 AWS 이전 단계의 자료로 이어집니다.
3. [프로젝트 수령 상태와 적용 경계](../../product/3차_구현_결정과_익명문맥_원문보관_가이드.md): 자료 수령과 실제 검증을 구분합니다.
4. [확인·인계 목록](../../product/3차_사용자_확인과_담당자_인계_목록.md): 서비스 개발과 연결할 남은 계약을 확인합니다.

AWS 원문 출처는 사용자가 제공한 `AWS 인프라 구축 계획서 (1).md`입니다. 수정 없이 보관했으며 계정명·IAM 역할명·프로젝트 식별자·IP/CIDR은 공개용 예시입니다. 실제 설정이나 접속 주소로 사용하지 않습니다. 원문 안의 README/SECURITY/실행기/템플릿 링크는 별도 aws-infra 코드 저장소의 참조이며 최초 자료 수령 시점에는 구현 파일이 없었습니다. 이후 이번 이관으로 저장소 루트에 aws-infra 코드와 실행기가 추가됐으며 최신 상태는 4절을 따릅니다.

## 2. 이어지는 구성과 변경점

| 구분 | 로컬 개발 | AWS 계획 |
|---|---|---|
| 실행 환경 | PC 3대·VM 9대 | 5계정·5VPC·EC2 14대 |
| 코어 | Kafka/Spark/Elasticsearch 각 3대 | 코어 9대 + Control 2대·PostgreSQL·MongoDB·광고 EC2 |
| 관리 접속 | WireGuard·WinNAT·SSH ProxyJump | IAM 역할·SSM, public IP 없는 EC2 |
| 공개 진입 | 별도 서비스 배치 보완 필요 | ALB 기본 DNS·임시 HTTP → 두 Control, 허용 CIDR 제한; 추후 ACM HTTPS |
| 운영 | 로컬에서 기능 연결 검증 | 생성·설치·검증·삭제·새 세대 재생성 |

문서에 보고된 완료는 IAM bootstrap·입력/정적 검증이며 VPC·EC2·ALB 및 앱 배포는 미실행입니다. AWS 계정 상태는 원작업의 2026-10-14 18:05 KST 읽기 검증 기록을 기준으로 하고 이번 이관에서는 새 AWS 조회를 하지 않았습니다. 코드의 로컬 검증 상태는 4절의 최신 인계 문서를 따릅니다. 96시간은 비용 산정 기준이며 자동 종료 예약이나 과금 상한이 아닙니다.

## 3. 서비스 연결 전에 조율할 사항

| 항목 | 원문과 현재 서비스 계약의 차이 | 인계/검증 담당 |
|---|---|---|
| 앱 프레임워크 | 수령 원문의 Django/Gunicorn은 이력이며 최신 AWS 규약은 제품 FastAPI 기준의 앱 호스트로 정리. ASGI 실행 서버/버전·worker 수는 미정 | INF·B/C: 실행 명령·ASGI 운영·포트·health check 합의 |
| Spark→MongoDB | Spark는 예시 계정2~4, MongoDB는5. 5↔2~4 직접 Peering 없음. 현재 날씨 저장 경로의 쓰기 주체/연결을 확정해야 함 | INF·A: 실제 writer 위치와 도달/반환 경로 검증. 계정1 경유를 자동 가정하지 않음 |
| 저장소 | artifact/checkpoint S3 외 날씨 원문·피드백 Delta·음악 RDB·광고 이미지 저장/권한이 부족 | INF·A/B/C: 경로·버킷·제품/DDL·보관/백업 인계 |
| 서비스 배치 | 광고 독립 EC2와 Control HA는 추가 구체화. 추천 작업자/outbox 위치·실행 수·연결 계약 필요 | INF·B/C: API/작업자·인증·소유·중복 실행 차단 검증 |
| 버전/연동 | Delta 호환 버전·Spark→ES connector, DB/앱 설치 버전 미완료 | INF·A/B/C: 설치 및 실제 처리 경로 검증 |
| 삭제/재생성 | 전체 새 세대는 offset/checkpoint 초기화 허용. 일반 재시작/승계는 초기화 금지 | INF·A/B/C·PL: 시험 데이터와 보존할 업무/피드백/원문을 구분하고 삭제 allowlist·복구 계약 확정 |

Control 두 대가 전체 서비스의 이중화를 뜻하지 않습니다. PostgreSQL/MongoDB 단일 노드와 NAT 장애 수용 범위, 서비스별 복구 목표를 별도로 검증합니다. 비용 추정은 원문 수령값이며 가격 재검증은 하지 않았습니다.

실제 AWS 변경 명령은 실행하지 않습니다. 기존 작업 ID·담당 배정·제품 범위는 유지하고 위 항목을 D-03/I 계열과 도메인 작업의 실행 인계에서 확인합니다.


## 4. AWS 실행 코드 이관과 최신 상태 — 2026-10-14

기존 작업물은 이 Git 저장소 루트의 `aws-infra/`로 이관했습니다. 실행 방법은 [aws-infra/README](../../../aws-infra/README.md)를 따릅니다.
기존 로컬 가이드와 수령 원문 AWS_인프라_구축_계획서.md, 위 서비스 연결 조율 항목은 보존합니다.

- [최신 구현·검증 상태](AWS-INFRA-STATUS.md): 코드 0.3.2과 완료/미완료, 실제 AWS 확인 시각, 다음 단계.
- [최신 AWS 구축 계획](<AWS 인프라 구축 계획.md>): 임시 HTTP, 확정 입력, PG/Mongo 기반 설치와 실행기 상태.
- [인프라 측 앱 배포 규약](TEAM-HANDOFF.md): FastAPI 앱 호스트·기반 설치와 팀원 앱의 경계, ASGI/fencing/connector/날씨 MongoDB 등 남은 실행 계약.

루트 AGENTS는 제품·팀 공통 계약, aws-infra/AGENTS는 AWS 설치·운영 계약입니다. 현재 `.github/workflows/aws-infra-check.yml`은 파일로 존재하며 원격 실행·브랜치 보호는 미검증입니다. 배포 전 `readiness`는 AWS 호출 없이 로컬 준비를 확인하고 원문 실행 기록은 `.state/`에 둡니다.

Mac 프로필·IAM bootstrap은 외부 AWS 상태를 유지하며 로컬 설정/실행 기록/도구는 aws-infra의 Git 제외 영역으로 함께 옮겼습니다.
실제 허용 접속 CIDR·계정 ID·비밀값을 공유 문서에 추가하지 않습니다. 이번 경로 정정은 Git add/commit/push 또는 AWS 생성/설치/삭제를 실행하지 않습니다.
