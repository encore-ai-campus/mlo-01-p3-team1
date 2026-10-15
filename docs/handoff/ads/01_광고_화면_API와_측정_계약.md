# 광고 화면·API·측정 인계 계약

- 작성일: 2026-10-14
- 수정일: 2026-10-14
- 상태: 기존 제품/광고 정책의 구현 연결입니다. 아래 보완 필드명은 문서 개발 기준이며 실제 OpenAPI/서버 구현 완료가 아닙니다.
- 기준: [광고 정책](../../product/3차_광고_운영_회의_결정사항_목록.md), [설계도](../../product/카페_음악_서비스_구현_설계도.md) 7/9절, [공통 계약](../../product/3차_공통_개발_계약과_검증_기준.md).

## 2026-10-14 광고 관리 간소화 적용

사용자가 제공한 [간소화 원문](./04_광고_관리_간소화_인수인계서.md)과 [통합·추가 인계](./05_광고_간소화_통합과_추가_인계.md)를 현행 광고 기준으로 적용합니다. 첫 관리 단계는 ads/ad_assets/ad_admin_changes 세 컬렉션·MongoDB 이미지 Binary·관리 감사/멱등 응답 통합입니다. 3차는 카페 전용이며 관리자/사용자 업종 선택·태그 입력·업종별 매칭은 제공하지 않습니다. 해당 확장은4차로 분리합니다. 공개 제공/측정과 토큰/주기 통계/예산은 다음 구현 단계이며 전체3차 필수 범위와 기존 태스크 ID/직접 선행은 유지합니다. 이하 기존 확장 저장 표는 후속 검토 자료이며 지금 일괄 생성하지 않습니다.

3차는 카페 광고만 운영하고 위치·일정·paused·소재·예산 자격을 충족한 후보에서 높은 priority·위치별 동률 순환을 적용합니다. 업종/태그가 제공·측정의 전제가 아니며 최초 guest 발급·추천 미요청 집계·단가8/5/클릭추가15·중복/지연/보관은 유지합니다. 미연결 지표는 연동 대기, 실제 통계는 주기 집계하며 예산 제공 제어와 구분합니다. 첫 관리 로그는 ad_admin_changes 내부 log_relay로 전달합니다. 업종별 입력/태그/매칭/순환은4차 인계에서 정하고3차 API/DB/화면/검증의 선행 조건으로 넣지 않습니다.

## 1. 관리 화면과 공개 배치

B는 `/admin/ads`에서 게시/예약 수·오늘 노출/클릭의 4개 요약, 전체/top/bottom·상태 필터, 목록의 누적 지표, 등록/수정·저장/중단·PC/모바일 미리보기를 제공합니다. C는 공통 로그인과 공개 화면의 배너를 연결합니다. ADMIN 인증/활성/광고 권한은 B의 공통 인증 API가 매 요청 검사합니다. 로그인은 ADMIN을 광고 관리로 이동시키고 로그아웃은 광고 상태를 바꾸지 않습니다.

입력은 title·asset_id·link_url·placement(top/bottom)·starts_at·ends_at·priority입니다. 3차는 카페 전용이며 targeting_mode·target_tag_codes·tag_catalog_version 같은 업종/태그 필드를 저장하거나 입력받지 않습니다. 광고 한 기록의 위치는 하나이며 같은 asset의 양쪽 게시는 별도 두 ad_id입니다. 수정에는 `version`을 보내고 서버가 원자 조건 갱신합니다. 등록/수정/중단은 공통 `Idempotency-Key`와 요청 해시를 사용하며 같은 키/다른 본문은409입니다. 실제 충돌은 VERSION_CONFLICT/409와 최신 상태를 확인하는 흐름입니다. 제목 길이·priority 허용 범위 등 아직 없는 운영 숫자는 AD-M01/03에서 보완합니다.

```text
paused이면 STOPPED
그 외 now < starts_at이면 RESERVED
그 외 starts_at <= now < ends_at이면 ACTIVE
그 외 ENDED
```

시각은 UTC 저장/응답·KST 관리 입력/표시입니다. `starts_at < ends_at`을 검사합니다. 상태는 조회 시각에 다시 계산하고 스케줄러 실행 결과만 믿지 않습니다. 단순 PUT은 paused를 해제하지 않으며 재개 API/버튼은 미정입니다. 첫 관리 단계의 저장/중단 성공은 ads와 ad_admin_changes의 감사/멱등 응답·내부 log_relay 상태를 같은 MongoDB 트랜잭션으로 커밋한 것입니다. 별도 outbox 컬렉션을 먼저 만들지 않습니다.

