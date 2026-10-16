# ad-server/backend/api/ads_public_serializers.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../../ad-server/backend/api/ads_public_serializers.py)

공개 ad·응답·측정 요청/응답의 OpenAPI 형식을 정의합니다. 공개 ad에는 title/link_url/image_url·광고/소재/위치·delivery ID/proof만 포함하며 관리 계정·원본 이미지 바이트·예산 내부 상태는 넣지 않습니다.

측정 입력은 event_id/delivery_id/event_type/occurred_at 네 필드입니다. 결과는 COUNTED/DELIVERY_DUPLICATE/REPEAT_SUPPRESSED/LATE_EVENT/DELIVERY_INVALID/MEASUREMENT_UNAVAILABLE를 구분합니다. 실제 strict 검증·소유/시각/회계 판정은 도메인 서비스에서 수행하며 serializer 설명만으로 대신하지 않습니다.

## AST 시그니처

```python
class PublicAdSerializer(serializers.Serializer)
class PublicAdsResponseSerializer(serializers.Serializer)
class AdEventInputSerializer(AdsInputSerializer)
class AdEventResponseSerializer(serializers.Serializer)
```
