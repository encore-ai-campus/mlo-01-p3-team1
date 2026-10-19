"""Common ADMIN session adapter for the existing local YouTube review registry."""
from django.conf import settings
from rest_framework.response import Response
from backend.recommendation import youtube_review_api as review
from backend.recommendation.api import Endpoint
from backend.recommendation.errors import require
from .identity import admin


class AdminReviewAuthorization:
    def authorize(self, request):
        user = admin(request, 'manage_music')
        require(settings.LOCAL_DEMO or getattr(settings, 'YOUTUBE_REGISTRY_BACKEND', 'disabled') == 'database', 'POLICY_NOT_READY',
                '공유 운영 영상 저장소 연결을 기다리고 있어요.', 503)
        if not settings.LOCAL_DEMO:
            from backend.recommendation.youtube_database import review_actor
            review_actor.set(str(user.pk))
        require('playlist_id' not in request.query_params and 'playlist_id' not in request.data,
                'VALIDATION_ERROR', '관리자 검수는 현재 음악 카탈로그를 사용해 주세요.')
        return None


class Status(Endpoint):
    def get(self, request):
        admin(request, 'manage_music')
        enabled = bool(settings.LOCAL_DEMO or getattr(settings, 'YOUTUBE_REGISTRY_BACKEND', 'disabled') == 'database')
        result = {'enabled': enabled, 'is_test': bool(settings.LOCAL_DEMO), 'auth_mode': 'ADMIN_SESSION'}
        if not settings.LOCAL_DEMO:
            result['authenticated'] = True
        return Response(result)


class Tracks(AdminReviewAuthorization, review.ReviewTracks):
    pass


class Mappings(AdminReviewAuthorization, review.ReviewMappings):
    pass


class Import(AdminReviewAuthorization, review.ReviewImport):
    pass


class Verify(AdminReviewAuthorization, review.ReviewVerify):
    pass


class Block(AdminReviewAuthorization, review.ReviewBlock):
    pass


class NativeVerify(AdminReviewAuthorization, review.ReviewNativeVerify):
    pass


class NativeBlock(AdminReviewAuthorization, review.ReviewNativeBlock):
    pass
