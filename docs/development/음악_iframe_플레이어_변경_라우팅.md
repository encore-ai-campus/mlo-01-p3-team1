# 기존 대시보드 중앙 YouTube iframe 플레이어 변경 라우팅

- 작성일: 2026-10-16
- 수정일: 2026-10-16
- 작성/담당: C 공개 화면·음악 재생 프런트엔드 작업 에이전트
- 작업 범위: U-01/U-03/U-05 연결에 해당하는 로컬 시험. 새로운 태스크 완료·운영 통합을 확정하지 않습니다.
- 브랜치/기준 커밋: `feature/ad-logic` / `f22f974`
- 최신 사용자 결정: 별도 YouTube 탭 이동 대신 **기존 사용자 대시보드 가운데 앨범 이미지 영역의 iframe에서 자동 재생을 시도**하고 곡이 끝나면 다음 곡으로 연결합니다. 추천이나 영상 검색을 위해 LLM을 필수로 만들지 않습니다.

## 기준 → 구현 연결

[서비스 흐름](../product/카페_음악_서비스_기능_및_사용자_흐름_정리.md), [구현 설계도](../product/카페_음악_서비스_구현_설계도.md), [ON/OFF 추천 가이드](../product/카페_음악_추천_서비스_3차_컬럼_기반_추천_로직_가이드.md), [구현 태스크](../product/카페_음악_추천_서비스_3차_구현_태스크.md)의 2026-10-16 현행 계약을 통합 담당이 대조하고, 이 작업에서는 재생 컴포넌트와 큐 상태 머신을 구현합니다. 기존 전체 적격 후보/시즌 필터/176~184분/기본 규칙·명시 Gemini 재설정·소유/제외/평가/승인 계약은 변경하지 않습니다.

기존 [대시보드 YouTube 라우팅](./기존_대시보드_YouTube_연결_라우팅.md)의 곡별 외부 검색·전곡 매핑 완료 시 임시 네이티브 목록 이동은 앞 단계 구현입니다. 현재 사용자 정정은 그 화면의 가운데에 실제 삽입 플레이어를 배치하는 후속 변경입니다. 외부 watch 제공 여부와 iframe의 100/101/150 오류는 별개이며, 과거 VERIFIED 47개를 모두 삽입 재생에 성공한 자료로 재해석하지 않습니다.

수령 원문 `docs/handoff/music/`를 변경하지 않습니다. 추천 결과 items의 기존 곡명·아티스트·고유 ID를 소비하며, 재생 도중 건너뛴 곡 때문에 원본 선곡표·점수·시간을 덮어쓰지 않습니다. 실제 전체 재생시간은 원본 총시간과 다를 수 있고 누락 내역을 표시합니다.

## 프런트엔드 소유 파일과 핵심 함수

