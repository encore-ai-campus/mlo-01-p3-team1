# 코드 변경 이력

실제 실행 결과는 `.state/`에 보관한다. 이 파일은 공개 가능한 코드 변경만 기록한다.

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
