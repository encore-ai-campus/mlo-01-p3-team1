# INF 배포 코드 공개·브랜치 동기화 변경 라우팅

- 작성일/수정일: 2026-10-17 (KST)
- 담당: INF 배포 코드 공개와 Git 통합
- 범위: 사용자 요청에 따른 비밀정보 점검, AWS 앱 배포 호환성 및 Kibana 운영로그의 분리 커밋·push. AWS 서비스 변경이나 재배포는 포함하지 않음.
- 출발점: feature/infra `ef5912e28d4cc81d4115e1e83b9442e10b39dc8b`, develop `e2b7d62a2161856714b14de8f56ca32611886969`.

## 기준 → 코드 → 인계

| 구분 | 실제 코드 | 공개·통합 경계 |
|---|---|---|
| 기반 인프라 | aws-infra의 공개 설치기·lock·샘플·검사·CI | feature/infra의 0.3.19 공개 코드를 develop에도 동기화. 루트 제품 AGENTS/CONTRIBUTING/제품 명세는 각 브랜치 내용을 보존 |
| AWS 앱 배포 | deployment/aws, pipeline/weather 실행·커넥터, 공통/광고 설정, 카탈로그 저장·읽기·동점 탐색 | 배포 도구는 두 브랜치에 기록하며 공통·추천·광고 앱의 실제 수정은 앱 소스가 있는 develop에만 기록 |
| Kibana 운영로그 | aws-infra/observability, nginx의 선택적 /ops/ include | 원본은 feature/infra 작업 폴더에서 작성. 수집·마스킹·지표·설치·V2 대시보드 20개 지표와 동시 편집 보호 검사를 두 브랜치에 같은 코드로 보존 |
| 인프라 버전 | aws-infra/VERSION·CHANGELOG·공개 샘플 템플릿 | 기반 동기화 시 0.3.19, 운영로그 변경에서 실제 공개 버전 0.3.20과 V2 대시보드 기록 적용. 실제 AWS 설치 세대의 identity는 변경하지 않음 |
| 수령 문서 | 기존 docs/handoff/infra와 제품·음악·날씨 인계 원문 | 이미 있는 파일을 덮어쓰거나 수정하지 않음. 새 APPLICATION-CONTRACT/CONTROL-FENCING/INTEGRATION-READINESS/TEAM-ACCESS 문서는 원본 바이트로 추가. 기존 인계의 과거 버전·구현 상태와 최신 코드 차이는 이 기록 및 분야별 라우팅으로 구분 |

## 커밋 경계

1. `fix(infra): AWS 앱 배포 호환성과 카탈로그 발행 안정화`
   - 기반 코드 동기화, 배포 공개 도구, 환경 예시·개인정보 보호 규칙, 앱 호환성 보완과 관련 검사를 포함.
   - nginx의 운영로그 include는 두 번째 커밋에서 추가하여 앱 연결과 관제 연결을 분리.
2. `feat(deploy): Kibana 운영로그 파이프라인 변경 및 대시보드 운영 지표 최신화`
   - Filebeat/ES/Kibana·운영 메타데이터·지표 20개·V2 saved object·편집 충돌 보호·운영 라우팅을 포함.

## 공개 제외와 검증 경계

- .env 실값, 개인 AWS 설정, 실제 계정 식별자, 키·인증서·자격 증명, .private/.state, 실제 원본 CSV·덤프·실행 로그·설치 묶음·Kibana 백업/게시 ledger·.DS_Store를 새 커밋에 넣지 않음.
- .gitignore는 두 작업 폴더의 보호 규칙을 합치고 비밀값 없는 .env.example/.env.sample/.env.template만 예외로 유지. 개인 PC 절대 경로는 공개용 AWS 배포 기록에서 제거.
- 정확한 변경 경로·blob을 검사하고 기존 환경 파일/비공개 runtime의 비밀값과 대조. 테스트용 고정 문자열·샘플 계정·공식 공개 키/해시는 실제 비밀정보와 구분.
- 격리된 체크아웃에서 백엔드·Spark 커넥터·기반 인프라 단위 검사, 대시보드 충돌 보호 검사, 공개 파일 검사와 CF schema/guard·샘플 재생성 일관성을 확인. 실제 AWS/API·운영 DB·유료 모델을 호출하지 않음.
- 다른 에이전트의 작업 폴더·브랜치·인덱스를 변경하지 않고 원격 최신 커밋을 기준으로 작성. 원격 선행 커밋이 달라지면 강제 push하지 않고 재검토.
- 실제 기본 추천의 일반 취향 탐색 시간 초과, 업무 HA와 운영 경보/보관의 남은 제약은 각 기존 라우팅의 검증 범위를 유지.

코드 반영·검증의 실제 명령과 결과는 로컬 비공개 공개 준비 기록에 두며, 최종 커밋 해시·범위는 두 브랜치의 Git log/show로 확인한다. Git 반영은 추가 AWS 배포를 뜻하지 않는다.
