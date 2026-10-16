# ad-server/backend/domains/ads/public_service.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../../../ad-server/backend/domains/ads/public_service.py)

공개 선정·delivery 발급/재확인·원본 이미지·최초 측정 판정을 저장소 run 콜백으로 연결합니다. 검증된 guest 내부 참조만 받고 사용자/관리자 화면·계정 원본은 만들지 않습니다. AdsPublicPolicy·서명 키·HTTPS 공개 주소가 필요하며 미정 정책을 기본 허용으로 바꾸지 않습니다.

provide는 최고 priority/위치별 동률 순환을 계산해 광고 경합 검사·커서 이동·delivery snapshot을 원자 저장합니다. 동일 발급 키 재전송은 최초 응답을 보존하고 기존 delivery 재확인은 커서를 이동하지 않습니다. 재확인은 현재 게시/소재/예산 자격을 검사하며 표시 기한을 확인+3초·발급 당시 종료·현재 단축 종료·delivery 만료 이내로 제한합니다.

HMAC proof를 검증하고 타 소유는404로 가립니다. read_image는 동일 proof와 현재 게시 자격으로 저장 원본만 반환합니다. 측정은 같은 event_id의 최초 본문/응답을 재반환하고 다른 본문은409입니다. 신규 보고는 관리 감사의 당시 광고 snapshot·수신/처리 시각·delivery/type claim·공유 반복 창을 판정합니다. claim/창/최초 이벤트·불변 응답/MongoDB 내장 로그·인정 시 예상 원장을 한 MongoDB 트랜잭션에 저장합니다.

쿠키 불가/테스트 측정은 운영 인정과 원장에 넣지 않습니다. 지연300초·노출60초/클릭300초·발생일KST·8/5/15 예상 토큰 규칙을 사용하며 실제 결제나 일별 집계를 요청 안에서 수행하지 않습니다. 별도5분 검증 상태로 신규/기존 표시·이미지를 차단하고 발생 당시 budget_version의 cutoff 전 보고는300초 안에서 인정합니다. budget_policy_version 마커가 있는 새 배달만 당시 예산 이력을 검사하며 마커 없는 기존 배달에 소급하지 않습니다. 마커도HMAC에 포함하고 최초 판정의 정책 버전은 배달 마커에서 보존합니다.

split_deadlines=False 기본 경로는 기존 단일 event_expires_at과 HMAC payload를 그대로 유지합니다. True로 명시한 선택 경로는 display_expires_at을 추가 저장하고 보고 기한은 기존 event_expires_at에 저장합니다. 표시·이미지는 display_expires_at, 신규 보고 수신은 event_expires_at을 사용하고 발생 시각은 표시 마감 미만이어야 합니다. 새 표시 마감도 HMAC 서명에 포함하며 필드가 없는 과거 배달의 서명과 최초 응답은 바꾸지 않습니다. helper의30분은 배달 수명이며 캠페인 ends_at을 변경하지 않습니다. cap_at_midnight=False는 자정 단축을 적용하지 않습니다. 현재 runtime provider도 자정 cap을False로 유지합니다. 소재/위치 수정 뒤 옛 배달의 새 표시/발생은 거절하고 수정 전 당시 자격은 이력으로 확인합니다. processed_at/accepted_at은 광고 잠금·이력·반복 창 조회 후 판정 직전에 채집하여 대기 시간을 반복 창에서 빼지 않습니다.

현행 로그 구조와 이전 자료 보존은 [광고 로그 저장 계약](../../../../../../development/ads/MongoDB_광고_로그_저장_계약.md)을 따릅니다.

## AST 시그니처

```python
_reference(value, name, *, nullable=False)
_context(owner_guest_id, measurement_available, request_id)
_snapshot(ad)
_active(ad, placement, now)
class AdsPublicService
AdsPublicService.__init__(self, repository, *, policy, signing_key, public_base_url, is_test, clock=None, id_factory=None)
AdsPublicService._now(self)
AdsPublicService._policy(self, callback, *args)
AdsPublicService._asset(self, repository, asset_id)
AdsPublicService._token(self, delivery)
AdsPublicService._verify_delivery(self, repository, delivery_id, token)
AdsPublicService._owner(self, delivery, owner_guest_id)
AdsPublicService._empty(self, now, measurement_available)
AdsPublicService._response(self, delivery, now, measurement_available, *, ends_at=None)
AdsPublicService._open_ad(self, repository, delivery, now)
AdsPublicService.provide(self, placement, *, owner_guest_id, measurement_available, request_id, delivery_id=None, delivery_token=None, idempotency_key=None)
AdsPublicService._log_record(self, event, decision, delivery, request_id)
AdsPublicService.record_event(self, data, *, owner_guest_id, measurement_available, delivery_token, request_id)
AdsPublicService.read_image(self, delivery_id, *, delivery_token)
```
