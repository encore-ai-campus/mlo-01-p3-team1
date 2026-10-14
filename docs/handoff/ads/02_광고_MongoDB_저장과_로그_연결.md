# 광고 MongoDB 저장과 PostgreSQL 로그 연결

- 작성일: 2026-10-14
- 수정일: 2026-10-14
- 상태: 사용자 확정 MongoDB 저장을 연결한 논리 설계입니다. 컬렉션/인덱스/드라이버·replica set의 실제 생성과 검증은 별도입니다.
- 기준: [광고 정책](../../product/3차_광고_운영_회의_결정사항_목록.md), [저장 경계](../../product/3차_저장소_경계와_발행_계약.md), [화면/API](./01_광고_화면_API와_측정_계약.md).

## 2026-10-14 광고 관리 간소화 적용

사용자가 제공한 [간소화 원문](./04_광고_관리_간소화_인수인계서.md)과 [통합·추가 인계](./05_광고_간소화_통합과_추가_인계.md)를 현행 광고 기준으로 적용합니다. 첫 관리 단계는 ads/ad_assets/ad_admin_changes 세 컬렉션·MongoDB 이미지 Binary·관리 감사/멱등 응답 통합입니다. 3차는 카페 전용이며 관리자/사용자 업종 선택·태그 입력·업종별 매칭은 제공하지 않습니다. 해당 확장은4차로 분리합니다. 공개 제공/측정과 토큰/주기 통계/예산은 다음 구현 단계이며 전체3차 필수 범위와 기존 태스크 ID/직접 선행은 유지합니다. 이하 기존 확장 저장 표는 후속 검토 자료이며 지금 일괄 생성하지 않습니다.

3차는 카페 광고만 운영하고 위치·일정·paused·소재·예산 자격을 충족한 후보에서 높은 priority·위치별 동률 순환을 적용합니다. 업종/태그가 제공·측정의 전제가 아니며 최초 guest 발급·추천 미요청 집계·단가8/5/클릭추가15·중복/지연/보관은 유지합니다. 미연결 지표는 연동 대기, 실제 통계는 주기 집계하며 예산 제공 제어와 구분합니다. 첫 관리 로그는 ad_admin_changes 내부 log_relay로 전달합니다. 업종별 입력/태그/매칭/순환은4차 인계에서 정하고3차 API/DB/화면/검증의 선행 조건으로 넣지 않습니다.

## 1. 업무 원본과 로그의 경계

광고 자료·delivery·최초 측정 판정·반복 제한·집계·예상 원장은 MongoDB의 광고 전용 논리 DB에 저장합니다. 광고 관리 변경 이력도 광고의 당시 상태를 재현하는 업무 원본입니다. PostgreSQL에는 HTTP/오류/처리 진단과 광고 업무 로그의 사본을 저장합니다. 로그를 별도 보관한다는 이유로 MongoDB 업무 판정과 PostgreSQL 로그를 동시에 쓰고 하나의 DB 트랜잭션이라고 설명하지 않습니다.

계정/관리 세션/guest는 공통 PostgreSQL에서 검증하고 MongoDB에는 내부 참조 ID만 남깁니다. DB 간 FK를 가정하지 않으며 보관 중인 당시 참조를 세션 만료와 함께 연쇄 삭제하지 않습니다. 인증 DB 확인 실패 시 관리자 변경은 차단합니다. 공개 무문맥 측정은 집계하지 않되 광고 표시/링크 이동과 기본 추천의 오류 경로를 분리합니다.

MongoDB의 광고 DB와 날씨 DB는 같은 인스턴스를 쓰더라도 별도 이름·권한·백업/정리 범위를 둡니다. 공유 호스트는 완전한 장애 격리가 아니므로 광고/날씨 connection pool·timeout·자원 경합을 INF가 검증합니다. 광고 이미지 원본은 ad_assets.image_bytes의 Binary로 저장하고 MIME/크기/해시·BSON 전체 크기를 검사합니다. 실제 조회URL/캐시/정리/백업은 별도 인계입니다.

## 2. 후속 확장 컬렉션 참고 — 첫 단계 생성 대상 아님

