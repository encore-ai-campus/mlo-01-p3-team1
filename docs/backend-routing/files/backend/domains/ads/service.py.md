# backend/domains/ads/service.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../../backend/domains/ads/service.py)

첫 광고 관리 단계의 이미지 업로드·광고 생성·수정·중단을 수행합니다. 입력은 검증할 원본/광고 body, 서버에서 검증한 actor 외부 참조, 멱등키·request ID입니다. 출력은 ServiceResult의 HTTP 상태와 고정 응답 body입니다.

멱등키는 관리자 출처/계정·operation·scope로 구분하고 request_hash를 비교합니다. 같은 요청의 재시도는 최초 성공 응답을 재생하며 다른 body는 409입니다. 이 조회는 수정/중단 version 검사보다 먼저 수행합니다. 각 중첩 commit 콜백은 저장소 run의 트랜잭션 안에서 광고/이미지와 감사·멱등·PENDING 로그 사본을 함께 기록합니다.

version 비교, no-op의 version/updated_at 유지, 정지 후 PUT에서도 paused 유지, 이미지 원본 보존을 적용합니다. 소재 필드 title/asset_id/link_url의 실제 변경 때 creative_version을 새로 만듭니다. 상태는 paused 우선·시작 포함/종료 제외로 계산합니다. 로그에는 이미지 Binary나 세션 비밀값을 넣지 않으며 PostgreSQL 전송은 worker가 별도로 수행합니다. 공개 delivery·노출/클릭·예산 집계는 이 서비스의 구현 범위에 포함하지 않습니다.

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
AdsService._asset(self, repository, asset_id)
AdsService._ad(self, repository, ad_id, version)
AdsService._record(self, context, *, asset_id, ad_id, before, after, changed, result)
AdsService.upload_asset(self, image_bytes, *, actor, idempotency_key, request_id)
AdsService.create_ad(self, data, *, actor, idempotency_key, request_id)
AdsService.update_ad(self, ad_id, data, *, actor, idempotency_key, request_id)
AdsService.stop_ad(self, ad_id, data, *, actor, idempotency_key, request_id)
```
