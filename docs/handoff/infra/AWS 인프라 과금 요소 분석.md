# AWS 인프라 과금 요소 분석

- **기준일:** 2026-10-15 KST
- **계정:** `encore1` ~ `encore5` (독립 AWS 계정 5개)
- **리전:** `ap-northeast-2` (서울), 단 Cost Explorer API는 `us-east-1` 엔드포인트로 조회
- **분석 단계:** 운영 절차 **2단계 — 과금 요소 분석**
- **프로젝트 목표:** 총 **96시간** 운영, 예산 **$200** (`encore1`~`encore4` 각 $45, `encore5` $20)
- **중요:** 모든 비용 수치는 가정한 단가를 적용한 **모델 추정치**이며, 실제 청구서가 아니다. AWS 자원 변경/중지/삭제는 전혀 수행하지 않음.

## 1. 조사 근거 및 AWS 청구 데이터 접근 제한

1단계 `AWS 인프라 리소스 현황.md`에서 확인한 인벤토리를 기준으로 계산했다.

| 리소스 | 현황 |
|---|---|
| EC2 | 14대 `running`: `t3.large` 8대 / `t3.medium` 4대 / `t3.small` 2대 |
| NAT Gateway | Public NAT 5개, 전부 `available` |
| ALB | encore1 1개, `active` |
| EBS gp3 | 28개 / 총 **1,004GiB**, 모두 `in-use` |
| EBS gp3 성능 | 전체 3,000 IOPS / 125MiB/s, 기본 제공 수준 (추가 성능 프로비저닝 없음) |
| Elastic IP | 7개: NAT Gateway 연결 5개, **ALB 관리 ENI 연결 2개** (추가 EC2 EIP 아님) |
| VPC / Subnet | 5 / 30개 |
| S3 Gateway Endpoint | 5개 (자체 시간당 요금 없음) |
| 관리형 RDS | 5개 계정 모두 서울 리전 DB Instance 0개 (owner 프로필로 재조회) |
| EC2 CPU Credit | 14대 모두 `standard` 모드 (실제 API로 확인) |

`ce:GetCostAndUsage` 조회는 5개 계정 모두 실패했다. `encore1` 및 owner 프로필에서는 AWS Organizations **SCP의 명시적 Deny**, `encore2`~`encore5`의 기본 `ProjectInfraRole`에서는 **IAM Allow 부재**가 확인됐다. 이에 따라 실제 누적 사용료, 크레딧, 무료 사용 범위, 할인 및 세금을 검증하지 못했다.

## 2. 비용 모델 및 전제

| 요금 요소 | 분석에 사용한 단가 | 과금 모델 |
|---|---:|---|
| EC2 t3.large | $0.104/h | Linux On-Demand 가정 |
| EC2 t3.medium | $0.052/h | Linux On-Demand 가정 |
| EC2 t3.small | $0.026/h | Linux On-Demand 가정 |
| Public NAT Gateway | $0.059/h/개 | 시간당 기본료만 |
| EBS gp3 | $0.0912/GiB-월 | 730시간/월로 시간 비례 배분 |
| Public IPv4 | $0.005/IP-h | 발견된 EIP 7개만 반영 |
| ALB | $0.0252/h | 기본 시간 요금만 반영 |

> 단가는 이전 단계에서 적용한 서울 리전의 **분석용 가정 단가**다. 계약 조건·AWS 요금 개정·실제 UsageType을 검증하지 못했으므로 최종 예산/청구 예측에 그대로 사용하지 말 것. 정확한 판단에는 AWS Price List API 또는 Cost Explorer 검증이 필요하다.

**96시간 비용 모델**: EC2 14대와 NAT·ALB·EIP·EBS 모두 해당 96시간 동안에만 과금 대상 상태로 유지된 것으로 가정한다. 실제로 EBS를 일주일 또는 한 달 내내 보존하면 비용이 늘어난다.

**제외한 비용**: NAT 데이터 처리량, ALB LCU, 인터넷 송신/교차 AZ/피어링 트래픽, S3 저장·요청, CloudWatch, EBS 스냅샷·추가 성능, SSM 관련 별도 서비스 사용량, CPU 크레딧 요금(실제 14대 모두 `standard`로 확인되어 Unlimited 초과요금은 해당 없음), ALB의 추가 공인 IPv4 사용량, 세금·환율·할인·크레딧. 미발견 글로벌/타 리전 자원도 제외.

## 3. 96시간 기준 계정별 기본 비용 추정

