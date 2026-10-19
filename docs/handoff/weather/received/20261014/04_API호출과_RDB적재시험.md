# 04. API 호출과 실행 기준

수정일: 2026-10-14. 기상청 API허브 사용. 공공데이터포털 JSON API와 구분.
키는 KMA_API_KEY 또는 .env. 아이디·비밀번호 불필요. 인증값 공유 제외.

## 요청

| 자료 | 경로·인자 |
|---|---|
| 실황 | /api/typ01/cgi-bin/url/nph-dfs_odam_grd — tmfc, vars |
| 초단기 | /api/typ01/cgi-bin/url/nph-dfs_vsrt_grd — tmfc, tmef, vars |
| SNO | /api/typ01/cgi-bin/url/nph-dfs_shrt_grd — tmfc, tmef, vars=SNO |
| KIM | /api/typ06/url/nwp_nc_sfc2d_down.php — group=KIMG, vars=tcld, UTC tmfc, hf, 영역, dataType=CSV |

기본/SNO는 항목·대상당 전국 배열 1요청. nx·ny별 호출 없음.
KIM은 대상당 영역 CSV. 별도 모델 격자를 연결.
HTTP 상태·본문 형식·격자 개수·값을 확인한 후 발행.

## 자동 실행

실황: 현재 10분 관측 시각부터. 초단기: xx:30+15분부터.
SNO: 발표 30분 여유. KIM: 최소 6시간 지난 발표, 현재 정시 + 초단기 대상의 시간별 값.
성공 요청은 제외, 최신 우선, 이전 실패는 별도 큐 유지.
실황 실패 60초·다른 자료 실패 300초 뒤 재시도. 한 요청 후 최신 계획 재확인.
응답 시간이 있으므로 정각 도착·정확히 60초 후 완료를 보장하지 않음.
401/403/429 새 호출 중단. 인증 URL·키·원천은 로그 제외.

## 개발 기본값 — 운영 최종값 아님

pipeline/runtime_config.json: 누락 최대 6시간·12시도. 종료 시 failed 기록.
재시작 후 큐 복원. 새 수집기가 멈춘 구간도 최근 6시간 계획 복원.
안전 예산 하루 9,000요청·4GB. 재시작해도 사용량 유지, 계정 전체 사용량과는 별개.
관측 만료 30분·예보 120분·KIM 720분·SNO 300분은 조회/전달 개발값.
체감·주야간·강수 변화 알림은 기존 자료 활용. 정상 요청 수 증가 없음.

## 요청 수

연속 운영의 정상 고유 계획: 실황 1,152 + 초단기 1,584 + SNO 72 + KIM 48 = 2,856/일.
KIM은 대상당 영역 1요청. 48시간 스케줄의 둘째 날 고유 요청 계산, 1,625배 아님.
KIM 시간별 실응답: 15·16·17시 각 1,625격자 유효. 예측 정확도 검증과 구분.
최초 시작·누락 복구·재시도·다른 사용량 별도. 기존 2,904를 현재 실측 총량으로 쓰지 않음.
원천 미보관이어도 API 수신량·Kafka 전송량 발생. 실제 한도는 공식 안내·계정 기준 확인.

기존 SQLite 날씨 적재는 과거 시험, 운영 DB 선정 아님.
collect()의 파일 보관 함수는 회귀 시험용. 자동 실행·단발 CLI는 메모리 스트림 경로.
로컬 Kafka → Spark → ES 최신 조회 연결. 운영 클러스터·PostgreSQL 매핑·개인 로컬 이력은 별도 연결.

## API 수집 로그

호출 1회당 1건. 자료 종류·항목·요청 조건·발표/대상 시각·요청/수신 시각 기록.
현재 requests.jsonl: HTTP 상태·오류 종류·응답 바이트·소요 초·이벤트 수·원천 해시 기록.
ok는 응답 해석과 Kafka 전달까지의 성공. ES 반영 완료 의미 아님.
보완: 요청 식별값·시도 번호·수신/발행/정제/ES 반영 단계별 결과 연결.
운영 방향: ES pipeline-logs-v1 → Kibana. 공용 전송·보관 기간은 미구현/미정.
인증키·인증 URL·원천 본문 제외. 전송 대기 로그의 저장·재전송 정책은 연결 시 확정.

[공식 API](https://apihub.kma.go.kr/apiList.do?seqApi=10) / [한도](https://apihub.kma.go.kr/apiInfo.do) / [KIM](https://apihub.kma.go.kr/apiList.do?seqApi=9)