현재 첫 관리 구조는 다음 세 컬렉션입니다. 아래 기존 확장 표는 이름/물리 구조를 확정한 목록이 아니라 다음 단계 비교 참고입니다. 원문의 ads를 advertisements로 다시 나누거나 ad_versions/별도 멱등/outbox를 지금 생성하지 않습니다.

| 첫 단계 컬렉션 | 저장 내용 |
|---|---|
| ads | 카페 광고·위치·기간·paused·version·priority·검증된 외부 관리자 ID |
| ad_assets | 원본 image_bytes·실제 MIME/크기/해시·검증된 업로드 관리자 ID. 새 이미지로 교체 |
| ad_admin_changes | 불변 before/after·성공 응답/멱등 해시·changed/version·보관과 내부 log_relay. 이미지 바이트/인증 비밀 제외 |

원문의 최소 인덱스·관리 트랜잭션과 통합 인계4절의 로그 전달 보완을 적용합니다. 측정 원본/원장·순환/반복 창·집계 구조는 후속 검증으로 정합니다.

아래 이름은 B/INF가 같은 구현을 만들기 위한 개발 기준입니다. ID는 외부 API 문자열과 `_id`의 대응을 명시하고 BSON ObjectId를 공개 응답에 자동 노출하지 않습니다. 서버 시각은 UTC BSON Date, API는 UTC Z, 금액/카운트는 정수입니다.

| 컬렉션 | 필수 업무 자료 | 고유 키/주요 조회 |
|---|---|---|
| advertisements | ad_id·title·asset_id·link_url·placement·starts_at/ends_at·priority·paused·version·creative_version·created/updated/stopped_at·현재 정책 참조 | ad_id unique; placement/paused/priority·기간 조회 |
| ad_assets | asset_id·image_bytes Binary·sha256·실제형식·byte_size·정적 검사·업로드 상태/시각 | asset_id unique; 원본 파일명은 식별키가 아님. 실제 조회URL은 제공 경계에서 결정 |
| ad_versions | ad_id·version·creative_version·당시 title/asset/link/위치/기간/중단·정책·유효구간 | (ad_id,version) unique; 현재 편집값으로 과거 유효성 대체 금지 |
| ad_deliveries | delivery_id·서버 문맥 참조·ad/creative/version/placement·당시 자료·issued_at·event_expires_at·last_used_at·마지막 신규 수신·환경 구분 | delivery_id unique; ad/owner/발급시각 조회 |
| ad_delivery_event_claims | delivery_id·event_type·최초 event_id/result·처리시각 | (delivery_id,event_type) unique; COUNTED와 REPEAT_SUPPRESSED의 최초 소비 보존 |
| ad_events | event_id·정규 request_hash·delivery/광고/문맥 내부 참조·type·occurred/received/processed/accepted_at·result/counted·policy/version·적용단가·원응답·운영/테스트 | event_id unique; ad/placement/KST일·result 조회 |
| ad_repeat_windows | owner_guest_id·ad_id·placement·event_type·accepted_at·window_version | 위4개 복합 unique; 조건 갱신, 노출/클릭 별도 |
| ad_rotation_state | placement·last_ad_id·revision | placement unique; top/bottom 별도 원자 커서 |
| ad_daily_metrics | metric_date_kst·ad_id·placement·is_test·impressions/clicks·updated_at | (date,ad,placement,is_test) unique |
| ad_lifetime_metrics | ad_id·placement·is_test·impressions/clicks·updated_at | (ad,placement,is_test) unique; 90일 원본만 합쳐 누적값 축소 금지 |
| ad_estimated_usage_ledger | ledger_entry_id·event_id·광고/소재/위치·종류·KST일·발생/처리·정책·단가·예상 사용량·status·정정 원본 참조 | ledger_entry_id unique; 최초 계산은 event_id unique(부분 인덱스 등). 정정은 새 ID/원본 참조 |
| ad_management_history | change_id·ad_id·이전/다음version·변경 내용/중단 시각·관리자 내부ID·reason·request_id | change_id unique; ad_id/version/시각 조회 |
| ad_mutation_requests | actor_id·관리action/대상·idempotency_key·request_hash·원응답·시각 | (actor,action,target,key) unique; 등록의 target은 서버 등록 요청 범위 |
| ad_log_outbox | log_event_id·업무 event/change ID·당시 payload·시각·pending/sent·시도/다음 재시도 | log_event_id unique; pending/next_retry 조회 |

