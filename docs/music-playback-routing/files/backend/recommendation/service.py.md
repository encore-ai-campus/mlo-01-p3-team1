# backend/recommendation/service.py 라우팅

- 작성일: 2026-10-16
- 수정일: 2026-10-18
- 담당: C 공개 대시보드·추천/음악 통합
- 범위: 일반 추천 후보와 고정 재생 시험 카탈로그 분리·오류 진단 후속
- 기준 브랜치/커밋: feature/ad-logic / f22f974
- 소스: [backend/recommendation/service.py](../../../../../backend/recommendation/service.py)

## 기준과 공급·소비

기본 추천·재설정·제외·승인 API가 소유자와 요청 키를 공급합니다. `basic` → `mutate`의 소유 잠금·멱등 확인 → `enqueue` → Family/Job 저장 순서로 연결하며, CSRF·익명 소유자 해석은 API 진입점 계약을 사용합니다. 국가·언어·임의 catalog 선택 입력은 추가하지 않습니다.

신규 일반 추천은 `catalog` → `current_catalog`를 사용합니다. `LOCAL_DEMO=True`에서는 ready 시험 카탈로그 중 `source_ref`가 `local-preview:youtube-playback-selection:`으로 시작하는 고정 재생 목록을 제외하고 최신 카탈로그를 선택합니다. 전체 GENERAL 카탈로그가 없으면 POLICY_NOT_READY/503으로 안내하며 고정 목록을 대체 사용하지 않습니다. 운영 모드는 기존 ready/is_test=False/최신순 선택을 유지합니다.

`enqueue`의 부모 결과가 있는 요청은 계속 `parent.job.catalog`를 고정합니다. 카탈로그·이미 생성된 선곡표·당시 snapshot을 삭제하거나 새 버전으로 바꾸지 않습니다. 신규 일반 추천과 작업자 사전 로딩만 같은 helper를 공유하며 순환 import는 발생하지 않습니다.

## 이번 변경과 검증

이전에는 최신 고정 47곡 재생 카탈로그가 일반 추천으로 선택되어 장르 선택 후 후보가 3곡으로 줄었습니다. 이번 변경은 카탈로그 선택 용도를 분리합니다. 전체 GENERAL에서 다시 구성한 새 목록은 전곡 YouTube VERIFIED를 보장하지 않으며, 영상 매핑 상태에 따른 화면 이동은 기존 계약을 따릅니다.

API 회귀 5건에서 최신 전체/고정 목록 구분·사전 로딩·고정 목록만 있을 때 503과 트랜잭션 롤백·운영 선택 범위·일반/과거 고정 부모 유지·과거 결과 조회를 확인했습니다. 실제 통합 결과와 미실행 항목은 아래 수용 기록을 따릅니다.

[정책·화면·저장 연결 라우팅](../../../../development/기존_대시보드_YouTube_연결_라우팅.md)과 [일반 추천/재생 시험 분리 수용 기록](../../../../acceptance/일반_추천_후보와_재생시험_분리_검증_20261016.md)을 함께 확인합니다. 수령 원문과 기존 backend-routing 문서는 수정하지 않습니다.

## AST 시그니처

검사 JSON의 python_files[].symbols를 정본으로 기록합니다.

```python
event(kind, family, request_id, payload)
owned(model, owner, pk, lock=False)
busy(family)
mutate(owner, scope, key, data, operation)
current_catalog()
catalog()
enqueue(family, request_id, parent=None, weather_refresh=False)
basic(owner, key, data, request_id)
exclusions(owner, family_id, key=None, data=None, request_id='')
regenerate(owner, playlist_id, key, data, request_id)
approve(owner, playlist_id, key, data, request_id)
```

## 2026-10-18 develop 동기화 보완

최신 develop의 지역 미설정 OFF·날씨 갱신 RULE_BASED·명시 재설정 GEMINI_RECONFIGURE·공통 outbox를 보존합니다. current_catalog의 고정 재생 목록 제외와 부모 카탈로그 고정도 유지합니다.

```python
enqueue(family, request_id, parent=None, weather_refresh=False)
refresh_weather(owner, playlist_id, key, data, request_id)
```

기준 develop `8bdad88`·기존 feature/ad-logic `0a0cc82`의 대조와 실제 재검증은 [통합 기록](../../../../development/feature_전체_동기화_변경_라우팅_20261018.md)을 따릅니다.
