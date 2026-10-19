# 광고 MongoDB 저장과 MongoDB 광고 로그 저장

- 작성일: 2026-10-14
- 수정일: 2026-10-16
- 상태: 관리·공개·5분 예산/통계의 구현 저장 계약입니다. 격리 개발 DB 검증과 실제 공유/운영 인프라 검증을 구분합니다.
- 기준: [광고 정책](../../product/3차_광고_운영_회의_결정사항_목록.md), [저장 경계](../../product/3차_저장소_경계와_발행_계약.md), [화면/API](./01_광고_화면_API와_측정_계약.md).

## 2026-10-15 광고 로그 MongoDB 독립 관리

최신 사용자 결정으로 광고 관리·측정·소진 로그는 광고 MongoDB에 저장합니다. PostgreSQL 전달과 공통 로그 테이블 규격은 사용하지 않습니다. 새 `log_record`와 기존 기록 보존·점검/스키마 적용은 [광고 로그 저장 계약](../../development/ads/MongoDB_광고_로그_저장_계약.md)을 따릅니다. 관리3+공개5+정책2 구조와 공유 ADMIN/guest 인증 경계는 유지합니다.

## 2026-10-14 광고 관리 간소화 적용

사용자가 제공한 [간소화 원문](./04_광고_관리_간소화_인수인계서.md)과 [통합·추가 인계](./05_광고_간소화_통합과_추가_인계.md)를 현행 광고 기준으로 적용합니다. 첫 관리 단계는 ads/ad_assets/ad_admin_changes 세 컬렉션·MongoDB 이미지 Binary·관리 감사/멱등 응답 통합입니다. 3차는 카페 전용이며 관리자/사용자 업종 선택·태그 입력·업종별 매칭은 제공하지 않습니다. 해당 확장은4차로 분리합니다. 공개 제공/측정과 5분 예산/통계를 관리 3개·공개 5개·정책 2개로 연결했습니다. 전체3차 필수 범위와 기존 태스크 ID/직접 선행은 유지하고, 별도 claim/outbox/ad_versions 컬렉션은 만들지 않습니다.

3차는 카페 광고만 운영하고 위치·일정·paused·소재·예산 자격을 충족한 후보에서 높은 priority·위치별 동률 순환을 적용합니다. 업종/태그가 제공·측정의 전제가 아니며 최초 guest 발급·추천 미요청 집계·단가8/5/클릭추가15·중복/지연/보관은 유지합니다. 미연결 지표는 연동 대기, 실제 통계는 주기 집계하며 예산 제공 제어와 구분합니다. 첫 관리 로그는 ad_admin_changes 내부 log_record에 MongoDB로 원자 저장합니다. 업종별 입력/태그/매칭/순환은4차 인계에서 정하고3차 API/DB/화면/검증의 선행 조건으로 넣지 않습니다.

## 1. 업무 원본과 로그의 경계

광고 자료·delivery·최초 측정 판정·반복 제한·집계·예상 원장은 MongoDB의 광고 전용 논리 DB에 저장합니다. 광고 관리 변경 이력과 업무 로그도 광고의 당시 상태를 재현하는 MongoDB 원본입니다. 광고 로그를 PostgreSQL이나 공통 로그 테이블에 복제하지 않습니다. HTTP/일반 서버 진단의 추가 수집·보관은 별도이며 이번에 새 수집기를 만들지 않습니다.

계정/관리 세션/guest는 공통 PostgreSQL에서 검증하고 MongoDB에는 내부 참조 ID만 남깁니다. DB 간 FK를 가정하지 않으며 보관 중인 당시 참조를 세션 만료와 함께 연쇄 삭제하지 않습니다. 인증 DB 확인 실패 시 관리자 변경은 차단합니다. 공개 무문맥 측정은 집계하지 않되 광고 표시/링크 이동과 기본 추천의 오류 경로를 분리합니다.

MongoDB의 광고 DB와 날씨 DB는 같은 인스턴스를 쓰더라도 별도 이름·권한·백업/정리 범위를 둡니다. 공유 호스트는 완전한 장애 격리가 아니므로 광고/날씨 connection pool·timeout·자원 경합을 INF가 검증합니다. 광고 이미지 원본은 ad_assets.image_bytes의 Binary로 저장하고 MIME/크기/해시·BSON 전체 크기를 검사합니다. 실제 조회URL/캐시/정리/백업은 별도 인계입니다.