**단위: USD. 각 수치는 소수 둘째 자리로 표시하되 합계는 반올림 전 원금액을 기준으로 계산함.**

| 계정 | EC2 | NAT | EBS | 발견된 IPv4 | ALB | 기본 합계 | 가정 예산 | 기본 잔여 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| encore1 | $22.46 | $5.66 | $1.87 | $1.44 | $2.42 | **$33.86** | $45 | $11.14 |
| encore2 | $24.96 | $5.66 | $2.95 | $0.48 | $0.00 | **$34.05** | $45 | $10.95 |
| encore3 | $24.96 | $5.66 | $2.95 | $0.48 | $0.00 | **$34.05** | $45 | $10.95 |
| encore4 | $24.96 | $5.66 | $2.95 | $0.48 | $0.00 | **$34.05** | $45 | $10.95 |
| encore5 | $7.49 | $5.66 | $1.32 | $0.48 | $0.00 | **$14.95** | $20 | $5.05 |
| **전체** | **$104.83** | **$28.32** | **$12.04** | **$3.36** | **$2.42** | **$150.97** | **$200** | **$49.03** |

**전체 약 $150.97 / 예산 $200 대비 약 75.5%**. 다만 미포함 요금과 실제 이미 발생한 청구액이 있으므로 이를 가용 예산이 $49.03 남았다는 의미로 해석하면 안 된다.

## 4. 월 730시간 가동 기준으로 환산한 비용

다음 값은 96시간 프로젝트를 상시 운영했을 경우의 **비교 기준선**이다. 실제 30일 사용량을 뜻하지 않는다.

| 항목 | 월 730시간 기준 모델 비용 |
|---|---:|
| EC2 | $797.16 |
| NAT 5개 | $215.35 |
| EBS 1,004GiB | $91.56 |
| Public IPv4 7개 | $25.55 |
| ALB 1개 | $18.40 |
| **합계** | **$1148.02** |

## 5. 비용이 쌓이는 방식과 운영 시나리오

**96시간 연속 운영**과 **24일간 하루 4시간씩 누적 96시간 운영**은 동등하지 않다. EC2만 Stop해도 NAT/EBS/ALB/EIP가 24일 또는 30일 계속 남아 있다면 기본 유지비가 누적된다.

| 시나리오 | EC2 과금 시간 | NAT·ALB·EIP·EBS 과금 시간 | 기본비 합계 |
|---|---:|---:|---:|
| 전체를 96시간만 유지 | 96h | 96h | **$150.97** |
| EC2만 누적 96시간, 나머지는 30일 내내 보존 | 96h | 730h | **$455.69** |
| 전부 30일 내내 가동 | 730h | 730h | **$1148.02** |

> 중지할 수 없는 리소스(예: NAT, ALB)는 삭제 후 재생성해야 시간당 요금이 멈출 수 있지만, 삭제·재생성에는 고유 ID/DNS/라우팅/CloudFormation의 상태와 서비스 연결에 변화가 생길 수 있다. **아직 안전한 `pause/resume` 자동화는 검증되지 않았다.**

## 6. 리소스별 과금 지속 여부

| 리소스 | EC2 Stop 후 과금 여부 | 중단/삭제 시 주의점 |
|---|---|---|
| EC2 컴퓨팅 | 중지 중 인스턴스 컴퓨팅 사용료는 일반적으로 중단 | 크레딧·예약/계약/타 서비스 비용 별도, 서비스 중단 |
| NAT Gateway | **계속** | 삭제해야 시간당 NAT 과금 중지; 라우팅과 SSM/인터넷 출구 영향 |
| ALB | **계속** | 삭제해야 기본요금 중지; DNS/리스너/타깃 그룹 영향 |
| EBS | **계속** | EC2 Stop은 데이터 보존; EBS Delete는 데이터 영구 손실 위험 |
| 발견된 Elastic IP | 상태에 따라 **계속** | NAT용 5개와 ALB 관리 ENI용 2개를 구분; ALB/NAT 삭제 시 연결·해제·과금 상태 재조회 필수 |
| VPC, Subnet, IGW, Route Table, SG | 리소스 자체 시간당 과금 없음 | 생성/삭제와 별개로 연결된 다른 비용 고려 |
| VPC Peering | 연결 자체 시간당 과금 없음 | 데이터 전송에 비용 발생 가능 |
| S3 Gateway Endpoint | 엔드포인트 자체 기본 시간당 과금 없음 | S3 저장/요청 사용료 별도 |
| CloudFormation Stack | 스택 자체 기본 시간당 과금 없음 | 스택이 관리하는 모든 리소스의 비용은 발생 |