|파일|함수·클래스/변경 이유|
|---|---|
|`frontend/src/features/recommendation/YoutubePlayer.tsx`|`YoutubePlayer({playlistId, tracks, blockReason, onTrackChange?})`: 중앙 영역용 iframe·현재 곡명/아티스트·이전/재생/정지/다음·연결 재확인·재생 불가 곡 표시. 결과 ID/곡 순서 변경 때만 큐를 새로 만들고 같은 결과의 평가/승인 재조회로 현재 재생을 초기화하지 않음|
|`frontend/src/features/recommendation/YoutubePlayer.css`|기존 중앙 카드 안에 들어가는 스타일. 가시 iframe 최소 200×200, 16:10 비율, 제어·누락 표시. 전체 대시보드 스타일/광고 배치 변경 없음|
|`frontend/src/features/recommendation/youtubePlayerController.ts`|`YoutubePlaybackController`: 결과의 원래 곡 순서·재생 상태와 실패 기록을 관리. `start/findCandidates/loadNextCandidate`는 소유 결과 내 곡의 영상 후보를 조회·검증해 `loadVideoById`에 전달. `onPlayerState`는 실제 PLAYING을 본 현재 곡의 ENDED만 자동 다음 처리|
|같은 컨트롤러|`onPlayerError`: 2/100/101/150에 동일 곡의 다른 후보를 순서대로 시도하고 실패 ID를 제외한 재검색은 최대 1회 추가. 곡당 서로 다른 영상 최대 5개. 재생 불가 시 곡명/이유를 기록하고 다음 곡으로 이동|
|같은 컨트롤러|`onAutoplayBlocked`, `onLoadingDelayed`, `play`, `pause`, `previous`, `next`, `retry`: 실제 자동 재생 제한과 단순 로딩 지연을 구분하고 곡 실패로 기록하지 않음. 사용자가 한 번 재생할 수 있으며 강제 음소거/보이지 않는 재생/무한 새로고침을 사용하지 않음|
|같은 컨트롤러|`setBlocked`, `invalidate`, `destroy`: 조건·제외 변경/저장 중/안내 표시의 gate가 들어오면 즉시 정지하고 진행 중 HTTP 요청을 취소. 오래된 응답은 무시. 해제만으로 자동 재개하지 않고 재생 버튼으로 이어감|
|`frontend/src/features/recommendation/youtubeIframeApi.ts`|`loadYoutubeIframeApi`: 공식 스크립트 한 번 로딩, 이미 존재하는 API/스크립트 재사용, 기존 전역 준비 콜백 보존. 20초 실패 후 소유 스크립트 제거 및 재연결 허용. `scopedYoutubeIframeEvents`는 폐기/교체된 iframe 이벤트를 무시하고 `watchYoutubeIframeReady`는 API 스크립트 이후에도 실제 iframe 준비 20초 제한을 별도로 적용|
|`frontend/src/features/recommendation/youtubePlayer.test.ts`|큐 자동 시작/실제 종료/중복 종료 무시/자동 재생 차단/150 대안/153 보류/서버 검색 불가/전곡 실패/조건 gate 취소·정지/잘못된 응답/해제·언마운트의 회귀 검사|
|`frontend/src/features/recommendation/youtubeIframeApi.test.ts`|동시 컴포넌트 단일 스크립트/기존 준비 콜백/기존 공식 스크립트 재사용/타임아웃 이후 실제 재연결/폐기된 iframe 이벤트/iframe 미준비 제한 및 취소 검사|

`PublicPage.tsx`의 중앙 영역 교체와 부모 gate 공급은 통합 담당이 변경합니다. 프런트엔드의 승인/피드백·추천 API·공유 타입을 이 작업자가 동시에 수정하지 않았습니다.

## 호출과 응답·오류·저장 순서

