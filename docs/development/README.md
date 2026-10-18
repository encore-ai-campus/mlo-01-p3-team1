# 개발 문서와 현재 코드 경로

2026-10-18 브랜치별 반영 여부·충돌 해결·시험·로컬 보존은 [전체 feature 동기화 기록](./feature_전체_동기화_변경_라우팅_20261018.md)을 확인합니다.

저장소 접속 설정·초기화·실행·준비 점검은 [설정 기반 서비스 전환](../runbook/설정_기반_서비스_전환.md)과 [통합 라우팅 10절](./서비스_통합_구현_변경_라우팅.md#10-설정-기반-저장소-전환과-초기화--2026-10-16)을 확인합니다.

현재 CSV Gemini 재설정·지역 미설정 시 OFF·HTTP `phase3-20261016.3`은 [통합 라우팅 9절](./서비스_통합_구현_변경_라우팅.md#9-csv-gemini-재설정과-날씨-미설정-처리--2026-10-16)을 우선합니다. 실제 Gemini 호출은 모델 혼잡503으로 성공 미확인입니다.

2026-10-16 후속 결정인 **전국 지역 계층 선택·광고 목업 적용·OFF 지역 생략**의 현재 코드/입력 계약은 [통합 라우팅 7절](./서비스_통합_구현_변경_라우팅.md#7-사용자-지적-3건의-실제-구현-수정--2026-10-16)을 우선합니다. 이전 원문의 OFF 지역 필수는 변경 전 이력입니다.

- 작성일: 2026-10-16
- 수정일: 2026-10-18

현재 파일을 수정할 때는 [통합 폴더 변경 라우팅](./통합_폴더_정리_변경_라우팅.md)의 현재 경로·이동 매핑을 먼저 확인합니다. 아래 기존 인계는 원문/이력이며 예전 경로를 담고 있을 수 있습니다. 원문을 수정하지 않고 변환표로 연결합니다.

| 작업 | 기준/인계 | 현재 코드 |
|---|---|---|
| 제품/담당 | [AGENTS](../../AGENTS.md), [구현 설계](../product/카페_음악_서비스_구현_설계도.md) | [루트 폴더 안내](../../README.md) |
| 추천·음악 | [C 작업 라우팅](./C_코드초안_정리기준과_작업라우팅.md), [C 실행 인계](../runbook/C_구현과_연결_인계.md) | backend/recommendation, backend/music, pipeline/music, frontend/src/features/recommendation |
| 음악 정본·일반 후보 | [정본 정리](./음악_재생_정본_변경_라우팅.md), [시즌 필터](./음악_시즌필터_변경_라우팅.md) | music_playback, analysis/weather_music_20261016/general |
| 키 없는 외부 재생·등록/검수 | [최신 검증](../acceptance/YouTube_키없는_등록과_검수_검증_20261016.md), [변경 라우팅](./YouTube_키없는_등록과_검수_변경_라우팅.md) | PublicPage 외부 기본·접이식 iframe 보조·URL/CSV/미연결 검수·별도 로컬 레지스트리. 키/LLM 불필요 |
| 앞 단계 중앙 iframe 음악 재생 | [당시 중앙 재생 검증](../acceptance/대시보드_중앙_YouTube_iframe_검증_20261016.md), [플레이어 코드](./음악_iframe_플레이어_변경_라우팅.md), [선택 검색 코드](./YouTube_자동검색_변경_라우팅.md), [선택적 API 키 설정](./music/YouTube_API_키_발급과_서버_설정.md) | 이전 주진입 검증 이력. 현행은 위 외부 기본/분리 검수이며 API 검색은 기본 비활성 |
| 기존 대시보드 YouTube 연결 | [기획·구현 가이드](./music/YouTube_로컬_재생_기획과_구현_가이드.md), [화면/API 연결](./기존_대시보드_YouTube_연결_라우팅.md), [일반 추천/재생 시험 분리 검증](../acceptance/일반_추천_후보와_재생시험_분리_검증_20261016.md), [47곡 재생 시험 검증](../acceptance/YouTube_47곡_매핑_검증_20261016.md), [앞 연결 단계](../acceptance/기존_대시보드_YouTube_연결_검증_20261016.md) | frontend/src/features/recommendation, backend/recommendation, analysis/youtube_mapping_20261016, [Python 코드 색인](../music-playback-routing/README.md) |
| iframe 검수 보조/이력 | [보조 도구 구현](./YouTube_재생_변경_라우팅.md), [이전 통합 검증](./음악_로컬_재생_통합_검증_라우팅.md) | prototype/youtube-player. 사용자 주진입점은 위 기존 대시보드 |
| 날씨 | [수령·차이 라우팅](./날씨_코드_수령과_연결_라우팅.md), [제공 원문](../handoff/weather/received/20261014/) | backend/weather, pipeline/weather, frontend/src/features/region-weather |
| 광고 | [광고 코드 색인](../backend-routing/README.md), [광고 실행 인계](../runbook/광고_서버_개발_준비.md) | ad-server/backend, frontend/src/features/ad-banners |
| 환경/실행 | [서비스별 환경 위치](../../config/environments/README.md), [통합 변경/검증](./통합_폴더_정리_변경_라우팅.md) | frontend/vite.config.ts, 각 실행 단위의 의존성/설정 |
| develop 문서 전체 | [develop 문서 목록](./develop_문서_목록.md) | 기준 커밋의 원본 Markdown과 계약/고정 자료 JSON |

루트 frontend는 공개 앱이며 광고의 정식 관리자 React 화면 연결은 대기입니다. ad-server의 presentation/templates는 기존 로컬 sandbox 도구입니다. 경로 정리를 화면/인증/DB 구현 완료로 해석하지 않습니다.

기상청 키 파일 배치·로딩의 후속 변경은 [날씨 환경설정 변경 라우팅](./날씨_환경설정_변경_라우팅.md)을 확인합니다.

현재 통합 구현·날씨 6개 원문 우선 적용·공통 인증/광고/음악/피드백 연결 및 검증은 [서비스 통합 구현 변경 라우팅](./서비스_통합_구현_변경_라우팅.md)을 우선 확인합니다. 이전 라우팅의 MongoDB 날씨·별도 관리자 ES 발행 설명은 변경 전 이력입니다.
