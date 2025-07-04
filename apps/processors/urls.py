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
    generate_scene_suggestions,
    save_draft,
    update_video_credentials,
get_processing_status_with_credentials,
get_voiceover_history,
update_video_history,
delete_all_clips,
get_saved_history,
split_subtitle,
merge_subtitles,
reorder_clips,
batch_update_clips,
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
    path('save-draft/', save_draft, name='save_draft'),  # Add this URL pattern
    path('videos/<int:video_id>/update-credentials/', update_video_credentials, name='update_video_credentials'),
    path('videos/<int:video_id>/processing-status/', get_processing_status_with_credentials, name='get_processing_status_with_credentials'),
    path('videos/<int:video_id>/voiceover-history/', get_voiceover_history, name='get_voiceover_history'),  # Add this URL pattern
    path('videos/<int:video_id>/saved-history/', get_saved_history, name='get_voiceover_history'),  # Add this URL pattern
    path('update-video-history/', update_video_history, name='update_video_history'),
    # Add this to your urlpatterns
path('delete-all-clips/', delete_all_clips, name='delete_all_clips'),


  path('split-subtitle/', split_subtitle, name='split_subtitle'),
    path('merge-subtitles/', merge_subtitles, name='merge_subtitles'),
    path('reorder-clips/', reorder_clips, name='reorder_clips'),
    path('batch-update-clips/', batch_update_clips, name='batch_update_clips'),
]
