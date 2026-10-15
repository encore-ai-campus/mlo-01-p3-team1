# backend/domains/ads/validation.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../../backend/domains/ads/validation.py)

광고 입력·중단 입력·시간·이미지·BSON을 서버에서 검사합니다. 생성은 허용 광고 필드 전체, 수정은 같은 필드와 양의 정수 version, 중단은 version만 받습니다. 업종/태그를 포함한 미정 필드는 거절합니다. placement는 top/bottom, priority는 bool을 제외한 strict 정수와 BSON int64 표현 범위로 검사합니다. 이 범위는 운영 priority 정책을 확정한 값이 아닙니다.

시간대가 있는 ISO 시각을 UTC·밀리초로 고정하고 시작<종료를 확인합니다. link_url은 자격증명/공백 등이 없는 절대 HTTPS URL로 검사합니다. 이미지 원본은 1~2,000,000바이트의 정적 PNG/JPEG/WebP만 허용하며 실제 디코딩·프레임/무결성·크기·SHA-256을 확인합니다. BSON은 인코딩 가능성과 16MiB를 검사합니다.

검증된 값/metadata나 바이트 크기를 반환하고 실패는 도메인 오류로 전달합니다. `AdsService`와 API 미리보기/이미지 읽기가 사용하며 저장이나 인증은 수행하지 않습니다.

## AST 시그니처

```python
utc_datetime(value)
utc_string(value)
validate_fields(data, allowed, required=None)
validate_positive_version(value)
validate_ad_input(data, with_version=False)
validate_stop_input(data)
validate_image(data)
validate_bson_size(document)
```
