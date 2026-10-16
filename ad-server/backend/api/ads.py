from datetime import datetime
from io import BytesIO
from uuid import uuid4

from django.conf import settings
from django.core import signing
from django.http import FileResponse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import APIException, ParseError, UnsupportedMediaType
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from api.ads_auth import authorize_admin
from api.ads_serializers import (
    AdCreateSerializer,
    AdResponseSerializer,
    AdsListSerializer,
    AdStopSerializer,
    AdUpdateSerializer,
    AssetResponseSerializer,
    AssetUploadSerializer,
    ErrorResponseSerializer,
)
from domains.ads.errors import DatabaseUnavailable, DomainError, ValidationError
from domains.ads.service import AdsService, serialize_ad
from domains.ads.validation import validate_ad_input, validate_image
from repositories.ads_mongo import get_ads_repository

ERROR_RESPONSES = {code: ErrorResponseSerializer for code in (400, 401, 403, 404, 409, 422, 503)}
MUTATION_PARAMETERS = [
    OpenApiParameter(
        name="Idempotency-Key", type=str, location=OpenApiParameter.HEADER, required=True
    ),
]


def error_response(exc, request_id):
    if isinstance(exc, DomainError):
        body = {"code": exc.code, "message": exc.message, "request_id": request_id}
        if exc.fields:
            fields = set()
            for key in exc.fields:
                if key in {"missing_fields", "unknown_fields"} and isinstance(exc.fields, dict):
                    fields.update(exc.fields[key])
                else:
                    fields.add(key)
            body["details"] = {"fields": sorted(fields)}
        return Response(body, status=exc.http_status)
    if isinstance(exc, (ParseError, UnsupportedMediaType)):
        return Response(
            {
                "code": "VALIDATION_ERROR",
                "message": "요청 본문 형식이 올바르지 않습니다.",
                "request_id": request_id,
            },
            status=422,
        )
    if isinstance(exc, APIException):
        return Response(
            {
                "code": "REQUEST_REJECTED",
                "message": "요청을 처리할 수 없습니다.",
                "request_id": request_id,
            },
            status=exc.status_code,
        )
    return None


def idempotency_key(request):
    value = request.headers.get("Idempotency-Key", "")
    if not value.strip():
        raise DomainError(
            "VALIDATION_ERROR", "Idempotency-Key가 필요합니다.", 422, fields=["idempotency_key"]
        )
    return value


def query_filters(request, allowed):
    unknown = sorted(set(request.query_params) - set(allowed))
    repeated = sorted(key for key in allowed if len(request.query_params.getlist(key)) > 1)
    if unknown or repeated:
        raise DomainError(
            "VALIDATION_ERROR",
            "허용되지 않거나 중복된 조회 필드입니다.",
            422,
            fields=sorted(set(unknown + repeated)),
        )
    placement = request.query_params.get("placement")
    status = request.query_params.get("status")
    if placement is not None and placement not in {"top", "bottom"}:
        raise DomainError(
            "OPTION_INVALID", "광고 위치가 올바르지 않습니다.", 400, fields=["placement"]
        )
    if status is not None and status not in {"RESERVED", "ACTIVE", "ENDED", "STOPPED"}:
        raise DomainError(
            "OPTION_INVALID", "광고 상태가 올바르지 않습니다.", 400, fields=["status"]
        )
    return placement, status


def verified_asset(asset_id):
    asset = get_ads_repository().get_asset(asset_id)
    if asset is None:
        raise DomainError("NOT_FOUND", "이미지를 찾을 수 없습니다.", 404)
    try:
        metadata = validate_image(bytes(asset["image_bytes"]))
        if any(metadata[key] != asset[key] for key in metadata):
            raise DatabaseUnavailable("이미지 원본 검증에 실패했습니다.")
    except (ValidationError, KeyError, TypeError):
        raise DatabaseUnavailable("이미지 원본 검증에 실패했습니다.") from None
    return asset, metadata