## 2. 현재 10개 컬렉션과 스키마

ID는 불투명 문자열, 시각은 UTC BSON Date/API UTC Z, 사용량은 strict 정수입니다. is_test와 스키마 버전은 서버가 고정하고 운영/시험을 읽기·집계에서도 분리합니다. `_id` 고유키 외 고유/부분 인덱스와 strict validator는 각 manifest를 기준으로 적용합니다.

| 단계·컬렉션 | 저장 자료·주요 제약 |
|---|---|
| 관리 `ads` | 광고/소재/일정/paused/priority·관리 version·creative_version·예산 두 값/budget_version. 선택 예산 기술 차단 4필드 |
| 관리 `ad_assets` | 원본 image_bytes Binary·MIME/크기/해시·업로드 관리자 참조. 이미지 교체는 새 asset |
| 관리 `ad_admin_changes` | 불변 before/after·관리자 참조·멱등 hash/원응답·내장 log_record. 과거 광고 상태 근거 |
| 공개 `ad_rotation_state` | 위치/환경 고유 커서·revision CAS |
| 공개 `ad_deliveries` | 불변 당시 광고·발급·표시/보고 마감·proof hash·원응답·내장 claims. 선택 요청 hash에 부분 고유키 |
| 공개 `ad_events` | event_id 고유 최초 요청/판정/원응답·발생/수신/처리/인정 시각·KST일·내장 log_record |
| 공개 `ad_repeat_windows` | owner/ad/placement/type/환경 고유·accepted_at·revision CAS |
| 공개 `ad_estimated_usage_ledger` | 인정 event_id 고유 예상량·당시 정책/단가·발생일·ESTIMATED. 최초 항목 불변 |
| 정책 `ad_budget_states` | ad/budget_version별 일일·전체 검증 근거·최초 cutoff 이력·검증 시각·최초 소진 내장 log_record |
| 정책 `ad_daily_metrics` | ad/placement/KST일/환경별 원장 재계산 교체·노출/클릭/예상량·as_of·보존 범위 |

별도 사용자·ad_versions·claim·관리 멱등·outbox·lifetime 컬렉션은 없습니다. 관리 manifest는 `phase3-ads-data-20261015.4`, 공개는 `phase3-ads-public-20261015.2`, 정책은 `phase3-ads-policy-20261015.2`입니다. 단가/제공 정책 버전은 스키마 버전과 구분합니다.

관리 API 예산 쌍은 양의 int64이며 함께 입력하고 null은 거부합니다. 미입력 광고는 저장 가능하지만 운영 제공 부적격입니다. 예산 두 값이 실제 바뀔 때만 새 budget_version UUID를 발급하며 다른 편집은 유지합니다. 이전 cutoff를 덮지 않고 새 버전은 새 검증 후 제공합니다. ads의 budget_blocked_at/until/version/scope는 배치 기술 상태이며 관리 version·actor를 바꾸지 않습니다.

## 3. 원자 저장과 동시성

