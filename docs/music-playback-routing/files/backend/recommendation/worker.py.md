# backend/recommendation/worker.py 라우팅

- 작성일/수정일: 2026-10-16
- 담당: C 공개 대시보드·추천/음악 통합
- 범위: 일반 추천 후보와 고정 재생 시험 카탈로그 분리·오류 진단 후속
- 기준 브랜치/커밋: feature/ad-logic / f22f974
- 소스: [backend/recommendation/worker.py](../../../../../backend/recommendation/worker.py)

## 기준과 공급·소비

저장된 Job과 고정 catalog/input을 읽고 임대 토큰·세대로 작업을 점유합니다. `verified_catalog`는 카탈로그 SHA와 고유 track_id를 확인한 불변 배열을 프로세스 안에 재사용합니다. `run_one`은 공통 적격 → 모드별 점수 → 규칙/로컬 프리뷰/Gemini 선택 → 시간·날씨 재검증 → 당시 snapshot/Playlist와 Job 상태 저장으로 연결합니다. 실제 외부 모델 호출은 기존 명시 재설정 경로에서만 발생합니다.

`warm_current_catalog`는 `service.current_catalog`와 같은 용도별 선택 기준을 사용합니다. 로컬 고정 재생 목록이 최신이어도 일반 추천용 카탈로그를 사전 로딩하며, 일반 카탈로그가 없을 때는 고정 목록을 대신 로딩하지 않습니다. 이미 점유한 Job은 그 Job의 고정 catalog_id를 계속 사용합니다.

## 이번 변경과 오류 전달

후보 진단에 catalog_count/common_eligible_count/common_rejected_count/common_eligible_total_ms/weather_rejected_count/off_missing_preference_count/candidate_count/candidate_total_ms를 보존합니다. CANDIDATE_SHORTAGE·SEARCH_INCOMPLETE·NO_MEANINGFUL_CHANGE 오류에 동일 진단을 합쳐 Job.error에 저장하고 폴링 응답으로 전달합니다. 상세 식별 사유는 solver의 reason을 유지합니다.

실패 시 active_job 조건을 만족하는 현재 임대만 갱신하며 기존 부모 결과·평가·승인 snapshot을 대체하지 않습니다. 공유 인증·운영 PostgreSQL·실제 날씨/모델 연결이나 전체 청취 완료를 이 변경으로 확정하지 않습니다.

## 검증

카탈로그 사전 로딩 선택은 신규 API 회귀에서 검증했습니다. 실제 전체 카탈로그 요청·오류 details·기존 결과 보존 및 전체 테스트 결과는 수용 기록을 따릅니다. AST 문서는 실제 함수 구조와 연결 경계를 기록하며, 서버 재시작·통합 성공 자체의 근거는 별도 수용 기록입니다.

[정책·화면·저장 연결 라우팅](../../../../development/기존_대시보드_YouTube_연결_라우팅.md)과 [일반 추천/재생 시험 분리 수용 기록](../../../../acceptance/일반_추천_후보와_재생시험_분리_검증_20261016.md)을 함께 확인합니다. 수령 원문과 기존 backend-routing 문서는 수정하지 않습니다.

## AST 시그니처

검사 JSON의 python_files[].symbols를 정본으로 기록합니다.

```python
verified_catalog(catalog)
warm_current_catalog()
claim()
heartbeat(job, stopped)
active_job(job)
run_one()
```
