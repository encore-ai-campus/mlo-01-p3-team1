# 메인 헤더 MUSIC X WEATHER 스크린샷 복원 — 변경 라우팅

- 작성·수정일: 2026-10-19
- 기준: 사용자 제공 2026-10-19 메인 화면 스크린샷, 운영 Django `a7dfafb`
- 작업 범위: React 공개 화면 상단 헤더의 대형 로고·좌/중/우 배치만 복원
- 이력: AWS 전용 UI 작업 트리 `codex/screenshot-header-aws-only-20261019`에서 검증 후, 최신 `origin/main` 기반 별도 통합 작업 트리에서 같은 소스를 선택적으로 반영
- AWS UI 릴리스: `music-weather-header-88ec27ebf77f28e1`

## 사용자 결정과 기준

첨부 스크린샷과 동일한 구성인 왼쪽 `muther.` 서비스명, 가운데 파형·태양 SVG와 대형 `MUSIC X WEATHER`, 오른쪽 홈·오늘의 선곡·사용 안내·로그인 메뉴를 제공한다. 별도 오른쪽 아래의 작은 고정 로고 배지는 제거한다. 광고·히어로·지역 선택·날씨·추천 카드 기능을 변경하지 않는다.

## 소스 변경

- `frontend/src/components/Header.tsx`: 중앙 브랜딩 링크를 배치하고 과거 고정 배지 마크업을 제거한다.
- `frontend/src/components/MusicWeatherHeaderLogo.tsx`: 반응형 SVG 파형·태양·구름과 브랜드 타이포그래피를 구성한다.
- `frontend/src/components/header-brand.css`: 데스크톱 3열 그리드, 태블릿·모바일 2행 배치와 스타일을 정의한다.
- `frontend/src/components/MusicWeatherHeaderLogo.test.tsx`: 스크린리더 이름·파형 SVG·브랜드 문구를 검사한다.

서버의 Django·SSO·Kibana·광고 API·날씨·추천 워커와 DB는 변경하지 않았다.

## 검증과 배포

- 프론트엔드 68개 테스트 통과, TypeScript 및 Vite 운영 빌드 성공.
- Chrome 1425/1024/768/390px, 중앙 정렬·메뉴·선곡표 이동·스크롤 넘침 없음·JS 오류 0건 검증.
- 2026-10-19 AWS Control B → Control A 순서로 정적 자산만 반영. 양쪽 Nginx 설정 검사 성공, ALB 2/2 healthy.
- 공개 URL의 HTML·JS·CSS 해시가 패키지와 일치하며 관리자 API 비인증 차단 유지. 지역 목록 API HTTP 200 확인.
- 기존 운영 앱 버전 `a7dfafb`은 유지한다. 원격 `develop`의 추가 YouTube 변경은 **이번 UI 배포 범위가 아니며 별도 배포** 대상이다.
- 운영 검증 증빙과 복구 스크립트: `aws-infra/.state/operations/screenshot-header-20261019/release-status.json`. 이 디렉터리는 비공개 운영 파일로 Git에 올리지 않는다.

## 미완료·인계

- 2026-10-19 후속 사용자 승인으로 로컬에서 검증한 헤더 소스 4개를 원격 `main`에 통합한다. UI 외의 Django·Kibana·재생 로직 파일은 변경하지 않는다.
- AWS에는 앞서 동일한 헤더 소스의 정적 빌드만 배포했다. 이번 Git 통합 자체는 AWS 재배포를 수행하지 않는다.
- 원본 로고 별도 파일이 제공되지는 않았으므로, 첨부 화면을 시각 기준으로 SVG로 재구성했다.
