# ad-server/backend/domains/ads/service.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../../../ad-server/backend/domains/ads/service.py)

광고 관리의 이미지 업로드·광고 생성·수정·중단과 선택 예산 설정을 수행합니다. 입력은 검증할 원본/광고 body, 서버에서 검증한 actor 외부 참조, 멱등키·request ID입니다. 출력은 ServiceResult의 HTTP 상태와 고정 응답 body입니다.

멱등키는 관리자 출처/계정·operation·scope로 구분하고 request_hash를 비교합니다. 같은 요청의 재시도는 최초 성공 응답을 재생하며 다른 body는 409입니다. 이 조회는 수정/중단 version 검사보다 먼저 수행합니다. 각 중첩 commit 콜백은 저장소 run의 트랜잭션 안에서 광고/이미지와 감사·멱등·MongoDB 내장 로그을 함께 기록합니다.

version 비교, no-op의 version/updated_at 유지, 정지 후 PUT에서도 paused 유지, 이미지 원본 보존을 적용합니다. 소재 필드 title/asset_id/link_url의 실제 변경 때 creative_version을 새로 만듭니다. 상태는 paused 우선·시작 포함/종료 제외로 계산합니다. 로그에는 이미지 Binary나 세션 비밀값을 넣지 않으며 광고 로그는 같은 MongoDB 트랜잭션에 저장하며 외부 전달은 수행하지 않습니다. 공개 delivery·노출/클릭·예산 집계는 별도 서비스가 담당합니다. 선택 예산2개는 함께 입력하며 생략 수정은 기존 값/예산 버전을 보존합니다. 실제 예산 변경만 새 불투명 budget_version과 감사 snapshot을 만들고 누락 광고에 운영 기본액을 채우지 않습니다. 자동 종료는 현재 예산 버전의 서버 annotation으로 조회하며 수동 STOPPED가 우선합니다. ENDED의 end_reason은 PERIOD_ENDED/BUDGET_EXHAUSTED로 구분하고 자동 상태가 관리자의paused/일정을 바꾸지 않습니다.

`_mutation_context`는 재시도 콜백마다 실제 적용 구간의 시각을 다시 정합니다. 수정/중단은 현재 광고를 조건부 쓰기로 잠근 뒤 같은 시각을 updated_at·stopped_at·감사 snapshot에 적용하여 요청 대기 시각으로 소급하지 않습니다. 이는 잠금 뒤 업무 효력 시각이며 MongoDB가 반환한 실제 commit timestamp와 구분합니다. 공개 서비스는 이 관리 감사 snapshot을 당시 자격 판정에 연결합니다.

현행 로그 구조와 이전 자료 보존은 [광고 로그 저장 계약](../../../../../../development/ads/MongoDB_광고_로그_저장_계약.md)을 따릅니다.

## AST 시그니처

```python
class ServiceResult
_json_value(value)
canonical_hash(value)
ad_status(ad, now)
serialize_ad(ad, now)
serialize_asset(asset)
class AdsService
AdsService.__init__(self, repository, clock=None, id_factory=None, is_test=False)
AdsService._context(self, actor, idempotency_key, request_id, operation, scope, data)
AdsService._replay(self, repository, context)
AdsService._mutation_context(self, context)
AdsService._asset(self, repository, asset_id)
AdsService._ad(self, repository, ad_id, version)
AdsService._record(self, context, *, asset_id, ad_id, before, after, changed, result)
AdsService.upload_asset(self, image_bytes, *, actor, idempotency_key, request_id)
AdsService.create_ad(self, data, *, actor, idempotency_key, request_id)
AdsService.update_ad(self, ad_id, data, *, actor, idempotency_key, request_id)
AdsService.stop_ad(self, ad_id, data, *, actor, idempotency_key, request_id)
```
