# 04. API 호출과 적재 기준

- 수정일: 2026-10-13

출처는 기상청 API 허브. 공공데이터포털 JSON API와 요청 규격 구분.
공통 인증 인자는 authKey. 인증키는 환경변수·로컬 입력창에서 전달, 문서·공유 파일에 기록 제외.

## 실제 요청 규격

기본 주소 `https://apihub.kma.go.kr`.

| 자료 | 경로 | 주요 인자 |
|---|---|---|
| 실황 | /api/typ01/cgi-bin/url/nph-dfs_odam_grd | tmfc=자료 시각, vars=항목 |
| 초단기 | /api/typ01/cgi-bin/url/nph-dfs_vsrt_grd | tmfc=발표, tmef=대상, vars=항목 |
| SNO | /api/typ01/cgi-bin/url/nph-dfs_shrt_grd | tmfc=발표, tmef=대상, vars=SNO |
| KIM 구름량 | /api/typ06/url/nwp_nc_sfc2d_down.php | group=KIMG, vars=tcld, tmfc=발표 UTC, hf=예측시간, 영역 경계, dataType=CSV |

기본·SNO는 항목 하나·대상 시각 하나당 전국 배열 한 번. nx·ny별 API 요청 없음.
KIM은 대상 시각별 영역 CSV 한 번. lon1·lat1·lon2·lat2로 전국 대표점이 들어가는 범위 지정.

KIM 예시: tmfc=2026101118, hf=6 → 한국 발표 10/12 03시, 대상 09시.
hf=9·12이면 대상 12·15시. 요청한 현재 시각에서 6시간 뒤라는 뜻 아님.
응답 CSV 자체에 발표 시각이 없으므로 요청 정보와 함께 보관.

## 수집 실행 기준

계획 생성은 현재 시각에서 30분 여유를 둔 기본 회차 사용.
KIM은 계산·공개 지연을 고려해 최소 6시간 지난 발표 회차 선택.
초단기 대상 범위를 감싸는 3시간 간격 시각 조회. 회차에 따라 3~4개 대상.
예보와 대상 시각이 맞는 값만 서비스 보완에 연결. 나머지는 이력 유지.

정상 판정: HTTP 상태 + 응답 형식 + 격자·항목·시각 확인.
HTTP 200이어도 자료 없음 본문은 적재 제외. 기존 자료 유지 + 실패 기록.
로컬 재요청은 최대 3시도, 실패 후 20초 대기. 401·403·429는 즉시 중단.

## 요청 수·용량

| 자료 | 하루 계획 요청 수 |
|---|---|
| 실황 | 8항목 × 144회 = 1,152 |
| 초단기 | 11항목 × 6시각 × 24회 = 1,584 |
| SNO | 9시각 × 8발표 = 72 |
| KIM | 시간당 최대 4시각 × 24회 = 최대 96 |
| 합계 | 최대 2,904. 재시도·다른 계정 사용량 제외 |

정해둔 주기를 자동 실행할 때의 보수적 상한. 반복 회차 재사용 시 감소.
일반회원 한도는 일 20,000건·5GB. 공식 안내 확인일 2026-10-12. 실제 사용량은 계정 전체 기준.

실측 표본: 기본·SNO 응답 약 0.341MB, KIM 전국 범위 3시각 합계 0.625MB·gzip 0.120MB·원본 수신 1.795초.
현재 표본 크기와 요청 상한으로 계산한 수신량 약 978MB/일. 자료·재시도에 따라 변동.
로컬 gzip으로 API 수신량 한도가 줄어들지는 않음. MongoDB·복제·인덱스 용량은 별도.

## 적재 방식

원문 gzip + 공통 JSON → Kafka → Spark → MongoDB 이력·최신 슬롯 → ES.
실제 저장 규격은 [03](./03_날씨_저장구조.md) 참고.
SQLite는 별도 로컬 적재 시험용. collection_attempt에 요청 결과, weather_reading에 한 격자·시각·항목의 측정값 저장.
운영 저장소를 SQLite로 선정한 의미는 아님.

출처 테스트 코드 참조: `pipeline/make_jobs.py` / `pipeline/collect.py`. 현재 저장소의 실행 파일·운영 완료 근거로 사용하지 않습니다. [공식 한도](https://apihub.kma.go.kr/apiInfo.do) / [KIM API](https://apihub.kma.go.kr/apiList.do?seqApi=9)