여러 컬렉션에 걸친 업무 원자성을 위해 **replica set의 MongoDB 트랜잭션**을 개발 기준으로 사용합니다. standalone mongod는 이 구현의 완료 환경이 아닙니다. AWS 원문의 MongoDB EC2 한 대는 서버 수 설명이며 replica set 모드가 설정됐다는 증거가 아닙니다. 단일 멤버 개발 replica set도 HA를 보장하지 않습니다. 실제 멤버 수/가용성/버전은 INF 인계 사항입니다. [공식 트랜잭션 문서](https://www.mongodb.com/docs/manual/core/transactions/)를 근거로 설정을 검증합니다.

| 처리 | 같은 MongoDB 트랜잭션에 들어갈 쓰기 |
|---|---|
| 첫 관리 등록/수정/중단 | ads의 본문 version 조건 갱신 + ad_admin_changes의 감사/멱등 원응답·내부 log_record. 별도 ad_versions/outbox 생성 없음 |
| 새 delivery | 위치별 커서 조건 갱신 + 현재 광고의 유효성/version 경합 검사 + delivery snapshot |
| 최초 측정 판정 | 내장 delivery/type claim·반복 창·event 최초 판정/원응답·인정 원장·내장 광고 로그 |
| 5분 정책 배치 | 원장 합계 검증·budget_version별 최초 소진 cutoff/내장 로그·ads 기술 차단 상태·일별 재계산 교체. 겹친 배치/제공/관리 경합은 트랜잭션 재검사 |
| 후속 정정 | 새 정정 ID/원본 연결·원장 근거 보존, 집계 범위 재계산/재실행 중복 방지. 최초 판정 덮어쓰기 없음 |

트랜잭션 밖에서 광고를 읽은 뒤 그 상태를 그대로 제공하지 않습니다. 제공과 중단이 경합하면 광고 version에 대한 조건 쓰기/충돌 검사를 포함해 커밋 순서를 확인합니다. 단순 snapshot 읽기만으로 t_stop 이후 새 제공 차단이 해결됐다고 설명하지 않습니다. 재확인은 primary의 현재 상태를 사용하고 과거 캐시로 표시 기한을 늘리지 않습니다.

반복 창은 같은 복합키의 조건 갱신과 unique 제약을 함께 사용합니다. 신규 창 동시 upsert/duplicate-key나 write-conflict는 해당 트랜잭션을 재조회/제한 재시도하고, 모든 탭이 조건을 통과하지 않도록 합니다. 반복 판정 accepted_at은 서버의 최초 인정 시각이며 응답 유실 재전송에 바뀌지 않습니다. 이벤트의 당시 발생 유효성과 서버 처리 순서의 반복 창은 별개입니다.

read concern snapshot·write concern majority·primary 기준을 환경에서 검증합니다. commit 결과가 불명확하면 동일 transaction commit 재시도/기존 event_id·멱등 키의 커밋 상태 조회로 해결하며 새 ID로 다시 계산하지 않습니다. DB 장애에 성공 응답을 보내지 않습니다. 외부 파일 전송·PostgreSQL 로그 발행·네트워크 호출은 MongoDB 트랜잭션 안에서 실행하지 않습니다.

## 4. MongoDB 광고 전용 로그와 기존 기록 보존

관리·측정·최초 소진 로그는 각각 ad_admin_changes/ad_events/ad_budget_states의 `log_record`에 업무 데이터와 같은 MongoDB 트랜잭션으로 저장합니다. 광고 전용 log_schema_version·log_event_id·payload·payload_hash·stored_at을 사용하며 공통 PostgreSQL 로그 테이블/이벤트 envelope에 맞추지 않습니다. 원본 이미지·인증 토큰·접속 비밀값을 포함하지 않습니다.

별도 로그 전송/ACK는 없습니다. `ADS_LOG_SINK`와 relay 명령3개는 제거했습니다. 과거 `log_relay` payload/상태는 보존하며 재전달하거나 SENT로 꾸미지 않습니다. 새 validator는 이전 기록도 허용하고 스키마 적용은 쓰기 전에 수행합니다. 기존 소진 로그는 후속 검증에서도 그대로 유지합니다.

`check_ads_logs --limit 20`은 신규/기존 건수·필수 로그 누락과 제한된 표본의 hash를 읽기만 합니다. 광고 통계/원장·멱등 응답은 변경하지 않습니다. 상세 필드·호환/manifest·정리 경계는 [광고 로그 저장 계약](../../development/ads/MongoDB_광고_로그_저장_계약.md)을 따릅니다.

### 4.1. 5분 정책과 표시/보고 경계

`refresh_ads_policy`는 기본 1회, `--watch`는 300초 시작 간격입니다. 불변 원장 합계가 일일/전체 예산 이상이면 최초 cutoff를 고정합니다. 이후 새 발급·재확인·이미지를 막고 3초 표시 lease를 적용합니다. occurred_at < cutoff인 당시 유효 보고는 300초 이내 초과 인정하며 경계 이상은 제외합니다. 최소 잔여23/20·예약은 없습니다. 자동 종료는 예산/게시 기간 두 가지이고 수동 paused는 별도로 유지합니다.

`domains.ads.runtime_policy.get_public_policy`는 1800초·split_deadlines=True·check_budget_history=True·cap_at_midnight=False를 사용합니다. 일일 KST는 기존 발생일 정렬에 맞춘 개발 기준입니다. 상태 누락은 부적격, 300초 초과 stale/future/형식 오류는 503 기술 장애이며 캠페인 종료 조건을 늘리지 않습니다. 기존 marker 없는 배달에 새 예산 정책을 소급하지 않습니다.

통계는 원장 범위를 재계산해 교체하여 재실행 중복을 막고 지연 수신 날짜도 보완합니다. summary는 오늘, 목록 행 measurement는 보존 범위 누적입니다. as_of·aggregation_status·coverage 및 coverage_from/coverage_through·is_stale로 실제 근거 범위를 표시하며, 누락 상태를 실제0으로 보이지 않습니다. 365일 범위를 영구 누적으로 부풀리지 않습니다.

정책 스키마 명령 `apply_ads_policy_schema`는 기본 dry-run이며 `--apply`는 loopback `_dev` DB와 primary 검사로 제한합니다. 실제 운영 watch·공유 인증·AWS 기동은 별도 검증입니다.

## 5. 보관·누적·재처리

| 자료 | 광고 정책 보관/기산점 |
|---|---|
| 원본 판정 이벤트 및 그 업무 로그 사본 |90일 / 최초 서버 received_at |
| delivery/최초 claim |90일 / 마지막 실제 사용 또는 신규 이벤트 수신 중 늦은 시각. 단순 재전송은 연장 없음 |
| 일별 집계 |365일 / 해당 KST일 다음 자정 |
| 예상 원장 |365일 / 최초 서버 processed_at |
| 관리 변경 이력 및 그 업무 로그 사본 |365일 / 변경 발생시각 |

누적 지표는 원본90일 만료 후에도 보관 중인365일 집계/원장의 근거를 유지합니다. 광고별 누적값의 전체 수명 보관은 별도 결정 전까지365일을 넘는 영구 보관을 임의 확정하지 않고 API에 실제 coverage_from/as_of를 표시합니다.90일 원본만으로365일 집계를 다시 만들 수 있다고 설명하지 않습니다. 최근 재처리는 격리된 출력에서 최초 판정/단가·accepted_at을 보존해 대조하고 반영합니다. 원본 만료 구간은 원본 상세 만료/재검증 불가를 표시하며 현재 광고로 복원하지 않습니다.

보관 중인 광고 로그·유효 delivery·재처리/정정에 필요한 snapshot은 먼저 삭제하지 않습니다. last_used·expires_at과 보호 참조를 확인하는 정리 작업을 설계하며 MongoDB TTL을 넣었다는 이유로 정시에 삭제되거나 참조가 안전하다고 판단하지 않습니다. [공식 TTL 문서](https://www.mongodb.com/docs/manual/core/index-ttl/)처럼 삭제는 백그라운드로 수행되므로 만료 즉시 API 접근을 막는 검사는 별도로 구현합니다. 자동 TTL은 정리 대상 확정 후 참조 없는 자료에만 적용합니다. 이전 log_relay도 보관/참조 기준을 확인하기 전에 삭제하지 않습니다.

광고 이미지/백업·guest/추천/음악/날씨 로그의 보관은 광고90/365일을 자동 적용하지 않습니다. asset 공유 중 정리를 금지하고 원본 정책을 보존합니다. 실제 삭제 명령·DB 생성은 이번 문서 작업에 포함하지 않습니다.

## 6. 인계할 실제 산출물

2026-10-16 `check_ads_retention --limit 100`을 추가했습니다. 위 확정 기산점·기간 도래·현재 참조를
제한 표본으로 읽기 점검하며 삭제 가능 판정·보관 연장·TTL/데이터 변경을 하지 않습니다.
무변경 관리 기록과 이미지·예산 소진 이력·서비스 상태의 미정 정리는 제외하며
필드/한계와 실제 결과는 [보관 점검·배치 종료](../../runbook/광고_보관_점검과_배치_종료.md)를 따릅니다.

B는 validator/필드/인덱스 manifest·버전 조건/멱등·트랜잭션 범위·relay/재처리·응답 모델과 고정 테스트를, INF는 replica set/primary·권한/접속·백업/복구 결과를 제공합니다. C는 같은 fixture의 delivery/기한/result를 사용해 브라우저를 검증합니다. [unique 인덱스 공식 문서](https://www.mongodb.com/docs/manual/core/index-unique/)를 참고하고 제약 존재와 실제 동시성 통과를 구분합니다.
