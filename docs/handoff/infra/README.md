# 인프라 인계 문서 — 로컬 개발에서 AWS 구축으로

- 작성일: 2026-10-14
- 수정일: 2026-10-14
- 상태: 인계 자료 연결입니다. 실제 서비스 배치·AWS 생성·설치·운영 검증 완료를 뜻하지 않습니다.

## 2026-10-15 광고 로그 MongoDB 독립 관리

최신 사용자 결정으로 광고 관리·측정·소진 로그는 광고 MongoDB에 저장합니다. PostgreSQL 전달과 공통 로그 테이블 규격은 사용하지 않습니다. 새 `log_record`와 기존 기록 보존·점검/스키마 적용은 [광고 로그 저장 계약](../../development/ads/MongoDB_광고_로그_저장_계약.md)을 따릅니다. 관리3+공개5+정책2 구조와 공유 ADMIN/guest 인증 경계는 유지합니다.

## 2026-10-14 저장소 결정과 광고 인계

2026-10-14 새 음악 문서 우선 지시로 음악 기준 저장은 **RDB 4개 테이블**과 추천·표시18개/검수 보조1개로 변경합니다. 음악 원본 CSV·백업/불변 내보내기는 로컬/S3 보관 가능하며 S3만을 음악 기준 DB로 사용하지 않습니다. 공통·피드백 로그/공통 업무 상태는 PostgreSQL, 광고와 광고 로그는 MongoDB, 날씨 MongoDB/Elasticsearch·원문 로컬/S3는 유지합니다. 3차 음원 파일·직접 재생은 추가하지 않습니다. [저장 경계와 발행 계약](../../product/3차_저장소_경계와_발행_계약.md)과 [ADS 인계](../ads/README.md)를 적용하며 실제 설치·접속·운영 검증 완료와 구분합니다.


## 1. 읽는 순서

1. [로컬 개발 인프라 가이드](./local%20infra%20guide.md): Windows PC 3대·Hyper-V Ubuntu VM 9대, WireGuard·WinNAT·SSH ProxyJump 기반 개발 접속 구조입니다.
2. [AWS 인프라 구축 계획서](./AWS_인프라_구축_계획서.md): 5계정·5VPC·14EC2·3AZ, CloudFormation·SSM·systemd와 ALB 기반 AWS 구축 계획입니다. 로컬 문서를 대체하지 않고 AWS 이전 단계의 자료로 이어집니다.
3. [프로젝트 수령 상태와 적용 경계](../../product/3차_구현_결정과_익명문맥_원문보관_가이드.md): 자료 수령과 실제 검증을 구분합니다.
4. [확인·인계 목록](../../product/3차_사용자_확인과_담당자_인계_목록.md): 서비스 개발과 연결할 남은 계약을 확인합니다.

AWS 원문 출처는 사용자가 제공한 `AWS 인프라 구축 계획서 (1).md`입니다. 수정 없이 보관했으며 계정명·IAM 역할명·프로젝트 식별자·IP/CIDR은 공개용 예시입니다. 실제 설정이나 접속 주소로 사용하지 않습니다. 원문 안의 README/SECURITY/실행기/템플릿 링크는 별도 aws-infra 코드 저장소의 참조이며 현재 프로젝트에 해당 구현 파일이 수령된 것은 아닙니다.

## 2. 이어지는 구성과 변경점

| 구분 | 로컬 개발 | AWS 계획 |
|---|---|---|
| 실행 환경 | PC 3대·VM 9대 | 5계정·5VPC·EC2 14대 |
| 코어 | Kafka/Spark/Elasticsearch 각 3대 | 코어 9대 + Control 2대·PostgreSQL·MongoDB·광고 EC2 |
| 관리 접속 | WireGuard·WinNAT·SSH ProxyJump | IAM 역할·SSM, public IP 없는 EC2 |
| 공개 진입 | 별도 서비스 배치 보완 필요 | HTTPS ALB → 두 Control |
| 운영 | 로컬에서 기능 연결 검증 | 생성·설치·검증·삭제·새 세대 재생성 |

