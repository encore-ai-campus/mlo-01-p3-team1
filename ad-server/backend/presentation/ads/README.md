# 광고 로컬 프레젠테이션

- 작성일: 2026-10-16
- 수정일: 2026-10-16

개발 총괄은 `content.json`에서 안내 문구, `ads.css`의 `:root`에서 색/간격,
`../../templates/ads_sandbox*.html`에서 배치를 수정할 수 있습니다.
`ads-page.mjs`는 화면 상태/이벤트, `ads-api.mjs`는 API 경로/전송,
`time.mjs`는 KST 입력/UTC 변환을 담당합니다.

실행 명령·시안 출처·필수 DOM id·정식 화면 이식 경계는
[수정 가이드](../../../../docs/development/ads/광고_로컬_화면과_프레젠테이션_수정_가이드.md)를 따릅니다.
이 폴더를 직접 열어 실행하지 말고 sandbox 서버의 `/dev/ads/`에서 사용합니다.
화면 수치는 기존 API 결과이며 모의 운영 지표를 만들지 않습니다.
