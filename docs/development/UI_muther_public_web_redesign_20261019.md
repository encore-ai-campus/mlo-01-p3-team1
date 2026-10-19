# Muther 사용자 웹 전면 개편 — 2026-10-19 변경 라우팅

- 작업 담당: 공개 프론트엔드 UI
- 작업 브랜치: \`develop\` (작업 시 기존 HEAD \`e2b7d62\`)
- 요청: 참조 화면 기반 Muther 메인/오늘의 선곡 페이지 분리, 3단계 지역 선택, 같은 지역 상태 공유, 광고 상·하단 자리 유지
- 환경: 로컬 Mac 검증. AWS 배포/데이터 변경/원격 Git 푸시는 하지 않음
- 참고: \`AGENTS.md\`, \`docs/product/\`, \`docs/handoff/weather/\`의 기존 날씨-선곡 계약. 원문은 수정하지 않음

## 변경 흐름

| 요구사항 | 구현 위치 | 실제 동작 |
|---|---|---|
| Muther 첫 화면 / 슬로건 | \`Header.tsx\`, \`HeroBanner.tsx\`, \`muther-home.css\` | 슬로건 "오늘의 날씨를 들어보세요", WEATHER 로고와 날씨 분위기 배너 |
| 오늘의 선곡 별도 화면 | \`PublicPage.tsx\`, \`PlaylistIntro.tsx\` | \`/\` 홈, \`/playlist\` 선곡 조합, History API 경로 전환; 실제 생성/평가 API는 기존 로직 유지 |
| 첫 화면의 지역 공유 | \`PublicPage.tsx\` | 두 화면에서 하나의 \`choices.region_id\`를 사용; 저장된 region_id 재접속 시 재선택 검증 |
| 시·도 / 구 / 동 선택 | \`RegionPicker.tsx\` | \`/api/regions/tree\` 응답을 기존 PostgreSQL region_id 기준으로 계층 필터링; 최종 선택 확정 시에만 상위 상태 업데이트 |
| 날씨를 풍성하게 표현 | \`WeatherPanel.tsx\` | 선택 지역, 현재 관측, 유효한 시간 구간의 날씨 아이콘/상태 표시; 미래 시간별 기온은 응답에 없으면 '—' |
| 날씨별 이미지 미리보기 | \`MoodGallery.tsx\` | 이미지/분위기 설명 **미리보기**. 별도 카탈로그/실제 재생 버튼을 꾸며내지 않음 |
| 광고 유지 | 기존 \`Banner.tsx\` | 운영 광고 API·측정·호출 로직 불변, 상단 광고는 헤더 직후 / 하단 광고는 메인 후 |
| 테스트 | \`tests/regionHierarchy.test.tsx\` 및 기존 테스트 | 계층 ID, 지역 필터, 접근성 라벨, 메뉴 링크, 날씨 누락을 단위 검증 |

### 계약과 안전성

- \`region_id\`는 기존 응답 원본 ID만 이용하고 \`/api/weather?region_id=...\`를 기존 코드로 호출함.
- 기존 \`/api/regions/tree\`는 실 운영에서 PostgreSQL 매핑 약 3,564개를 반환한 것으로 확인됨. API/DB 스키마를 변경하지 않음.
- 날씨 ON/OFF, 추천 요청, Gemini 재생성, 추천 작업 취소, 제외/별점/좋아요·싫어요 API는 변경하지 않음.
- 동시 요청 시 기존 AbortController 처리를 보존하고 날씨 미지원 정보는 임의 보간하지 않음.
- 타인의 기존 미커밋 수정(특히 추천 취소 기능 등)을 덮어쓰지 않고, 이 작업과 무관한 파일은 커밋 대상에서 제외함.
- 현재 \`develop\`가 \`origin/develop\`보다 뒤처져 있음. 별도 병합/동기화 없이 요청에 따라 로컬 \`develop\`에 커밋하며 \`push\`하지 않음.

## 로컬 검증

- 프론트엔드: \`frontend/\`에서 \`npm run build\`, \`npm run test\`.
- 브라우저: Chrome + Puppeteer에서 \`서울특별시 → 구로구 → 구로제1동\` 지역 변경, 홈→\`/playlist\` 이동, 같은 선택 유지, 브라우저 뒤로 가기, 모바일(390px) 및 데스크톱(1536px) 가로 넘침, uncaught JS 오류 유무 확인.
- 로컬 Django: 별도 /tmp 가상환경 및 별도 /tmp SQLite DB에 \`seed_c_demo\`로 64곡 합성 테스트 카탈로그 저장 후 Django/worker 실행. **실제 AWS PostgreSQL과 연결하지 않음.**
- 로컬 추천 워커: 시연용 지역을 선택한 뒤 45곡 선곡표 생성 테스트 성공.
- 로컬 미리보기 URL: \`http://127.0.0.1:5173/?ad_preview=1\` (광고 샘플 렌더링용 플래그). 선곡 페이지 URL: \`http://127.0.0.1:5173/playlist?ad_preview=1\`.
- 실제 PostgreSQL, 원격 API Gateway/CloudFront/운영용 광고 측정, 실제 3시간 실시간 온도 예보는 로컬 검증으로 대체하지 않음.

## 이미지 출처

- 히어로: Pexels, cottonbro studio, photo 6686440 (무료 이용 사진)
- 장르/날씨 이미지: Unsplash 공개 이미지들 (기존 API/음악 데이터와 관계없는 시각 자료)
- 펭귄 안내는 저장소의 기존 자산을 재사용함.

## 배포 전 남은 확인

- 최신 원격 \`develop\` 55개 후속 커밋과 새 UI 파일 간 3-way 병합 영향 확인
- 실제 AWS 배포 환경의 3,564 지역 목록/권한/응답 계약 재확인
- 실제 CloudFront 경유 브라우저 테스트 (SSM 직접 조회와 별도)
- 실제 음악 카탈로그/원본 이미지 사용 정책 및 라이선스 검수