상단은 메뉴 아래/날씨 위, 하단은 본문 다음 일반 흐름입니다. 폭은 사용 가능100%/최대1536px, 높이는 top120px/bottom104px입니다. PC 권장2배 소재는3072×240/208, 모바일390px 폭에서도 높이는120/104px를 유지합니다. 사진 cover·HTML 제목/버튼·title 기반 alt, 키보드/반응형을 제공합니다. 별도 모바일 필수 업로드를 추가하지 않습니다.

## 2. API 목록과 데이터 계약

3차에는 광고 업종 사전 API를 추가하지 않습니다. 업종 태그 입력·필터·사용자 업종 문맥은 [4차 업종 매칭 가이드](./06_4차_광고_업종매칭_확장_가이드.md)에서 다시 검토합니다.

3차 광고 관리 목록 필터는 placement/status로 제한합니다. GET /api/admin/ad-target-tags와 사용자 업종 입력/저장 API는 3차에 제공하지 않으며 4차 확장 가이드의 검토 항목입니다.

| 메서드·경로 | 입력/반환·핵심 검사 | 접근/담당 |
|---|---|---|
| GET /api/ads | placement 필수, 재확인 시 delivery_id. ad·evaluated_at·valid_until | 공개, B 제공/C 연결 |
| POST /api/ad-events | delivery_id·event_id·event_type·occurred_at. counted·처리 결과 | 공개 문맥/배달 검증, B |
| GET /api/admin/ads | placement/status 필터·version. 누적 측정 미연결은 연동 대기 | ADMIN 광고 조회, B |
| POST /api/admin/ad-assets | 정적 이미지 Binary 저장·asset_id·검사 결과. 실제 image_url 계약은 공개 조회 인계 | ADMIN 광고 변경, B/INF |
| POST /api/admin/ads | 위 입력, 저장된 ad_id·version·서버 상태 | ADMIN 광고 변경, B |
| PUT /api/admin/ads/{id} | 전체 편집값·version, paused 유지 | ADMIN 광고 변경, B |
| POST /api/admin/ads/{id}/stop | version·멱등 키, stopped_at·version·STOPPED | ADMIN 광고 변경, B |
| GET /api/admin/ads/summary | 게시/예약 수는 실제 계산. 측정 미연결은 연동 대기, 연결 후 주기 집계 범위/시각 | ADMIN 광고 조회, B |
| POST /api/admin/ads/preview | 등록 전 편집 소재도 검증·PC/모바일 자료 반환. 운영 delivery 발급 없음 | ADMIN, B |

ID는 불투명 문자열, JSON은 snake_case, 시각은 UTC Z입니다. 공개 ad 객체는 ad_id·creative_version·placement·title·image_url·link_url·delivery_id와 클라이언트 제출용 불투명 delivery 검증 자료만 제공합니다. 관리 계정/예산/중단 원본·MongoDB 내부 ID는 공개하지 않습니다. 정상 광고 없음은 `ad:null`이며 조회 자체는 노출/클릭이 아닙니다. 목록 페이지/정렬·summary의 실제 응답 모델은 B가 기존 공통 계약과 함께 OpenAPI로 고정하고 C와 같은 fixture를 사용합니다. 미구현 모델을 실제 응답이라고 표시하지 않습니다.

광고 측정 입력에서 owner_guest_id·ad_id·creative_version·placement·인정 여부·토큰·is_test를 임의 지정하게 하지 않습니다. 서버의 문맥/delivery에서 결정합니다. 클라이언트의 occurred_at은 검증 대상이며 신뢰된 서버 시각처럼 취급하지 않습니다. measurement 요청은 event_id 멱등을 사용하고 관리 변경의 Idempotency-Key와 섞지 않습니다.

정상 처리/억제의 200 응답 개발 기준은 `event_id`, `delivery_id`, `event_type`, `result`, `counted`, `occurred_at`, `received_at`, `processed_at`, `ads_policy_version`입니다. 최초 본문/응답을 저장하고 동일 event_id·정규 본문 재전송에 같은 응답을 반환합니다. 같은 ID의 다른 본문은 IDEMPOTENCY_CONFLICT/409, malformed/type/금지 필드는 VALIDATION_ERROR/422입니다. 미인증 관리401·권한 없음403·없는/타 소유 delivery404, DB 장애503은 공통 오류 형식을 적용합니다. 날짜/당시 유효성에서 제외한 정상 형태 보고는 counted=false와 사유를 반환하고 성공 노출로 집계하지 않습니다.

## 3. 첫 방문·문맥과 조회 실패

