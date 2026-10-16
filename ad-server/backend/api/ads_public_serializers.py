from rest_framework import serializers

from api.ads_serializers import AdsInputSerializer


class PublicAdSerializer(serializers.Serializer):
    ad_id = serializers.CharField()
    creative_version = serializers.CharField()
    placement = serializers.ChoiceField(choices=["top", "bottom"])
    title = serializers.CharField()
    image_url = serializers.URLField()
    link_url = serializers.URLField()
    delivery_id = serializers.CharField()
    delivery_token = serializers.CharField(help_text="서버 발급 불투명 배달 검증 자료")


class PublicAdsResponseSerializer(serializers.Serializer):
    ad = PublicAdSerializer(allow_null=True)
    evaluated_at = serializers.DateTimeField()
    valid_until = serializers.DateTimeField(allow_null=True)
    measurement_available = serializers.BooleanField()


class AdEventInputSerializer(AdsInputSerializer):
    event_id = serializers.CharField()
    delivery_id = serializers.CharField()
    event_type = serializers.ChoiceField(choices=["VIEWABLE_IMPRESSION", "CLICK"])
    occurred_at = serializers.DateTimeField()


class AdEventResponseSerializer(serializers.Serializer):
    event_id = serializers.CharField()
    delivery_id = serializers.CharField()
    event_type = serializers.ChoiceField(choices=["VIEWABLE_IMPRESSION", "CLICK"])
    result = serializers.ChoiceField(
        choices=[
            "COUNTED",
            "DELIVERY_DUPLICATE",
            "REPEAT_SUPPRESSED",
            "LATE_EVENT",
            "DELIVERY_INVALID",
            "MEASUREMENT_UNAVAILABLE",
        ]
    )
    counted = serializers.BooleanField()
    occurred_at = serializers.DateTimeField()
    received_at = serializers.DateTimeField()
    processed_at = serializers.DateTimeField()
    ads_policy_version = serializers.CharField()
