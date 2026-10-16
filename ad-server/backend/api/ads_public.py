"""공개 배달·측정 API. 관리 화면과 계정 원본은 이 경계에서 구현하지 않습니다."""

from io import BytesIO
from uuid import uuid4

from django.conf import settings
from django.http import FileResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView

from api.ads import ERROR_RESPONSES, error_response, query_filters
from api.ads_public_auth import load_public_policy, resolve_guest
from api.ads_public_serializers import (
    AdEventInputSerializer,
    AdEventResponseSerializer,
    PublicAdsResponseSerializer,
)
from domains.ads.errors import DomainError, ValidationError
from domains.ads.public_service import AdsPublicService
from repositories.ads_policy_mongo import get_ads_policy_repository
from repositories.ads_public_mongo import get_public_ads_repository

DELIVERY_HEADER = OpenApiParameter(
    name="X-Ad-Delivery-Token",
    type=str,
    location=OpenApiParameter.HEADER,
    required=True,
    description="공개 광고 조회에서 발급받은 불투명 검증 자료",
)


def delivery_token(request) -> str:
    value = request.headers.get("X-Ad-Delivery-Token", "")
    if not value.strip():
        raise ValidationError(fields=["delivery_token"])
    return value


def get_public_service() -> AdsPublicService:
    policy = load_public_policy()
    return AdsPublicService(
        get_ads_policy_repository() if policy.check_budget_history else get_public_ads_repository(),
        policy=policy,
        signing_key=settings.ADS_DELIVERY_SIGNING_KEY,
        public_base_url=settings.ADS_PUBLIC_BASE_URL,
        is_test=settings.ADS_IS_TEST,
    )


@extend_schema(
    description=(
        "공통 서버의 guest 문맥과 명시 운영 정책이 필요합니다. "
        "수명·예산·소재 수정 정책 미연결 시 503입니다."
    ),
    extensions={"x-shared-guest-required": True, "x-public-policy-required": True},
)
class AdsPublicView(APIView):
    authentication_classes = []
    permission_classes = []
    parser_classes = [JSONParser]

    def initialize_request(self, request, *args, **kwargs):
        self.request_id = uuid4().hex
        self.guest_context = None
        return super().initialize_request(request, *args, **kwargs)

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            try:
                SessionAuthentication().enforce_csrf(request._request)
            except PermissionDenied:
                raise DomainError(
                    "FORBIDDEN", "요청 출처 또는 CSRF 검증에 실패했습니다.", 403
                ) from None

    def handle_exception(self, exc):
        response = error_response(exc, self.request_id)
        return response if response is not None else super().handle_exception(exc)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        if self.guest_context is not None and self.guest_context.response_finalizer is not None:
            try:
                finalized = self.guest_context.response_finalizer(response)
                if finalized is not None and finalized is not response:
                    raise ValueError
            except Exception:
                response = error_response(
                    DomainError("GUEST_UNAVAILABLE", "공유 방문자 문맥 응답에 실패했습니다.", 503),
                    self.request_id,
                )
                response = super().finalize_response(request, response, *args, **kwargs)
        response["X-Request-ID"] = self.request_id
        if settings.ADS_API_CONTRACT_VERSION:
            response["X-Contract-Version"] = settings.ADS_API_CONTRACT_VERSION
        response["Cache-Control"] = "no-store"
        response["Referrer-Policy"] = "no-referrer"
        return response

    def guest(self, request, *, bootstrap):
        self.guest_context = resolve_guest(request, bootstrap=bootstrap)
        return self.guest_context


class PublicAdsView(AdsPublicView):
    @extend_schema(
        tags=["ads-public"],
        responses={**ERROR_RESPONSES, 200: PublicAdsResponseSerializer},
        parameters=[
            OpenApiParameter(name="placement", type=str, enum=["top", "bottom"], required=True),
            OpenApiParameter(name="delivery_id", type=str),
            OpenApiParameter(
                name="X-Ad-Delivery-Token",
                type=str,
                location=OpenApiParameter.HEADER,
                description="delivery_id 재확인 시 필수",
            ),
            OpenApiParameter(
                name="Idempotency-Key",
                type=str,
                location=OpenApiParameter.HEADER,
                description="신규 배달 발급의 동일 소유·위치 재전송 키",
            ),
        ],
    )
    def get(self, request):
        placement, _ = query_filters(request, {"placement", "delivery_id"})
        if placement is None:
            raise ValidationError(fields=["placement"])
        existing_delivery = request.query_params.get("delivery_id")
        if existing_delivery is not None and not existing_delivery.strip():
            raise ValidationError(fields=["delivery_id"])
        proof = delivery_token(request) if existing_delivery is not None else None
        key = request.headers.get("Idempotency-Key")
        if key is not None and not key.strip():
            raise ValidationError(fields=["idempotency_key"])
        context = self.guest(request, bootstrap=placement == "top" and existing_delivery is None)
        body = get_public_service().provide(
            placement,
            owner_guest_id=context.owner_guest_id,
            measurement_available=context.measurement_available,
            delivery_id=existing_delivery,
            delivery_token=proof,
            idempotency_key=key,
            request_id=self.request_id,
        )
        return Response(body)


class PublicAdEventsView(AdsPublicView):
    @extend_schema(
        tags=["ads-public"],
        request=AdEventInputSerializer,
        responses={**ERROR_RESPONSES, 200: AdEventResponseSerializer},
        parameters=[DELIVERY_HEADER],
        description=(
            "CSRF/Origin 및 서버 guest 문맥을 확인한 후 네 필드만 도메인에서 검사합니다. "
            "event_id 재전송은 최초 판정 응답을 반환합니다."
        ),
    )
    def post(self, request):
        query_filters(request, set())
        proof = delivery_token(request)
        context = self.guest(request, bootstrap=False)
        return Response(
            get_public_service().record_event(
                request.data,
                owner_guest_id=context.owner_guest_id,
                measurement_available=context.measurement_available,
                delivery_token=proof,
                request_id=self.request_id,
            )
        )


class PublicAdImageView(AdsPublicView):
    @extend_schema(
        tags=["ads-public"],
        responses={**ERROR_RESPONSES, 200: OpenApiTypes.BINARY},
        parameters=[OpenApiParameter(name="delivery_token", type=str, required=True)],
        description=(
            "배달 proof와 서버 게시 자격을 검증한 광고 이미지 원본만 반환합니다. "
            "proof는 광고 이미지 읽기 권한이며 계정/guest 쿠키를 발급하지 않습니다."
        ),
        extensions={"x-shared-guest-required": False, "x-public-policy-required": True},
    )
    def get(self, request, delivery_id):
        query_filters(request, {"delivery_token"})
        proof = request.query_params.get("delivery_token", "")
        if not proof.strip():
            raise ValidationError(fields=["delivery_token"])
        image_bytes, mime_type = get_public_service().read_image(delivery_id, delivery_token=proof)
        return FileResponse(BytesIO(image_bytes), content_type=mime_type)
