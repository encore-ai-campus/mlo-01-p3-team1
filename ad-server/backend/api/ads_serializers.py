from drf_spectacular.extensions import OpenApiSerializerExtension
from rest_framework import serializers


class AdsInputSerializer(serializers.Serializer):
    """요청 명세의 공통 경계. 실제 strict 검증은 광고 도메인이 수행합니다."""


class AdCreateSerializer(AdsInputSerializer):
    title = serializers.CharField()
    asset_id = serializers.CharField()
    link_url = serializers.URLField()
    placement = serializers.ChoiceField(choices=["top", "bottom"])
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    priority = serializers.IntegerField(help_text="운영 범위 미정; 서버에서 strict integer 검사")
    daily_budget_tokens = serializers.IntegerField(
        required=False,
        min_value=1,
        max_value=2**63 - 1,
        help_text="total_budget_tokens와 함께 지정; 서버에서 strict integer 검사",
    )
    total_budget_tokens = serializers.IntegerField(
        required=False,
        min_value=1,
        max_value=2**63 - 1,
        help_text="daily_budget_tokens와 함께 지정; 서버에서 strict integer 검사",
    )


class AdUpdateSerializer(AdCreateSerializer):
    version = serializers.IntegerField(min_value=1)


class AdStopSerializer(AdsInputSerializer):
    version = serializers.IntegerField(min_value=1)


class AdResponseSerializer(AdCreateSerializer):
    measurement = serializers.DictField(required=False, read_only=True)
    ad_id = serializers.CharField()
    creative_version = serializers.CharField()
    version = serializers.IntegerField()
    paused = serializers.BooleanField()
    stopped_at = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    status = serializers.ChoiceField(choices=["RESERVED", "ACTIVE", "ENDED", "STOPPED"])
    changed = serializers.BooleanField(required=False)
    daily_budget_tokens = serializers.IntegerField(read_only=True, allow_null=True)
    total_budget_tokens = serializers.IntegerField(read_only=True, allow_null=True)
    budget_version = serializers.CharField(read_only=True, allow_null=True)
    end_reason = serializers.ChoiceField(
        choices=["BUDGET_EXHAUSTED", "PERIOD_ENDED"], read_only=True, allow_null=True
    )


class AdsListSerializer(serializers.Serializer):
    items = AdResponseSerializer(many=True)
    next_cursor = serializers.CharField(allow_null=True)
    as_of = serializers.DateTimeField()


class AssetUploadSerializer(AdsInputSerializer):
    image = serializers.FileField(help_text="정적 PNG/JPEG/WebP, 실제 원본 최대 2,000,000바이트")


class AssetResponseSerializer(serializers.Serializer):
    asset_id = serializers.CharField()
    mime_type = serializers.CharField()
    byte_size = serializers.IntegerField()
    width = serializers.IntegerField()
    height = serializers.IntegerField()
    sha256 = serializers.CharField()
    changed = serializers.BooleanField()


class ErrorResponseSerializer(serializers.Serializer):
    code = serializers.CharField()
    message = serializers.CharField()
    request_id = serializers.CharField()
    details = serializers.DictField(required=False)


class AdsInputSchemaExtension(OpenApiSerializerExtension):
    target_class = "api.ads_serializers.AdsInputSerializer"
    match_subclasses = True

    def map_serializer(self, auto_schema, direction):
        schema = auto_schema._map_serializer(self.target, direction, bypass_extensions=True)
        if direction == "request":
            schema["additionalProperties"] = False
        return schema
