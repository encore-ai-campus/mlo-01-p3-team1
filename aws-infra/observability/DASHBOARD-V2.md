# 운영 대시보드 v2 · 지표 사전과 변경 경계

- 작성일: 2026-10-17 (KST)
- 변경 범위: Kibana 저장 객체와 새 `dashboard_v2.py`. 수집기·앱·DB·nginx·인프라 설정 변경 없음.
- 기존 `dashboard.py`와 수령 문서, 다른 담당자의 수정은 보존합니다. 기존 대시보드 ID를 유지해 기존 링크를 사용할 수 있습니다.
- 디자인: 남색 헤더, 핵심 카드 6개, 트래픽·추천·날씨·서버 운영 영역, 일관된 색상/여백/범례, 가로 축 라벨. 긴 범주는 가로 막대로 표시합니다.

## 지표 20개

| # | 지표 | 집계·해석 |
|---|---|---|
| 1 | 수신 서버 / 14 | 전체 서버 최근 3분 heartbeat의 고유 host 수. 조회 시간/필터와 독립적인 LIVE 카드 |
| 2 | 앱 HTTP 5xx율 | Nginx 접근 관측 중 5xx 비율. health·운영 화면 경로 제외 |
| 3 | 추천 성공률 | SUCCEEDED / (SUCCEEDED+FAILED+EXPIRED), 비시험 카탈로그의 종료 작업 |
| 4 | 추천 처리 P95 | 성공 작업 생성→결과 저장, 큐 대기 포함. HTTP 응답시간과 다름 |
| 5 | 날씨 전달 P95 | 요청 시작→같은 request_id가 포함된 ES projection 배치 완료 |
| 6 | 로그 전송 대기 | LIVE 최근 3분 서버별 최신 queued_events의 합. 누적 snapshot 합산 금지 |
| 7 | 앱 요청량·응답 상태 | 10분 구간의 2xx/3xx/4xx/5xx 관측 로그 구성 |
| 8 | 요청 상위 경로 | 안전하게 정규화된 접근 메시지에서 경로 추출. 긴 segment를 :id로 묶은 상위 8개 |
| 9 | 추천 방식별 종료 상태 | 규칙/Gemini 방식과 성공·실패·만료를 교차 집계 |
| 10 | 추천 실패 원인 | 실패·만료 error_type 상위 8개, 원인 없는 기록은 별도 표시 |
| 11 | 추천 처리시간 추이 | 성공 작업 10분 cohort의 P50/P95. 요청 생성시각 기준 |
| 12 | 날씨 단계별 통과 | collection 시도의 API 수신·파싱·Kafka ACK. 동일 시도가 여러 단계에 포함되므로 합산 금지 |
| 13 | 날씨 실패 원인·종류 | collection/es_projection 오류와 원본 category의 구성 |
| 14 | 날씨 수집 처리시간 | HTTP+파싱+Kafka 발행 elapsed_seconds의 10분 P50/P95. API 네트워크 시간만의 지표 아님 |
| 15 | 날씨 전달 지연 추이 | request_id 상관 지연의 10분 P50/P95, 배치 완료 기준 |
| 16 | 서버 오류 발생 구간 | host×10분 구간의 오류 로그 줄 수. stack trace 줄 수와 독립 장애 수를 구분 |
| 17 | 비활성 서비스 점검 | LIVE 최근 3분 unit별 최신 상태. inactive는 의도된 중지일 수 있어 장애 단정 금지 |
| 18 | 서버별 수신 상태 | 마지막 수신 간격. tooltip에 대기 gauge·Filebeat RSS 표시. 서버 전체 메모리 지표 아님 |
| 19 | 피드백 데이터 흐름 | 최신 outbox 대기·수신 원본·투영 이벤트. 수신/투영의 단위·중복 차이 때문에 차이를 미처리 수로 계산하지 않음 |
| 20 | 광고 로그·무결성 | 컬렉션별 최신 원본 저장·필수 누락·무결성 표본 오류. 표본을 전수 검사로 표현하지 않음 |

수집하지 않는 CPU 사용률·서버 전체 메모리·HTTP 지연·Kafka offset lag·청취 품질·매출은 추정하거나 만들어 넣지 않습니다. 값이 없으면 `—` 또는 데이터 없음으로 표시합니다. 의도된 0과 미수신은 구분합니다.

LIVE 상태(1·6·17)는 전체 서버 최근 3분을 보며 상단 시간/필터와 독립적입니다. 다른 그래프는 상단 시간·KQL·필터를 따릅니다. 추천 통계의 기존 배포 점검 실패, 초기 비구조화 파일 backfill의 수집 시각/중복 이력, 추천 최근 7일 최대 5,000건·광고 컬렉션별 최근 5,000건의 원본 메타데이터 조회 한도는 기존 수집기의 제약을 유지합니다.

## 다른 작업자 변경 보호

1. 기존 대시보드와 참조 시각화의 전체 JSON·version을 작업별 `.state` 디렉터리에 백업합니다.
2. 신규 시각화는 `music-ops-v2-*` 이름공간으로 만들며, 기존 12개 시각화를 수정/삭제하지 않습니다.
3. 별도 preview 대시보드에서 렌더링을 확인합니다. 최초 live 적용 전 기존 dashboard version이 백업 시점과 같은지 확인합니다.
4. 저장 객체 갱신은 Kibana update API의 version을 전달합니다. 수정 충돌(409)이나 다른 editor version을 발견하면 중단합니다. 새 객체도 소유 영수증이 없으면 덮어쓰지 않습니다.
5. 자신의 게시 ledger에 기록된 version/digest만 재사용합니다. 공유 버전/CHANGELOG나 수집 설정을 이 작업에서 수정하지 않습니다.

`test_dashboard_v2.py`는 live 수정 충돌 시 쓰기 0건, 자신의 시각화에 타 작업자가 수정한 경우 덮어쓰기 거부, 패널 배치 겹침/화면 밖 배치를 검사합니다.

## 배포와 복구

`Client`에는 기존 private public_url/viewer_password를 메모리로 전달합니다. 비밀번호를 명령 인자·공개 파일·로그에 쓰지 않습니다. `publish(client, state_dir, preview=True)`로 검토본, `preview=False`로 기존 ID에 적용합니다. `state_dir`에는 먼저 `dashboard-before.json` 백업을 두어야 하며 게시 ledger는 해당 작업 전용 디렉터리에 보관합니다.

복구할 때는 현재 version을 먼저 읽고 백업 attributes/references를 version 조건부 update로 되돌립니다. 백업 version을 무조건 재사용하거나 `overwrite=true`로 다른 변경을 지우지 않습니다. 원래 시각화 12개를 보존하므로 live dashboard를 복구해 참조할 수 있습니다. 검토본은 복구·비교용으로 남기며 자동 기본 배포 경로에는 넣지 않습니다.

근거: [Elastic Vega](https://www.elastic.co/guide/en/kibana/8.19/vega.html), [저장 객체 update API](https://www.elastic.co/guide/en/kibana/8.19/saved-objects-api-update.html). 실제 쿼리·화면 검증 영수증은 작업별 `.state/operations/observability/dashboard-redesign-*/`에 기록합니다.
