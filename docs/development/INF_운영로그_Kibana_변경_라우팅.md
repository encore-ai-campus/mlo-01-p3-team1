# INF 운영로그·Kibana 변경 라우팅

- 작성일·수정일: 2026-10-16
- 담당: INF. 사용자 요청에 따른 운영로그 전송·대시보드 구현 및 배포.
- 이번 범위: Control A 로그의 ES 발행, 다른 13대 로그 누락 확인·수집, 로그인 필수 Kibana. 기존 앱 배포/음악 발행 작업과 별개입니다.
- 공개 /ops/ 연결은 사용자의 “관리자 로그인 조건으로 HTTPS /ops/ 연결 승인” 답변 후 적용했습니다. 커밋·push·PR는 하지 않았습니다.

## 계약 → 코드 → 실행 근거

| 기준·문제 | 변경 코드 | 확인 결과 |
|---|---|---|
| Q-07 운영 통합 관제, INF 모니터링·운영 책임 | 인프라 저장소 aws-infra/observability/ | 별도 운영로그 인덱스·Data View·대시보드 생성 |
| 날씨 파일만 기록되고 optional ES 로그 설정이 없음 | Filebeat의 weather 입력, request_id 지연 상관 지표 | Control A 수집·정규화/ES 발행 성공·실패 조회 |
| journal·Kafka·ES·Spark·DB 파일을 중앙에서 조회할 경로 없음 | 역할별 journald/filestream 입력, Mongo 실제 mongod.log 경로 보완 | 14대 모두 실제 ES 수신 및 최근 heartbeat 확인 |
| 업무 인덱스와 운영로그의 용도 구분 | ops-mlo-* 템플릿·전용 writer/reader·Kibana 서비스 토큰 | 기존 weather-stream-current-v1-aws 유지 |
| 추천 성공률/시간·피드백 상태·광고 원본 로그 상태 필요 | app_metrics.py / metrics.py의 읽기 전용 메타데이터 조회 | 추천 종료 작업 19건(성공 6·실패 13), 피드백 및 광고 audit 지표 확인. 실패에는 기존 배포 점검 이력 포함 |
| 이후 앱 배포에서도 운영 경로 보존 | deployment/aws/control-nginx.conf.in의 optional include 1줄 | 양쪽 Control nginx 검증/reload, 공통 앱 재시작 없음 |
| 외부 운영자료 접근 보호 | HTTPS /ops/ + 별도 관리자 로그인 | 비인증 saved-object API 401, 인증 후 200, 기존 앱/health 200·내부 API 403 |

인프라 코드는 별도 인프라 체크아웃의 `aws-infra/observability/`와 VERSION 0.3.20/CHANGELOG에 있습니다. 이 앱 저장소에서는 nginx include와 이 담당 기록만 추가했습니다. 수령 원문과 다른 담당자의 기존 수정은 보존했습니다.

## 실제 실행·검증

- 기존 14 EC2·5 VPC 유지. Control B에 Kibana 8.19.23, 각 서버 Filebeat 8.19.23. 공식 SHA-512 확인.
- 별도 CloudFormation ingress 14개(/32, private 8444), cfn-lint·cfn-guard·서비스 변경 세트 검증 및 CREATE_COMPLETE 확인. IAM 권한/peering/새 EC2 추가 없음.
- 원본 JSONL·journal·MongoDB 감사 기록은 보존합니다. 전송 전 인증정보·query·클라이언트 식별자·허용하지 않은 JSON을 제거합니다.
- 최종 확인 집계 94,285건, 14대 heartbeat 수신. 14/14 active, 미전송·실패·폐기 0건(검증 시점).
- 실제 Filebeat를 분리한 localhost 시험: 강제 종료 후 disk queue 복구, 503 재시도, 부분 429 재시도, 회전, 마스킹 통과. 고유 시험 이벤트 53건, 운영 ES 시험 쓰기 0건.
- 실제 브라우저에서 로그인·날씨/지연/서버/추천/피드백 차트 확인. 빈 데이터 차트 예외 수정. 관리 권한이 없는 선택 기능 Streams API의 403은 유지합니다.
- 영수증·집계·화면: 인프라 저장소 `.state/operations/observability/run-20261016/`.
- 계정 비밀번호: 인프라 저장소 `.private/observability/<generation>/KIBANA-ACCESS.txt`, 0600. 공개 문서에는 비밀값을 기록하지 않습니다.

## 남은 운영 제약

- gateway와 Kibana는 Control B, gateway 대상은 ES01에 의존합니다. 장애 시 노드별 최대 512MB disk queue로 대기하며 장기 장애의 무손실을 보장하지 않습니다.
- 추천 메타데이터는 최근 7일 최대 5,000건, 광고는 컬렉션별 최근 5,000 log_record 조회입니다. 현재 자료는 한도 내이며 장기 전수 감사 복제/legacy log_relay 발행은 별도입니다. 볼륨 증가 시 cursor/change stream 확장이 필요합니다.
- 설치 전에 이미 삭제된 원본은 복원하지 못합니다. 비구조화 파일 backfill 시각은 수집 시각일 수 있고 시험 단계 Control B 접근 로그 일부의 중복 이력은 보존했습니다.
- 보관 만료/자동 삭제/외부 알림은 새로 설정하지 않았습니다. 장기 운영 전 디스크와 보관 정책을 정해야 합니다.
- 전체 인프라 철거 전 이번 별도 *-ops-network ingress 스택을 먼저 제거해야 합니다. 기존 foundation destroy에 자동 편입하지 않았습니다.
- 자세한 운영·복구·설정 계약은 인프라 코드 `aws-infra/observability/README.md`를 따릅니다.