정책/스키마·환경 버전과 is_test는 서버에서 고정합니다. 테스트는 별도 namespace/DB를 우선 사용하며 조회/집계에서도 운영과 구분합니다. BSON schema validation과 타입/필수/enum 검사를 B가 구현하고 인덱스 적용 전 중복을 대조합니다. unique 인덱스만으로 모든 업무 조건이 검증됐다고 판단하지 않습니다.

## 3. 원자 저장과 동시성 — 측정/확장 단계 참고

여러 컬렉션에 걸친 업무 원자성을 위해 **replica set의 MongoDB 트랜잭션**을 개발 기준으로 사용합니다. standalone mongod는 이 구현의 완료 환경이 아닙니다. AWS 원문의 MongoDB EC2 한 대는 서버 수 설명이며 replica set 모드가 설정됐다는 증거가 아닙니다. 단일 멤버 개발 replica set도 HA를 보장하지 않습니다. 실제 멤버 수/가용성/버전은 INF 인계 사항입니다. [공식 트랜잭션 문서](https://www.mongodb.com/docs/manual/core/transactions/)를 근거로 설정을 검증합니다.

| 처리 | 같은 MongoDB 트랜잭션에 들어갈 쓰기 |
|---|---|
| 첫 관리 등록/수정/중단 | ads의 본문 version 조건 갱신 + ad_admin_changes의 감사/멱등 원응답·내부 log_relay. 별도 ad_versions/outbox 생성 없음 |
| 새 delivery | 위치별 커서 조건 갱신 + 현재 광고의 유효성/version 경합 검사 + delivery snapshot |
| 후속 최초 측정 판정 | event_id·delivery/type claim·반복 창 + 최초 판정/원응답 + 인정 시 예상 항목. 일별/누적 통계는 별도 주기 집계, 후속 로그 구조는 인계 검증 |
| 후속 정정 | 새 정정 ID/원본 연결·원장 근거 보존, 집계 범위 재계산/재실행 중복 방지. 최초 판정 덮어쓰기 없음 |

트랜잭션 밖에서 광고를 읽은 뒤 그 상태를 그대로 제공하지 않습니다. 제공과 중단이 경합하면 광고 version에 대한 조건 쓰기/충돌 검사를 포함해 커밋 순서를 확인합니다. 단순 snapshot 읽기만으로 t_stop 이후 새 제공 차단이 해결됐다고 설명하지 않습니다. 재확인은 primary의 현재 상태를 사용하고 과거 캐시로 표시 기한을 늘리지 않습니다.

반복 창은 같은 복합키의 조건 갱신과 unique 제약을 함께 사용합니다. 신규 창 동시 upsert/duplicate-key나 write-conflict는 해당 트랜잭션을 재조회/제한 재시도하고, 모든 탭이 조건을 통과하지 않도록 합니다. 반복 판정 accepted_at은 서버의 최초 인정 시각이며 응답 유실 재전송에 바뀌지 않습니다. 이벤트의 당시 발생 유효성과 서버 처리 순서의 반복 창은 별개입니다.

read concern snapshot·write concern majority·primary 기준을 환경에서 검증합니다. commit 결과가 불명확하면 동일 transaction commit 재시도/기존 event_id·멱등 키의 커밋 상태 조회로 해결하며 새 ID로 다시 계산하지 않습니다. DB 장애에 성공 응답을 보내지 않습니다. 외부 파일 전송·PostgreSQL 로그 발행·네트워크 호출은 MongoDB 트랜잭션 안에서 실행하지 않습니다.

## 4. PostgreSQL 로그 발행과 복구 — 후속 outbox 컬렉션 예시

```text
MongoDB 업무 변경 + 광고 로그 outbox 커밋
  → B의 광고 로그 relay가 미발행 자료 조회
  → PostgreSQL 로그에 UNIQUE(log_event_id)로 저장/동일 payload 확인
  → 성공 확인 후 MongoDB outbox를 SENT로 표시
```

PostgreSQL 쓰기 후 SENT 표시 전에 종료되면 같은 ID/payload를 다시 보내고 로그를 중복 만들지 않습니다. 같은 ID의 다른 payload는 충돌 경보이며 덮어쓰지 않습니다. PostgreSQL 지연 중에도 이미 커밋된 광고 업무 판정은 유지하고 outbox pending/최초 지연/시도·오류를 관측합니다. 관리자 API 인증 확인은 별도이며 이 로그 지연 허용으로 인증 장애를 우회하지 않습니다. relay 재처리는 지표/예상 비용을 다시 계산하지 않습니다.

로그 사본에는 log_event_id·source_domain=ADS·source_event_id/change_id·request_id·업무 버전·occurred/received/processed·result·is_test와 필요한 당시 참조를 둡니다. 원문 쿠키·개인키·비밀번호·MongoDB URI를 남기지 않습니다. PostgreSQL 로그 테이블/인덱스·보관은 B/INF 공통 로그 계약으로 맞추되 광고 업무 로그는 아래90/365일 분류에 연결합니다. 일반 HTTP/진단 로그 기간은 별도 미정입니다.

## 5. 보관·누적·재처리

| 자료 | 광고 정책 보관/기산점 |
|---|---|
| 원본 판정 이벤트 및 그 업무 로그 사본 |90일 / 최초 서버 received_at |
| delivery/최초 claim |90일 / 마지막 실제 사용 또는 신규 이벤트 수신 중 늦은 시각. 단순 재전송은 연장 없음 |
| 일별 집계 |365일 / 해당 KST일 다음 자정 |
| 예상 원장 |365일 / 최초 서버 processed_at |
| 관리 변경 이력 및 그 업무 로그 사본 |365일 / 변경 발생시각 |

누적 지표는 원본90일 만료 후에도 보관 중인365일 집계/원장의 근거를 유지합니다. 광고별 누적값의 전체 수명 보관은 별도 결정 전까지365일을 넘는 영구 보관을 임의 확정하지 않고 API에 실제 coverage_from/as_of를 표시합니다.90일 원본만으로365일 집계를 다시 만들 수 있다고 설명하지 않습니다. 최근 재처리는 격리된 출력에서 최초 판정/단가·accepted_at을 보존해 대조하고 반영합니다. 원본 만료 구간은 원본 상세 만료/재검증 불가를 표시하며 현재 광고로 복원하지 않습니다.

연결된 outbox pending·유효 delivery·재처리/정정에 필요한 snapshot은 먼저 삭제하지 않습니다. last_used·expires_at과 보호 참조를 확인하는 정리 작업을 설계하며 MongoDB TTL을 넣었다는 이유로 정시에 삭제되거나 참조가 안전하다고 판단하지 않습니다. [공식 TTL 문서](https://www.mongodb.com/docs/manual/core/index-ttl/)처럼 삭제는 백그라운드로 수행되므로 만료 즉시 API 접근을 막는 검사는 별도로 구현합니다. 자동 TTL은 정리 대상 확정 후 참조 없는 자료에만 적용합니다. 미발행 outbox를 TTL로 먼저 제거하지 않습니다.

광고 이미지/백업·guest/추천/음악/날씨 로그의 보관은 광고90/365일을 자동 적용하지 않습니다. asset 공유 중 정리를 금지하고 원본 정책을 보존합니다. 실제 삭제 명령·DB 생성은 이번 문서 작업에 포함하지 않습니다.

## 6. 인계할 실제 산출물

B는 validator/필드/인덱스 manifest·버전 조건/멱등·트랜잭션 범위·relay/재처리·응답 모델과 고정 테스트를, INF는 replica set/primary·권한/접속·백업/복구 결과를 제공합니다. C는 같은 fixture의 delivery/기한/result를 사용해 브라우저를 검증합니다. [unique 인덱스 공식 문서](https://www.mongodb.com/docs/manual/core/index-unique/)를 참고하고 제약 존재와 실제 동시성 통과를 구분합니다.
