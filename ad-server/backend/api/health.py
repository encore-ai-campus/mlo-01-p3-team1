from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthResponseSerializer(serializers.Serializer):
    status = serializers.CharField()
    service = serializers.CharField()
    database_checked = serializers.BooleanField()


class HealthView(APIView):
    authentication_classes = []
    permission_classes = []

    @extend_schema(responses=HealthResponseSerializer, tags=["development"])
    def get(self, request):
        return Response({"status": "ok", "service": "ads-api", "database_checked": False})
