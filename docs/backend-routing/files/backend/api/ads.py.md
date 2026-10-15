# backend/api/ads.py

- 작성일: 2026-10-15
- 수정일: 2026-10-15
- [원본 코드](../../../../../backend/api/ads.py)

HTTP 관리 API를 도메인 서비스와 저장소에 연결합니다. `AdsAdminView`는 서버 request ID를 발급하고 공통 ADMIN 검증 뒤에만 본문을 해석합니다. 응답에는 X-Request-ID, 설정 시 X-Contract-Version, no-store를 적용합니다. `error_response`는 code/message/request_id와 필요한 필드명만 반환하며 연결 정보·저장된 비밀값을 노출하지 않습니다.

입력은 JSON 광고/중단 요청, multipart 이미지, 필터/커서와 Idempotency-Key 헤더입니다. 생성·수정·중단·업로드는 `AdsService`로 전달하고 목록/요약은 `MongoAdsRepository`에서 조회합니다. 목록 커서는 서명되며 필터·page_size·조회 시각에 귀속됩니다. `verified_asset`은 원본 디코딩과 저장 metadata 일치를 확인합니다.

이미지 읽기는 ADMIN 검증 후 원본 FileResponse, 미리보기는 읽기 권한 및 CSRF 검증 후 화면 연결용 크기/이미지 metadata를 반환합니다. 미리보기는 저장·배달·측정을 만들지 않습니다. 요약은 실제 광고 상태 개수와 미연결 측정값(null/연동 대기)을 구분합니다. 실제 URL/메서드 대응은 이 색인의 API 연결 표를 따릅니다.

OpenAPI는 공통 오류 응답, 저장 변경의 Idempotency-Key 헤더와 공유 ADMIN 필수 마커를 포함합니다. 명세 표시는 실제 공유 인증 연결 완료를 의미하지 않습니다.

## AST 시그니처

```python
error_response(exc, request_id)
idempotency_key(request)
query_filters(request, allowed)
verified_asset(asset_id)
class AdsAdminView(APIView)
AdsAdminView.initialize_request(self, request, *args, **kwargs)
AdsAdminView.initial(self, request, *args, **kwargs)
AdsAdminView.handle_exception(self, exc)
AdsAdminView.finalize_response(self, request, response, *args, **kwargs)
AdsAdminView.service(self)
class AdsCollectionView(AdsAdminView)
AdsCollectionView.get(self, request)
AdsCollectionView.post(self, request)
class AdUpdateView(AdsAdminView)
AdUpdateView.put(self, request, ad_id)
class AdStopView(AdsAdminView)
AdStopView.post(self, request, ad_id)
class AdAssetUploadView(AdsAdminView)
AdAssetUploadView.post(self, request)
class AdAssetReadView(AdsAdminView)
AdAssetReadView.get(self, request, asset_id)
class AdPreviewView(AdsAdminView)
AdPreviewView.post(self, request)
class AdsSummaryView(AdsAdminView)
AdsSummaryView.get(self, request)
```