1. 기존 추천이 성공하면 PublicPage가 불변 `playlist_id`와 원래 순서의 `items`를 플레이어에 전달합니다. 재생을 위해 [승인]을 새 필수 단계로 추가하지 않습니다.
2. iframe은 `enablejsapi=1`, 현재 페이지 `origin`, `playsinline=1`, `allow="autoplay; encrypted-media; fullscreen; picture-in-picture"`, `referrerPolicy="strict-origin-when-cross-origin"`로 생성합니다. 플레이어가 준비되면 현재 곡부터 조회합니다.
3. 기존 공통 `api()`로 `POST /api/playlists/{playlist_id}/youtube-playback`을 호출합니다. 요청은 `{track_id, excluded_video_ids}`이며 동일 출처 쿠키·CSRF 처리와 소유 검사는 기존 API 계약을 사용합니다. 임의 외부 URL/영상 ID를 클라이언트에서 조회 endpoint에 전달하지 않습니다.
4. 응답은 `{track_id, status, candidates, message?}`입니다. `status`는 READY/SEARCH_UNAVAILABLE/NO_MATCH, 후보는 `video_id/title/channel_title/duration_seconds/source`이며 `match_status`는 선택 VERIFIED/CANDIDATE입니다. source는 CATALOG_MAPPING/YOUTUBE_API입니다. 곡 ID가 다르거나 ID가 11자리 허용 문자에 맞지 않으면 재생하지 않습니다. 중복 후보와 실패한 ID도 제거합니다.
5. READY 후보를 `loadVideoById`에 전달하면 자동 재생을 시도합니다. PLAYING 관측 뒤 ENDED가 와야 자동 다음 곡으로 진행합니다. 플레이어 광고/버퍼링 시간을 원본 곡 길이로 추정해 강제 다음으로 넘기지 않습니다.
6. 첫 조회의 SEARCH_UNAVAILABLE은 현재 곡을 보류하고 연결 재확인을 제공합니다. 키/검색 장애를 전곡 실패로 반복 처리하지 않습니다. 이미 실제 100/101/150 차단이 관측된 곡의 대안 조회도 불가능하면 그 곡의 차단·대안 조회 불가를 기록한 뒤 다음 곡으로 이동합니다. 다음 미매핑 곡도 검색 연결이 없으면 다시 보류합니다.
7. NO_MATCH 또는 한 곡의 재생 후보 소진은 누락 사유를 표시하고 다음 곡으로 이동합니다. 모든 곡이 실패하면 재생 가능한 영상을 찾지 못했다고 안내하며 전체 성공/완주로 표현하지 않습니다. 오류 153(Referer/클라이언트 식별)·5 등 환경 오류는 현재 곡에서 보류합니다.
8. 실제 자동 재생 차단 이벤트에는 브라우저 재생 보류를 안내합니다. loading 상태가 15초 지속되면서 현재 시간이 0초인 경우는 광고/버퍼링일 수도 있으므로 일반적인 재생 준비 지연만 안내하고 차단으로 단정하지 않습니다. 두 경우 모두 자동 다음으로 넘기지 않습니다. 한 곡의 완료를 정해진 타이머만으로 판단하지 않습니다.
9. API 스크립트가 준비되더라도 iframe이 20초 안에 onReady를 보내지 않으면 준비 오류와 연결 재확인 버튼을 표시합니다. 준비 이전의 153/5 등 오류도 즉시 환경 오류로 안내합니다. dispose 여부와 현재 iframe 인스턴스 일치 검사를 모든 이벤트에 적용해 이전 결과의 늦은 ENDED/오류가 새 큐에 영향을 주지 않습니다.

프런트엔드가 새 DB/큐/작업·피드백 이벤트를 생성하지 않습니다. 백엔드 resolver의 검색·캐시/권한·설정·미매핑 후보 검증 범위는 해당 담당의 라우팅에서 확인합니다. Gemini/LLM API 호출은 플레이어에 없습니다. 공식 YouTube Data API 설정이 없는 상황에서 전체 새 곡 자동 매핑이 완료됐다고 표시하지 않습니다.

## 검증·실행·인계

- `cd frontend; pnpm test`: 중간 31건 PASS. 최종 프런트엔드 테스트는 통합 담당이 실행하며, 이 프런트 작업에는 기존 15건 외 컨트롤러/컴포넌트 12건과 로더/수명주기 5건을 추가했습니다.
- `cd frontend; pnpm build`: TypeScript와 Vite 빌드 PASS. 뒤에 백엔드/UI 통합 수정이 추가되면 통합 담당이 최종 검사 결과를 갱신합니다.
- 이 테스트는 모의 IFrame API 상태/HTML 출력·스크립트 로더를 검사합니다. 실제 YouTube 광고/국내 제공·삽입 허용·소리·Premium·약 3시간 완주 증거가 아닙니다.
- 통합 담당 인계: `PublicPage.tsx` 중앙 연결·안내/조건/제외 gate·소유 결과 resolver와 실제 브라우저 재생/자연 전환. 검증된 실제 화면/이벤트 관측은 별도 수용 기록에 남깁니다.
- C·B 인계: 자동 검색 키/쿼터/서비스 설정·결과별 후보 캐시·공유 인증·검색 후보의 실제 음원 일치 검수. INF 인계: Chrome 자동 재생·Referer/배포 CSP·운영 도메인 origin과 장시간 환경 검증.
- 커밋/푸시/PR/병합/배포·외부 계정 저장형 재생목록 생성은 수행하지 않았습니다.

공식 동작 근거: [YouTube IFrame API](https://developers.google.com/youtube/iframe_api_reference). `loadPlaylist`의 검색 방식은 사용하지 않습니다. 실제 영상 ID를 서버가 제공한 후보에서 받아 삽입합니다.