문서에 보고된 완료는 IAM bootstrap·입력/정적 검증이며 VPC·EC2·ALB 및 앱 배포는 미실행입니다. 프로젝트에서 AWS 계정·코드·테스트 결과를 직접 확인한 상태는 아닙니다. 96시간은 비용 산정 기준이며 자동 종료 예약이나 과금 상한이 아닙니다.

## 3. 서비스 연결 전에 조율할 사항

광고는 [ADS 인계](../ads/README.md)의 MongoDB replica set·광고/날씨 DB 권한 분리·MongoDB 내장 로그 저장/복구로 연결합니다. AWS 원문의 MongoDB EC2 한 대를 transaction 지원/HA 완료로 간주하지 않습니다. 음악RDB4개·원본/백업로컬/S3와PostgreSQL로그/피드백은최신음악/저장계약이며 원문은 수정하지 않습니다.

| 항목 | 원문과 현재 서비스 계약의 차이 | 인계/검증 담당 |
|---|---|---|
| 앱 프레임워크 | 2026-10-14 사용자 결정으로 서비스도 Django·DRF로 통일. 프레임워크 차이는 해소 | INF·B/C: Django WSGI/Gunicorn·systemd 실행 명령·포트·health check·실제 호환 버전 검증 |
| Spark→MongoDB | Spark는 예시 계정2~4, MongoDB는5. 5↔2~4 직접 Peering 없음. 현재 날씨 저장 경로의 쓰기 주체/연결을 확정해야 함 | INF·A: 실제 writer 위치와 도달/반환 경로 검증. 계정1 경유를 자동 가정하지 않음 |
| 저장소 | artifact/checkpoint S3 외 음악RDB4개/불변카탈로그·원본/백업S3·공통·피드백 로그 PostgreSQL·광고/광고 로그 MongoDB·날씨 원문·광고 이미지의 접속/권한 보완 필요 | INF·A/B/C: 객체/manifest·로그 스키마·replica set·보관/백업 인계 |
| 서비스 배치 | 광고 독립 EC2와 Control HA는 추가 구체화. 추천 작업자/outbox 위치·실행 수·연결 계약 필요 | INF·B/C: API/작업자·인증·소유·중복 실행 차단 검증 |
| 버전/연동 | Spark→PostgreSQL/ES connector, DB/앱 설치 버전 미완료 | INF·A/B/C: 설치 및 실제 처리 경로 검증 |
| 삭제/재생성 | 전체 새 세대는 offset/checkpoint 초기화 허용. 일반 재시작/승계는 초기화 금지 | INF·A/B/C·PL: 시험 데이터와 보존할 업무/피드백/원문을 구분하고 삭제 allowlist·복구 계약 확정 |

Control 두 대가 전체 서비스의 이중화를 뜻하지 않습니다. PostgreSQL/MongoDB 단일 노드와 NAT 장애 수용 범위, 서비스별 복구 목표를 별도로 검증합니다. 비용 추정은 원문 수령값이며 가격 재검증은 하지 않았습니다.

실제 AWS 변경 명령은 실행하지 않습니다. 기존 작업 ID·담당 배정·제품 범위는 유지하고 위 항목을 D-03/I 계열과 도메인 작업의 실행 인계에서 확인합니다.

## 최신 인프라 실행 인계 자료

- [Connector·Checkpoint·Fencing 후속 준비](INTEGRATION-READINESS.md): 의존성 및 재시작·승계 검증 경계.
- [Control Fencing 실행 검토](CONTROL-FENCING.md): canary와 실제 Control 승계 경계.
- [ES·날씨 MongoDB·앱 실행 계약](APPLICATION-CONTRACT.md): 쓰기 위치·DB 권한 및 앱 인계 항목.
- [AWS 비용 모델 분석](<AWS 인프라 과금 요소 분석.md>): 예상 비용과 실제 청구 자료를 구분한 자료.
- [AWS 리소스 목록 안내](<AWS 인프라 리소스 현황.md>): 실제 식별자는 Git 제외 운영 기록에서만 관리.
