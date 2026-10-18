# INF 운영 대시보드 개선 변경 라우팅

- 작성·수정일: 2026-10-17 (KST)
- 사용자 요청: 가로 축 라벨, 웹 대시보드 형태의 디자인, 실제 로그 조합 기반 약 20개 지표. 다른 에이전트의 변경 보호.
- 범위: Kibana 저장 객체 및 인프라 저장소의 새 dashboard_v2.py / test_dashboard_v2.py / DASHBOARD-V2.md. 수집기·앱 소스·DB·네트워크는 변경하지 않았습니다.

## 원문 → 코드 → 검증

| 요청/기준 | 구현 | 검증 |
|---|---|---|
| 긴 축 라벨의 가독성 | 모든 축 labelAngle 0, 범주형 가로 막대, 축 끝 flush/bound·container 자동 크기 | 실제 브라우저에서 글자 방향과 가로 넘침 0 확인 |
| 웹 대시보드 같은 가시성 | 헤더·상태 카드 6개·트래픽/추천/날씨/서버 운영 4개 영역, 통일된 색상/여백/범례 | 25개 시각화(지표20+장식5) 렌더링, 경고창·차트 오류 없음 |
| 실무 지표 | HTTP 오류율/구간 요청량/상위경로, 추천 성공·원인·P50/P95, 날씨 단계·오류·지연, 오류 heatmap·heartbeat·서비스 상태·피드백·광고 무결성 | 실제 ES 쿼리 20개 모두 성공 |
| 올바른 지표 해석 | 최신 gauge만 합산, 누적 counter 반복 합산 금지, LIVE와 기간 조회 구분, 미수신/0건/정상 표시 | 실제 수신 14/14, queue 0·광고 0·서비스 정상 구분 화면 확인 |
| 다른 작업자 보호 | 기존 dashboard/시각화 백업, 새 music-ops-v2-* 이름공간, 기존 module 보존, saved object version 조건부 update | 기존 dashboard.py 해시 동일; 충돌 시 쓰기 차단 2개 및 패널 겹침 검사 1개 통과 |

- 기존 live dashboard ID music-operations-v1을 유지했습니다. v2 검토본은 별도 이름으로 구분합니다.
- 기존 시각화 12개는 삭제하지 않았습니다. 원격 version이 변경됐거나 새 시각화의 소유 영수증이 없으면 덮어쓰지 않습니다.
- 상세 지표 산식/한도/보관 제약은 인프라 코드 aws-infra/observability/DASHBOARD-V2.md에 기록했습니다. CPU·전체 서버 메모리·HTTP 응답시간·Kafka offset lag를 수집하지 않은 상태에서 추정 지표로 넣지 않았습니다.
- 조회 기간의 기존 배포 점검 실패와 초기 backfill 중복/수집 시각의 한계는 유지됩니다. 이 대시보드 작업으로 업무 앱의 장애 해결 또는 수집 범위 확대를 완료 처리하지 않습니다.
- 영수증·원격 백업·쿼리 검증·화면: 인프라 저장소 .state/operations/observability/dashboard-redesign-20261016/.
- 공개 파일 비밀값 검사 및 git diff --check 통과. 공유 VERSION/CHANGELOG와 수령 문서는 이번 작업에서 수정하지 않았습니다. 커밋·push·PR는 하지 않았습니다.
