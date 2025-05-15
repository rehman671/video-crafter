from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    # BackgroundMusicViewSet, 
    # upload_background_music,
    add_music_from_url,
    delete_clip,
    update_clip,
    handle_clip_assignment,
    save_slides_data,  # Add this import
    background_music_view,  # Add this import
    recent_videos_view,
    process_video_view,  # Add this import
    start_video_processing,  # Add this import
    get_processing_status,  # Add this import
    delete_background_music,  # Add this import
    generate_scene_suggestions
)

# router = DefaultRouter()
# router.register(r'background-music', BackgroundMusicViewSet, basename='background-music')

urlpatterns = [
    # path('', include(router.urls)),
    # path('upload-background-music/', upload_background_music, name='upload-background-music'),
    # path('add-music-from-url/', add_music_from_url, name='add-music-from-url'),
    path('delete-clip/', delete_clip, name='delete-clip'),
    path('update-clip/', update_clip, name='update-clip'),
    path('handle-clip-assignment/', handle_clip_assignment, name='handle-clip-assignment'),
    path('save-slides-data/', save_slides_data, name='save-slides-data'),  # Add this URL pattern
    path('background-music/<int:video_id>/', background_music_view, name='background_music'),  # Add this URL pattern
    path('recent-videos/', recent_videos_view, name='recent_videos'),  # Add this URL pattern
    path('process-video/<int:video_id>/', process_video_view, name='process_video'),  # Add this URL pattern
    path('videos/<int:video_id>/process-video/', start_video_processing, name='start_video_processing'),  # Add this URL pattern
    path('videos/<int:video_id>/processing-status/', get_processing_status, name='get_processing_status'),  # Add this URL pattern
    path('delete-background-music/', delete_background_music, name='delete_background_music'),  # Add this URL pattern
    path('generate-scene-suggestions/', generate_scene_suggestions, name='generate_scene_suggestions'),  # Add this URL pattern
]
