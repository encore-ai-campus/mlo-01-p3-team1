# ad-server/backend/api/ads_public.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../../ad-server/backend/api/ads_public.py)

공개 광고 조회·측정·이미지의 실제 HTTP 경계입니다. `GET /api/ads`는 placement와 선택 delivery_id를 받고 `X-Ad-Delivery-Token`으로 재확인합니다. 신규 발급에는 선택 `Idempotency-Key`를 전달합니다. `POST /api/ad-events`는 네 필드(event_id/delivery_id/event_type/occurred_at)와 배달 proof를 전달하며 `GET /api/ad-deliveries/<delivery_id>/image`는 query proof로 원본 이미지를 읽습니다.

상단 신규 조회만 공통 guest 부트스트랩을 요청합니다. guest 내부 참조·측정 가능 여부는 서버 어댑터에서 받고 클라이언트 ID/환경 헤더를 사용하지 않습니다. 이미지 capability 조회는 guest 발급 없이 게시 자격만 검사합니다. 측정 POST는 JSON 파싱 전에 CSRF/Origin을 확인합니다. 공통 오류·서버 X-Request-ID·no-store/no-referrer를 적용합니다.

운영 정책·서명 키·HTTPS 공개 주소가 없는 경우 503이며 실제 공통 guest 서비스 연결은 별도입니다. 관리자 화면·실제 배너 렌더링은 구현하지 않습니다.

## AST 시그니처

```python
delivery_token(request) -> str
get_public_service() -> AdsPublicService
class AdsPublicView(APIView)
AdsPublicView.initialize_request(self, request, *args, **kwargs)
AdsPublicView.initial(self, request, *args, **kwargs)
AdsPublicView.handle_exception(self, exc)
AdsPublicView.finalize_response(self, request, response, *args, **kwargs)
AdsPublicView.guest(self, request, *, bootstrap)
class PublicAdsView(AdsPublicView)
PublicAdsView.get(self, request)
class PublicAdEventsView(AdsPublicView)
PublicAdEventsView.post(self, request)
class PublicAdImageView(AdsPublicView)
PublicAdImageView.get(self, request, delivery_id)
```