1. 최초 상단 조회에서 기존 유효 guest 쿠키를 재사용하거나 B의 공통 guest 서비스가 발급합니다. 광고가 없어도 동일하며 추천·지역·로그인이 필요하지 않습니다.
2. C는 최초 상단 응답 후 하단 조회/측정 전송을 시작합니다. 상단 부트스트랩 실패에는 재시도로 문맥을 확보하며 무문맥 측정을 운영으로 성공 처리하지 않습니다. 광고 영역 실패가 추천 이용을 막지는 않습니다.
3. 문맥/ADMIN 원본은 PostgreSQL에 유지하고 MongoDB에는 서버 검증된 내부 ID만 참조합니다. 쿠키 원문/로그인 비밀번호를 저장하거나 광고 DB에 계정을 복제하지 않습니다.
4. 쿠키 저장 불가에서도 배너/링크 이동은 가능하며 측정은 MEASUREMENT_UNAVAILABLE로 운영 집계/예상 비용에서 제외합니다. 문맥 발급/조회는 광고/음악 행동 로그의 성공 지표가 아닙니다.

## 4. 후속 공개 단계 — 카페 광고 선정·중단 3초·열린 화면

기간·paused·위치·사용 가능한 소재·예산 자격을 통과한 카페 광고 중 높은 priority를 우선하고 동률은 ad_id 코드 포인트 순으로 위치별 round-robin을 적용합니다. top/bottom 순환 상태는 분리하고 새 delivery 발급과 커서 이동을 같은 MongoDB 트랜잭션으로 기록합니다. 기존 delivery 재확인·관리 미리보기·멱등 재전송은 커서를 진행하지 않습니다.

기존 delivery는 C가1초마다 같은 조회 경로에 delivery_id를 붙여 재확인합니다. MongoDB primary의 현재 광고 상태를 읽고 `valid_until <= min(evaluated_at+3초, ends_at)`을 발급합니다. 중단 커밋 시각 t_stop부터 새 제공은 차단하며 정상 활성 화면은 t_stop+3초 이내 숨깁니다. 이전 캐시/늦은 응답으로 기한을 연장하지 않고 C는 왕복시간을 보수적으로 차감합니다. 확인 실패/기한 종료 시 배너와 노출 타이머를 중단하고 탭 복귀에는 재확인부터 합니다. 숨김·재확인은 새 노출이 아닙니다.

중단 전 발생한 유효 보고는300초 이내 수신 시 검사할 수 있고 중단 후 발생 보고는 화면 반영이 늦어도 제외합니다. 소재 수정 전 delivery의 향후 표시/무효화 세부는 AD-M06/15의 미정이며 당시 snapshot을 현재 소재로 덮지 않습니다. 3초 표시 기한·측정 지연300초·delivery 자체 수명·보관90일은 네 가지 별도 개념입니다.

## 5. 후속 측정·반복·예상 사용량과 주기 통계

노출은 이미지 로딩 완료·활성 탭·면적50% 이상·연속1000ms가 모두 충족될 때 VIEWABLE_IMPRESSION입니다. 조건 중단 시 타이머를 초기화합니다. 안내 가림·예시·미리보기·테스트·화면 밖·배경 탭·이미지 실패는 운영 제외입니다. 실제 CLICK은 사용자 조작만 보고하며 성공 이동을 측정 응답 대기 조건으로 두지 않습니다. 새 탭 HTTPS에 noopener noreferrer를 적용합니다.

처리 순서는 동일 event_id/본문의 최초 판정 재반환 → 문맥/배달·발생/수신·당시 유효성 → delivery/type 최초 처리 → 반복 창 → 원자 저장입니다. 미래 발생 시각과 수신 지연300초 초과는 제외하며 정확히300초는 검사합니다. COUNTED·DELIVERY_DUPLICATE·REPEAT_SUPPRESSED·LATE_EVENT·DELIVERY_INVALID·MEASUREMENT_UNAVAILABLE를 구분합니다.

delivery마다 각 종류 최초 유효 처리만 소비합니다. 새 delivery도 `(owner_guest_id, ad_id, placement, event_type)`의 서버 accepted_at부터 노출60초/클릭300초 동안 추가 인정하지 않습니다. 정확한 경계부터 인정하며 소재 버전 변경만으로 초기화하지 않습니다. 억제/재전송은 accepted_at을 연장하지 않고 이미 억제된 delivery를 창 종료 후 다시 성공 처리하지 않습니다. 노출/클릭 창은 별개입니다.

집계 일자는 검증된 occurred_at의 KST 날짜입니다. received_at·processed_at·accepted_at을 따로 보존하고 오늘 합계와 광고별 누적을 구분합니다. 유효 노출 top8/bottom5, 인정 클릭15토큰을 예상 원장에 기록합니다. 조기 클릭은15만, 정상 노출 후 클릭은 top23/bottom20이며 중복/억제는0입니다. 실제 결제/잔액 차감은 수행하지 않습니다. 예산 수치/경계·예약/초과 처리 미정은 테스트용 명시 정책으로만 검증합니다.