def measurement_summary(repository, now, *, ad_id=None):
    reader = getattr(repository, "metrics_summary", None)
    if reader is None:
        return {
            "status": "PENDING",
            "message": "연동 대기",
            "impressions": None,
            "clicks": None,
            "estimated_tokens": None,
        }
    metrics = reader(now, ad_id=ad_id)
    prefix = "today" if ad_id is None else "lifetime"
    return {
        "status": metrics["aggregation_status"],
        "message": "연동 대기" if metrics["aggregation_status"] == "PENDING" else "주기 집계",
        "impressions": metrics[f"{prefix}_valid_impressions"],
        "clicks": metrics[f"{prefix}_valid_clicks"],
        "estimated_tokens": metrics[f"{prefix}_estimated_tokens"],
        "as_of": metrics["as_of"].isoformat().replace("+00:00", "Z")
        if metrics["as_of"] is not None
        else None,
        "metric_date_kst": metrics["metric_date_kst"],
        "coverage": metrics["coverage"],
        "coverage_from": metrics.get("coverage_from"),
        "coverage_through": metrics.get("coverage_through"),
        "is_stale": metrics.get("is_stale"),
        "aggregation_interval_seconds": 300,
    }


@extend_schema(
    description="공유 환경의 현재 활성 ADMIN과 광고 권한을 확인합니다. 인증 미연결 시 503입니다.",
    extensions={"x-shared-admin-required": True},
)
class AdsAdminView(APIView):
    authentication_classes = []
    permission_classes = []
    parser_classes = [JSONParser]

    def initialize_request(self, request, *args, **kwargs):
        self.request_id = uuid4().hex
        return super().initialize_request(request, *args, **kwargs)

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        action = "read" if request.method in {"GET", "HEAD", "OPTIONS"} else "write"
        if isinstance(self, AdPreviewView):
            action = "read"
        identity = authorize_admin(request, action)
        self.actor = {
            "account_id": identity.account_id,
            "identity_source": identity.identity_source,
        }

    def handle_exception(self, exc):
        response = error_response(exc, self.request_id)
        return response if response is not None else super().handle_exception(exc)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["X-Request-ID"] = self.request_id
        if settings.ADS_API_CONTRACT_VERSION:
            response["X-Contract-Version"] = settings.ADS_API_CONTRACT_VERSION
        response["Cache-Control"] = "no-store"
        return response

    def service(self):
        return AdsService(get_ads_repository(), is_test=settings.ADS_IS_TEST)


class AdsCollectionView(AdsAdminView):
    @extend_schema(
        tags=["ads-admin"],
        responses={**ERROR_RESPONSES, 200: AdsListSerializer},
        parameters=[
            OpenApiParameter(name=name, type=str)
            for name in ("placement", "status", "page_size", "cursor")
        ],
    )
    def get(self, request):
        placement, status = query_filters(request, {"placement", "status", "page_size", "cursor"})
        size = request.query_params.get("page_size", "20")
        if len(size) > 3 or not size.isascii() or not size.isdecimal() or not 1 <= int(size) <= 100:
            raise DomainError(
                "VALIDATION_ERROR", "page_size는 1~100이어야 합니다.", 422, fields=["page_size"]
            )
        size = int(size)
        now = timezone.now()
        cursor = None
        encoded = request.query_params.get("cursor")
        if encoded:
            try:
                value = signing.loads(encoded, salt="ads-management-cursor")
                if [value["placement"], value["status"], value["page_size"]] != [
                    placement,
                    status,
                    size,
                ]:
                    raise ValueError
                now = datetime.fromisoformat(value["as_of"])
                cursor = (datetime.fromisoformat(value["updated_at"]), value["id"])
            except (signing.BadSignature, KeyError, TypeError, ValueError):
                raise DomainError(
                    "VALIDATION_ERROR", "조회 커서가 올바르지 않습니다.", 422, fields=["cursor"]
                ) from None
        rows, has_more = get_ads_repository().list_ads(
            placement=placement,
            status=status,
            now=now,
            limit=size,
            cursor=cursor,
        )
        next_cursor = None
        if has_more and rows:
            row = rows[-1]
            next_cursor = signing.dumps(
                {
                    "placement": placement,
                    "status": status,
                    "page_size": size,
                    "as_of": now.isoformat(),
                    "updated_at": row["updated_at"].isoformat(),
                    "id": row["_id"],
                },
                salt="ads-management-cursor",
            )
        return Response(
            {
                "items": [
                    {
                        **serialize_ad(row, now),
                        "measurement": measurement_summary(
                            get_ads_repository(), now, ad_id=row["_id"]
                        ),
                    }
                    for row in rows
                ],
                "next_cursor": next_cursor,
                "as_of": now.isoformat().replace("+00:00", "Z"),
            }
        )

    @extend_schema(
        tags=["ads-admin"],
        request=AdCreateSerializer,
        responses={**ERROR_RESPONSES, 201: AdResponseSerializer},
        parameters=MUTATION_PARAMETERS,
    )
    def post(self, request):
        result = self.service().create_ad(
            request.data,
            actor=self.actor,
            idempotency_key=idempotency_key(request),
            request_id=self.request_id,
        )
        return Response(result.body, status=result.http_status)


