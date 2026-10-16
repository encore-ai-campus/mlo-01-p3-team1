from django.urls import path
from backend.recommendation import api

urlpatterns = [
    path('api/c-demo/context',api.DemoContext.as_view()),
    path('api/recommendation-options',api.Options.as_view()),
    path('api/weather',api.Weather.as_view()),
    path('api/recommendation-jobs',api.Jobs.as_view()),
    path('api/recommendation-jobs/<str:pk>',api.JobDetail.as_view()),
    path('api/playlists/<str:pk>',api.PlaylistDetail.as_view()),
    path('api/playlists/<str:pk>/regenerations',api.Regenerate.as_view()),
    path('api/playlists/<str:pk>/approval',api.Approve.as_view()),
    path('api/playlists/<str:pk>/feedback',api.Feedback.as_view()),
    path('api/playlists/<str:pk>/tracks/<str:track_id>/reaction',api.TrackReaction.as_view()),
    path('api/playlists/<str:pk>/rating',api.PlaylistRating.as_view()),
    path('api/playlist-families/<str:pk>/exclusions',api.Exclusions.as_view()),
]
