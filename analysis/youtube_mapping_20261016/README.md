# 기존 대시보드 47곡 YouTube 매핑 자료

- 작성일/수정일: 2026-10-16
- 범위: 사용자가 요청한 기존 47곡의 로컬 재생 시험. 한국에서 제공되지 않는 원곡 1개는 사용자 승인으로 같은 날씨·장르의 곡으로 교체했습니다.
- 최신 실행·검증·기동 경로는 [수용 기록](../../docs/acceptance/YouTube_47곡_매핑_검증_20261016.md)과 [구현 가이드](../../docs/development/music/YouTube_로컬_재생_기획과_구현_가이드.md)를 따릅니다.

후속 수정으로 고정47곡 카탈로그는 일반 추천 기본값에서 제외했습니다. 일반 추천은 전체GENERAL과 이 매핑을 결합한 새 카탈로그를 사용하며 결과에 실제 포함된 매핑 수만 표시합니다. 이 폴더의47곡 재생 기록을 모든 사용자 조건의 전곡 영상 확보로 해석하지 않습니다. [일반 추천 복구 검증](../../docs/acceptance/일반_추천_후보와_재생시험_분리_검증_20261016.md)을 함께 확인합니다.

## 현재 적용 자료

|파일|역할|
|---|---|
|[mapping-47-verified-v1.json](./mapping-47-verified-v1.json)|공식 메타데이터·한국 제공·최종 네이티브 목록의 ID/순서를 대조한47곡 매핑 스냅샷|
|[playback-selection-v1.json](./playback-selection-v1.json)|원본 CSV 해시와 시험용47개 track_id의 명시 선택|
|[final-candidates.json](./final-candidates.json)|최종 곡과 영상의 조사·원본 스냅샷. 순서는 실제 결과/매핑과 동일|
|[native-final-47-observed.json](./native-final-47-observed.json)|YouTube에서 실제 받아들인47개 영상ID·순서|
|[independent-verification.json](./independent-verification.json)|다른 에이전트의 저장 자료 대조35항목 통과|
|[natural-transition-observed.json](./natural-transition-observed.json)|최종 목록에서 첫 곡 종료 후 두 번째 곡으로 자동 전환된 실제 관측|
|[dashboard-exclusion-gate-observed.json](./dashboard-exclusion-gate-observed.json)|기존 대시보드 제외 초안의 전체 링크 보류·취소 후 복원 관측|

원본 CSV SHA-256은 `b202fa49909b2d5cef71a04b1d21243cfeb36414535f2ca9272aa646721177bd`입니다. 승인 교체곡은 All on Me / Devin Dawson (`0WIeJxgsLtiUGqoSxB9Bht`, 영상 `3_K5hKcw1nw`)이며 나머지46곡의 원본 스냅샷을 보존했습니다. 교체곡은 기존 ON 동점 정렬에 따라 최종47번째에 표시됩니다.

새47곡의 원본 합계는10,632,974ms(177분12.974초), 영상 메타데이터의 정수초 합계는10,648초(177분28초)입니다. 광고·버퍼링을 포함한 실제 경과시간과 다릅니다. `VERIFIED`는 위 매핑 대조 범위이며 파형 동일성·모든 곡의 청취·약177분 전체 재생·Chrome/Premium·스피커 출력 검증을 뜻하지 않습니다. 미검수 CSV 시험의 `preview_only=true`·`validation_passed=false`를 유지합니다.

## 조사 이력 보존

`part*.json`·`track40-research.json`·`ordered-candidates.json`은 최초 조사이며 현재 적용 매핑과 다를 수 있습니다. 최초 `http-metadata.json`은43개 `OK`/4개 `UNPLAYABLE`, `native-initial-47-observed.json`은43개만 포함된 목록을 기록합니다. 동일 곡의 공식 대안3개는 `http-alternatives.json`·`native-alternatives-observed.json`으로 확인했습니다. `replacement-candidate.json`의 승인 대기 표기는 당시 조사 상태이고, 후속 사용자 승인·실제 적용은 최종 매핑과 수용 기록에 보존합니다.

기존 전체 GENERAL 카탈로그와 별도인47곡 test Catalog만 새로 적재했습니다. 원본 CSV·기존 카탈로그·이전 추천 결과를 덮어쓰지 않았으며 운영 DB·외부 계정의 재생목록을 변경하지 않았습니다.