class AdUpdateView(AdsAdminView):
    @extend_schema(
        tags=["ads-admin"],
        request=AdUpdateSerializer,
        responses={**ERROR_RESPONSES, 200: AdResponseSerializer},
        parameters=MUTATION_PARAMETERS,
    )
    def put(self, request, ad_id):
        result = self.service().update_ad(
            ad_id,
            request.data,
            actor=self.actor,
            idempotency_key=idempotency_key(request),
            request_id=self.request_id,
        )
        return Response(result.body, status=result.http_status)


class AdStopView(AdsAdminView):
    @extend_schema(
        tags=["ads-admin"],
        request=AdStopSerializer,
        responses={**ERROR_RESPONSES, 200: AdResponseSerializer},
        parameters=MUTATION_PARAMETERS,
    )
    def post(self, request, ad_id):
        result = self.service().stop_ad(
            ad_id,
            request.data,
            actor=self.actor,
            idempotency_key=idempotency_key(request),
            request_id=self.request_id,
        )
        return Response(result.body, status=result.http_status)


class AdAssetUploadView(AdsAdminView):
    parser_classes = [MultiPartParser]

    @extend_schema(
        tags=["ads-admin"],
        request=AssetUploadSerializer,
        responses={**ERROR_RESPONSES, 201: AssetResponseSerializer},
        parameters=MUTATION_PARAMETERS,
    )
    def post(self, request):
        if set(request.data) != {"image"} or len(request.data.getlist("image")) != 1:
            raise DomainError(
                "VALIDATION_ERROR", "image 파일 하나만 전달해야 합니다.", 422, fields=["image"]
            )
        image = request.FILES.get("image")
        if image is None or image.size > 2_000_000:
            raise DomainError(
                "VALIDATION_ERROR", "정적 이미지 최대 2MB만 허용합니다.", 422, fields=["image"]
            )
        result = self.service().upload_asset(
            image.read(2_000_001),
            actor=self.actor,
            idempotency_key=idempotency_key(request),
            request_id=self.request_id,
        )
        return Response(result.body, status=result.http_status)


class AdAssetReadView(AdsAdminView):
    @extend_schema(tags=["ads-admin"], responses={**ERROR_RESPONSES, 200: OpenApiTypes.BINARY})
    def get(self, request, asset_id):
        asset, _ = verified_asset(asset_id)
        return FileResponse(BytesIO(asset["image_bytes"]), content_type=asset["mime_type"])


class AdPreviewView(AdsAdminView):
    @extend_schema(
        tags=["ads-admin"], request=AdCreateSerializer, responses={**ERROR_RESPONSES, 200: dict}
    )
    def post(self, request):
        values = validate_ad_input(request.data)
        asset, metadata = verified_asset(values["asset_id"])
        height = 120 if values["placement"] == "top" else 104
        return Response(
            {
                "title": values["title"],
                "placement": values["placement"],
                "link_url": values["link_url"],
                "asset_id": asset["_id"],
                "asset": metadata,
                "desktop": {"max_width": 1536, "height": height},
                "mobile": {"width": 390, "height": height},
                "operational_delivery": False,
            }
        )


class AdsSummaryView(AdsAdminView):
    @extend_schema(tags=["ads-admin"], responses={**ERROR_RESPONSES, 200: dict})
    def get(self, request):
        query_filters(request, set())
        now = timezone.now()
        counts = get_ads_repository().summary(now=now)
        return Response(
            {
                "counts": counts,
                "evaluated_at": now.isoformat().replace("+00:00", "Z"),
                "measurement": measurement_summary(get_ads_repository(), now),
            }
        )
