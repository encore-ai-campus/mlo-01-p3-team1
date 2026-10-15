# backend/api/ads_serializers.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../backend/api/ads_serializers.py)

OpenAPI용 광고 생성·수정·중단·목록/응답·업로드·오류 필드를 정의합니다. 광고 body, 버전, multipart image, 응답 metadata의 모양을 API schema에 연결합니다.

업무 요청의 실제 strict 검증은 `domains/ads/validation.py`에서 수행합니다. serializer의 자동 형 변환으로 bool/문자열 priority나 알 수 없는 입력을 수용하지 않습니다. 이 모듈은 DB 조회·저장·권한 판정을 하지 않습니다.

`AdsInputSerializer`의 하위 요청을 `AdsInputSchemaExtension.map_serializer`가 연결하여 request의 additionalProperties=false를 명시합니다. settings의 COMPONENT_SPLIT_REQUEST=True로 요청/응답 컴포넌트를 구분하고 multipart FileField를 binary 입력으로 표시합니다. 실제 입력 검증은 여전히 도메인에서 수행합니다.

## AST 시그니처

```python
class AdsInputSerializer(serializers.Serializer)
class AdCreateSerializer(AdsInputSerializer)
class AdUpdateSerializer(AdCreateSerializer)
class AdStopSerializer(AdsInputSerializer)
class AdResponseSerializer(AdCreateSerializer)
class AdsListSerializer(serializers.Serializer)
class AssetUploadSerializer(AdsInputSerializer)
class AssetResponseSerializer(serializers.Serializer)
class ErrorResponseSerializer(serializers.Serializer)
class AdsInputSchemaExtension(OpenApiSerializerExtension)
AdsInputSchemaExtension.map_serializer(self, auto_schema, direction)
```
