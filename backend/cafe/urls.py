from django.urls import path
from backend.recommendation import api
from backend.recommendation import youtube_review_api as review
from backend.recommendation.youtube_queue_api import YoutubeQueue

urlpatterns = [
    path('api/youtube-review/status',review.ReviewStatus.as_view()),
    path('api/youtube-review/tracks',review.ReviewTracks.as_view()),
    path('api/youtube-review/mappings',review.ReviewMappings.as_view()),
    path('api/youtube-review/import',review.ReviewImport.as_view()),
    path('api/youtube-review/verify',review.ReviewVerify.as_view()),
    path('api/youtube-review/native-verify',review.ReviewNativeVerify.as_view()),
    path('api/youtube-review/native-block',review.ReviewNativeBlock.as_view()),
    path('api/youtube-review/block',review.ReviewBlock.as_view()),
    path('api/c-demo/context',api.DemoContext.as_view()),
    path('api/recommendation-options',api.Options.as_view()),
    path('api/weather',api.Weather.as_view()),
    path('api/recommendation-jobs',api.Jobs.as_view()),
    path('api/recommendation-jobs/<str:pk>',api.JobDetail.as_view()),
    path('api/playlists/<str:pk>',api.PlaylistDetail.as_view()),
    path('api/playlists/<str:pk>/youtube-playback',api.YoutubePlayback.as_view()),
    path('api/playlists/<str:pk>/youtube-queue',YoutubeQueue.as_view()),
    path('api/playlists/<str:pk>/regenerations',api.Regenerate.as_view()),
    path('api/playlists/<str:pk>/approval',api.Approve.as_view()),
    path('api/playlists/<str:pk>/feedback',api.Feedback.as_view()),
    path('api/playlists/<str:pk>/tracks/<str:track_id>/reaction',api.TrackReaction.as_view()),
    path('api/playlists/<str:pk>/rating',api.PlaylistRating.as_view()),
    path('api/playlist-families/<str:pk>/exclusions',api.Exclusions.as_view()),
]