## 7. Elasticsearch와 OpenSearch의 구분

- 프로젝트 `aws-infra/installer/core/30-elasticsearch.sh`는 Elasticsearch를 EC2/Ubuntu에 직접 설치하고 `music-elasticsearch.service`로 운영하도록 작성되어 있다.
- AWS 관리형 OpenSearch Domain 및 OpenSearch Serverless Collection을 **서울 리전 5개 계정 모두**에서 조회했다. 기본 프로필의 권한 부족은 별도 `encore2-owner`~`encore5-owner`로 보완하여 **Domain 0 / Collection 0**을 확인했다.
- 따라서 확인된 프로젝트 범위에서 **Amazon OpenSearch Service/Serverless의 관리형 서비스 기본요금 대상은 발견되지 않았다**. Elasticsearch는 EC2/EBS 등에 포함되는 셀프 매니지드 구성이다.
- 타 리전은 별도 조사 대상이다.

## 8. 실제 코드의 Lifecycle 및 보존 관련 위험

- `aws-infra/README.md`: 96시간은 비용 산정 전제일 뿐 자동 종료 예약이 아니며, **전체 Create → Destroy → Create 실제 AWS 왕복 검증은 완료되지 않았다**.
- `aws-infra/bin/manage.py`: `destroy`는 ALB → Control EC2 → 다른 EC2 → peering/route → 프로젝트 S3 오브젝트·버전 → network까지 제거하도록 설계됨.
- `aws-infra/templates/...compute...json`: EC2 루트 EBS 및 데이터 EBS에 `DeleteOnTermination: true`. **EC2 Stop과 Terminate를 혼동하면 데이터가 삭제될 수 있다.**
- `aws-infra/README.md`: 새 세대 배포에서 Kafka Offset, Spark Checkpoint 초기화를 허용. 현재 `destroy`는 비용 최적화용 일시 중지가 아니라 전체 재생성 성격이 강함.
- **권장 설계 방향**: 데이터/네트워크 보존을 전제로 한 별도 `pause/resume` 설계 및 정상 종료/복구 검증. 구현·실행은 별도 승인 필요.

## 9. 후속 조사 및 승인 조건

1. CloudFormation Stack과 직접 생성 리소스 소유권 매핑 완료.
2. 각 EC2 서비스의 정상 종료·부팅 순서 및 저장소/체크포인트 복원 검증.
3. NAT 제거 시 SSM 접근, OS 패키지 설치, 외부 API, ECR/S3, 라우팅·Peering 의존성 파악.
4. ALB 제거·재생성 시 DNS, ACM, target group health, 보안 그룹, 클라이언트 접속 변경 검증.
5. 프로젝트 데이터 보존 정책(EBS/S3/DB/Kafka/ES) 문서화.
6. Cost Explorer 청구 데이터 접근 제한 해결 또는 계정별 청구 내역을 별도 검증.
7. **사용자의 개별 승인 없이 AWS 자원의 생성·수정·삭제·중지·재부팅은 절대 실행하지 않음.**

## 10. 분석 상태

| 단계 | 상태 |
|---:|---|
| 1 리소스 조회 | 서울 리전 기준 완료 |
| 2 과금 요소 분석 | **기본 단가 가정 모델 완료 / 실제 청구 조회 제한** |
| 3 영향도 분석 | 별도 분석 진행 대상 |
| 4 실행 대상 승인 | 미진행 |
| 5 중지·삭제 | **미진행** |
| 6 검증 | 미진행 |

## 출처·검증 경로

- 실제 리소스: 같은 폴더의 `AWS 인프라 리소스 현황.md` (2026-10-15 조회)
- AWS 자체 조회: `ec2 describe-instances`, `describe-nat-gateways`, `describe-volumes`, `describe-addresses`, `elbv2 describe-load-balancers`, `opensearch list-domain-names`, `opensearchserverless list-collections`, `ce get-cost-and-usage`
- 코드 검토: `aws-infra/README.md`, `bin/manage.py`, CloudFormation 템플릿, `installer/core/30-elasticsearch.sh`
- 공식 요금 페이지: https://aws.amazon.com/ec2/pricing/on-demand/ , https://aws.amazon.com/vpc/pricing/ , https://aws.amazon.com/ebs/pricing/ , https://aws.amazon.com/elasticloadbalancing/pricing/
