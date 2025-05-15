import os
import uuid
import threading
from django.conf import settings
from django.shortcuts import render, get_object_or_404, redirect
from rest_framework import viewsets, status
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from django.db.models import F
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
import json
from .models import BackgroundMusic, Video, Clips, Subclip, BackgroundMusic, ProcessingStatus
from .serializers import BackgroundMusicSerializer
from .utils import add_background_music, generate_audio_file, generate_srt_file, generate_clips_from_srt, generate_final_video, update_clip_timings, generate_signed_url
from apps.processors.services.video_processor import VideoProcessorService
from apps.core.models import Subscription

import traceback
from apps.core.models import UserAsset
from apps.core.services.s3_service import get_s3_client

import tempfile
from django.core.files import File
import time
from .handler.openai import OpenAIHandler
import logging
from django.db.models.signals import pre_save, post_save
from .signals import configure_subclip
logger = logging.getLogger(__name__)

class BackgroundMusicViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing background music
    """
    serializer_class = BackgroundMusicSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """
        Return background music tracks for the authenticated user's videos
        """
        video_id = self.request.query_params.get('video_id')
        queryset = BackgroundMusic.objects.filter(video__user=self.request.user)
        
        if video_id:
            queryset = queryset.filter(video_id=video_id)
            
        return queryset
    
    def perform_create(self, serializer):
        # Ensure the video belongs to the authenticated user
        video_id = self.request.data.get('video')
        video = get_object_or_404(Video, id=video_id, user=self.request.user)
        serializer.save(video=video)
    
    def perform_update(self, serializer):
        # Ensure the video belongs to the authenticated user
        instance = self.get_object()
        if instance.video.user != self.request.user:
            raise PermissionError("You don't have permission to modify this music track")
        serializer.save()

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
@login_required(login_url='login')
def upload_background_music(request):
    """
    Upload background music for a video
    
    Request parameters:
    - video_id: ID of the video
    - music_file: Music file to upload
    - start_time: Start time in seconds (default: 0)
    - end_time: End time in seconds (optional)
    """
    video_id = request.data.get('video_id')
    music_file = request.FILES.get('music_file')
    start_time = float(request.data.get('start_time', 0))
    end_time = request.data.get('end_time')
    
    if end_time:
        end_time = float(end_time)
    
    # Validate input
    if not video_id:
        return Response({'error': 'Video ID is required'}, status=status.HTTP_400_BAD_REQUEST)
    
    if not music_file:
        return Response({'error': 'Music file is required'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Get video
    try:
        video = Video.objects.get(id=video_id, user=request.user)
    except Video.DoesNotExist:
        return Response({'error': 'Video not found'}, status=status.HTTP_404_NOT_FOUND)
    
    # Add background music
    bg_music = add_background_music(
        video=video,
        music_file=music_file,
        start_time=start_time,
        end_time=end_time
    )
    
    if bg_music:
        serializer = BackgroundMusicSerializer(bg_music)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    else:
        return Response({'error': 'Failed to add background music'}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@login_required(login_url='login')
def add_music_from_url(request):
    """
    Add background music from a URL
    
    Request parameters:
    - video_id: ID of the video
    - music_url: URL to download music from
    - start_time: Start time in seconds (default: 0)
    - end_time: End time in seconds (optional)
    """
    video_id = request.data.get('video_id')
    music_url = request.data.get('music_url')
    start_time = float(request.data.get('start_time', 0))
    end_time = request.data.get('end_time')
    
    if end_time:
        end_time = float(end_time)
    
    # Validate input
    if not video_id:
        return Response({'error': 'Video ID is required'}, status=status.HTTP_400_BAD_REQUEST)
    
    if not music_url:
        return Response({'error': 'Music URL is required'}, status=status.HTTP_400_BAD_REQUEST)
    
    # Get video
    try:
        video = Video.objects.get(id=video_id, user=request.user)
    except Video.DoesNotExist:
        return Response({'error': 'Video not found'}, status=status.HTTP_404_NOT_FOUND)
    
    # Add background music
    bg_music = add_background_music(
        video=video,
        music_url=music_url,
        start_time=start_time,
        end_time=end_time
    )
    
    if bg_music:
        serializer = BackgroundMusicSerializer(bg_music)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    else:
        return Response({'error': 'Failed to add background music'}, status=status.HTTP_400_BAD_REQUEST)

@csrf_exempt
@require_POST
@login_required(login_url='login')
def delete_clip(request):
    """
    Delete a clip based on the provided clip ID
    """
    try:
        data = json.loads(request.body)
        clip_id = data.get('clip_id')
        
        # Validate input
        if not clip_id:
            return JsonResponse({'success': False, 'error': 'Clip ID is required'}, status=400)        
        try:
            clip = Clips.objects.get(id=clip_id, video__user=request.user)
            clip.delete()
            return JsonResponse({'success': True, 'message': 'Clip deleted successfully'})
        except Clips.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Clip not found'}, status=404)
            
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@csrf_exempt
@require_POST
@login_required(login_url='login')
def update_clip(request):
    """
    Update or create a clip based on data from the frontend
    """
    try:
        # Parse the JSON data
        data = json.loads(request.body)
        clip_id = data.get('clip_id')
        text = data.get('text')
        video_id = data.get('video_id')
        sequence = data.get('sequence')  # Get sequence number from request
        
        # Validate input
        if not text or not video_id:
            return JsonResponse({'success': False, 'error': 'Missing required fields'}, status=400)
        
        # Get the video object
        try:
            video = Video.objects.get(id=video_id, user=request.user)
        except Video.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Video not found'}, status=404)
        
        # If clip_id is negative, create a new clip
        if clip_id < 0:
            # Use the provided sequence number or get the highest sequence number for ordering
            if sequence is None:
                highest_sequence = Clips.objects.filter(video=video).order_by('-sequence').first()
                sequence = (highest_sequence.sequence + 1) if highest_sequence else 1
            
            # Default values for time fields
            clip = Clips.objects.create(
                video=video,
                text=text,
                start_time=0.0,  # Default start time
                end_time=5.0,    # Default end time
                sequence=sequence
            )
            return JsonResponse({
                'success': True, 
                'message': 'New clip created successfully',
                'clip_id': clip.id
            })
        else:
            # Update existing clip
            try:
                clip = Clips.objects.get(id=clip_id, video=video)
                clip.text = text
                if sequence is not None:  # Update sequence if provided
                    clip.sequence = sequence
                clip.start_time=0 # Default start time
                clip.end_time=5 # Default end time
                clip.save()
                return JsonResponse({
                    'success': True, 
                    'message': 'Clip updated successfully'
                })
            except Clips.DoesNotExist:
                return JsonResponse({'success': False, 'error': 'Clip not found'}, status=404)
                
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

# @csrf_exempt
# @login_required(login_url='login')
# def background_music_view(request, video_id):
#     """
#     View to handle background music for a specific video
#     """
#     try:
#         video = Video.objects.get(id=video_id, user=request.user)
#         # Get all background music associated with this video
#         video.output_with_bg = video.output
#         video.output_with_bg_watermark = video.output_with_watermark
#         video.save()
#         background_music = BackgroundMusic.objects.filter(video=video)
        
#         # Process file names for each background music object
#         for music in background_music:
#             if music.audio_file:
#                 # Extract the filename from the full path
#                 music.file_name = os.path.basename(music.audio_file.name)
#             else:
#                 music.file_name = "No file"
        
#         # Generate a signed URL for direct access to the video in S3
#         video_url = None
#         if video.output and video.output.name:
#             # Generate a signed URL that's valid for 2 hours
#             video_url = generate_signed_url(video.output_with_watermark.name, expires_in=7200)
            
#             if video_url:
#                 print(f"Successfully generated signed URL for video: {video_url}")
#             else:
#                 # Fall back to the regular URL if signed URL generation fails
#                 video_url = video.output.url
#                 print(f"Failed to generate signed URL, falling back to: {video_url}")
#         else:
#             print(f"Video has no output file. Video ID: {video.id}")
        
#     # Handle POST request for background music
#         if request.method == 'POST':
#             print("==== Background Music Form Data ====")
#             print(f"Video ID: {video_id}")
            
#             # Get music form data
#             music_tracks = []
            
#             # Loop through possible music tracks (dynamic number)
#             i = 1
#             while f'bg_music_{i}' in request.FILES:
#                 # Get time values in format like "00:00"
#                 from_when_str = request.POST.get(f'from_when_{i}', '00:00')
#                 to_when_str = request.POST.get(f'to_when_{i}', '')
                
#                 # Convert time strings to seconds
#                 start_seconds = 0
#                 if from_when_str:
#                     parts = from_when_str.split(':')
#                     if len(parts) == 2:
#                         start_seconds = int(parts[0]) * 60 + int(parts[1])
                    
#                 end_seconds = None
#                 if to_when_str:
#                     parts = to_when_str.split(':')
#                     if len(parts) == 2:
#                         end_seconds = int(parts[0]) * 60 + int(parts[1])
                    
#                 music_tracks.append({
#                     'file': request.FILES[f'bg_music_{i}'],
#                     'from_when': start_seconds,
#                     'to_when': end_seconds,
#                     'bg_level': request.POST.get(f'bg_level_{i}', '50')
#                 })
#                 print(f"Music Track {i}:")
#                 print(f"  - File: {request.FILES[f'bg_music_{i}'].name}")
#                 print(f"  - From: {from_when_str} ({start_seconds} seconds)")
#                 print(f"  - To: {to_when_str} ({end_seconds} seconds)")
#                 print(f"  - Level: {request.POST.get(f'bg_level_{i}', '50')}%")
#                 i += 1
                
#             # Process each music track
#             for track in music_tracks:
#                 bg_music = BackgroundMusic.objects.create(
#                     video=video,
#                     audio_file=track['file'],
#                     start_time=track['from_when'],
#                     end_time=track['to_when'],
#                     volumn=float(track['bg_level'])/100
#                 )
#                 video_processor = VideoProcessorService(video)
#                 result = video_processor.apply_background_music(bg_music)
#                 result = video_processor.apply_background_music_watermark(bg_music)
#                 if bg_music:
#                     print(f"Added background music: {bg_music}")
#                 else:
#                     print(f"Failed to add background music")

#             return redirect('download_video', video_id=video.id)
    
#         return render(request, 'home/background-music.html', {
#             'video': video,
#             'background_music': background_music,
#             "user_subscription": request.user.subscription,
#             "video_url": video_url,
#         })
#     except Video.DoesNotExist:
#         return JsonResponse({'success': False, 'error': 'Video not found'}, status=404)


# 1. First, let's modify the Django view to handle updates to existing background music

# @csrf_exempt
# @login_required(login_url='login')
# def background_music_view(request, video_id):
#     """
#     View to handle background music for a specific video
#     """
#     try:
#         video = Video.objects.get(id=video_id, user=request.user)
#         # Get all background music associated with this video
#         # video.output_with_bg = video.output
#         # video.output_with_bg_watermark = video.output_with_watermark
#         # video.save()
#         background_music = BackgroundMusic.objects.filter(video=video)
        
#         # Process file names for each background music object
#         for music in background_music:
#             if music.audio_file:
#                 # Extract the filename from the full path
#                 music.file_name = os.path.basename(music.audio_file.name)
#             else:
#                 music.file_name = "No file"
        
#         # Generate a signed URL for direct access to the video in S3
#         video_url = None
#         if video.output and video.output.name:
#             # Generate a signed URL that's valid for 2 hours
#             video_url = generate_signed_url(video.output_with_watermark.name, expires_in=7200)
            
#             if video_url:
#                 print(f"Successfully generated signed URL for video: {video_url}")
#             else:
#                 # Fall back to the regular URL if signed URL generation fails
#                 video_url = video.output.url
#                 print(f"Failed to generate signed URL, falling back to: {video_url}")
#         else:
#             print(f"Video has no output file. Video ID: {video.id}")
        
#         # Handle POST request for background music
#         if request.method == 'POST':
#             print("==== Background Music Form Data ====")
#             print(f"Video ID: {video_id}")
            
#             # Get music form data
#             music_tracks = []
#             existing_music_updates = {}
            
#             # Process form data
#             for key in request.POST:
#                 # Handle existing music updates
#                 if key.startswith('existing_music_'):
#                     parts = key.split('_')
#                     if len(parts) >= 3:
#                         music_id = parts[2]
#                         field_name = '_'.join(parts[3:])
                        
#                         if music_id not in existing_music_updates:
#                             existing_music_updates[music_id] = {}
                        
#                         existing_music_updates[music_id][field_name] = request.POST[key]
            
#             # Process updates to existing music tracks
#             for music_id, update_data in existing_music_updates.items():
#                 try:
#                     bg_music = BackgroundMusic.objects.get(id=music_id, video=video)
                    
#                     # Update the fields
#                     if 'from_when' in update_data:
#                         # Convert time strings to seconds
#                         from_when_str = update_data['from_when']
#                         start_seconds = 0
#                         if from_when_str:
#                             if from_when_str.find(':') != -1:
#                                 parts = from_when_str.split(':')
#                                 if len(parts) == 2:
#                                     start_seconds = int(parts[0]) * 60 + int(parts[1])
#                             else:
#                                 # Use the _seconds value if available
#                                 seconds_key = f"existing_music_{music_id}_from_when_seconds"
#                                 if seconds_key in request.POST:
#                                     start_seconds = int(request.POST[seconds_key])
#                                 else:
#                                     start_seconds = int(from_when_str)
                        
#                         bg_music.start_time = start_seconds
                    
#                     if 'to_when' in update_data:
#                         to_when_str = update_data['to_when']
#                         end_seconds = None
#                         if to_when_str:
#                             if to_when_str.find(':') != -1:
#                                 parts = to_when_str.split(':')
#                                 if len(parts) == 2:
#                                     end_seconds = int(parts[0]) * 60 + int(parts[1])
#                             else:
#                                 # Use the _seconds value if available
#                                 seconds_key = f"existing_music_{music_id}_to_when_seconds"
#                                 if seconds_key in request.POST:
#                                     end_seconds = int(request.POST[seconds_key])
#                                 else:
#                                     end_seconds = int(to_when_str)
                        
#                         bg_music.end_time = end_seconds
                    
#                     if 'bg_level' in update_data:
#                         bg_music.volumn = float(update_data['bg_level'])/100
                    
#                     # Save the updated music
#                     bg_music.save()
                    
#                     # Re-apply the background music
#                     video_processor = VideoProcessorService(video)
#                     result = video_processor.apply_background_music(bg_music)
#                     result = video_processor.apply_background_music_watermark(bg_music)
#                     print(f"Updated background music: {bg_music}")
                    
#                 except BackgroundMusic.DoesNotExist:
#                     print(f"Background music with ID {music_id} not found")
            
#             # Loop through possible new music tracks (dynamic number)
#             i = 1
#             while f'bg_music_{i}' in request.FILES:
#                 # Get time values in format like "00:00"
#                 from_when_str = request.POST.get(f'from_when_{i}', '00:00')
#                 to_when_str = request.POST.get(f'to_when_{i}', '')
                
#                 # Convert time strings to seconds
#                 start_seconds = 0
#                 if from_when_str:
#                     # If there's a _seconds field, use that
#                     seconds_key = f"from_when_{i}_seconds"
#                     if seconds_key in request.POST:
#                         start_seconds = int(request.POST[seconds_key])
#                     else:
#                         # Otherwise parse the time string
#                         if from_when_str.find(':') != -1:
#                             parts = from_when_str.split(':')
#                             if len(parts) == 2:
#                                 start_seconds = int(parts[0]) * 60 + int(parts[1])
#                         else:
#                             start_seconds = int(from_when_str)
                    
#                 end_seconds = None
#                 if to_when_str:
#                     # If there's a _seconds field, use that
#                     seconds_key = f"to_when_{i}_seconds"
#                     if seconds_key in request.POST:
#                         end_seconds = int(request.POST[seconds_key])
#                     else:
#                         # Otherwise parse the time string
#                         if to_when_str.find(':') != -1:
#                             parts = to_when_str.split(':')
#                             if len(parts) == 2:
#                                 end_seconds = int(parts[0]) * 60 + int(parts[1])
#                         else:
#                             end_seconds = int(to_when_str)
                    
#                 music_tracks.append({
#                     'file': request.FILES[f'bg_music_{i}'],
#                     'from_when': start_seconds,
#                     'to_when': end_seconds,
#                     'bg_level': request.POST.get(f'bg_level_{i}', '50')
#                 })
#                 print(f"Music Track {i}:")
#                 print(f"  - File: {request.FILES[f'bg_music_{i}'].name}")
#                 print(f"  - From: {from_when_str} ({start_seconds} seconds)")
#                 print(f"  - To: {to_when_str} ({end_seconds} seconds)")
#                 print(f"  - Level: {request.POST.get(f'bg_level_{i}', '50')}%")
#                 i += 1
                
#             # Process each new music track
#             for track in music_tracks:
#                 bg_music = BackgroundMusic.objects.create(
#                     video=video,
#                     audio_file=track['file'],
#                     start_time=track['from_when'],
#                     end_time=track['to_when'],
#                     volumn=float(track['bg_level'])/100
#                 )
#                 video_processor = VideoProcessorService(video)
#                 result = video_processor.apply_background_music(bg_music)
#                 result = video_processor.apply_background_music_watermark(bg_music)
#                 if bg_music:
#                     print(f"Added background music: {bg_music}")
#                 else:
#                     print(f"Failed to add background music")

#             return redirect('download_video', video_id=video.id)
    
#         return render(request, 'home/background-music.html', {
#             'video': video,
#             'background_music': background_music,
#             "user_subscription": request.user.subscription,
#             "video_url": video_url,
#         })
#     except Video.DoesNotExist:
#         return JsonResponse({'success': False, 'error': 'Video not found'}, status=404)
# @csrf_exempt
# @login_required(login_url='login')
# def background_music_view(request, video_id):
#     """
#     View to handle background music for a specific video
#     """
#     try:
#         video = Video.objects.get(id=video_id, user=request.user)
#         # Get all background music associated with this video
#         background_music = BackgroundMusic.objects.filter(video=video)
        
#         # Process file names for each background music object
#         for music in background_music:
#             if music.audio_file:
#                 # Extract the filename from the full path
#                 music.file_name = os.path.basename(music.audio_file.name)
#             else:
#                 music.file_name = "No file"
        
#         # Generate a signed URL for direct access to the video in S3
#         video_url = None
#         if video.output and video.output.name:
#             # Generate a signed URL that's valid for 2 hours
#             video_url = generate_signed_url(video.output_with_watermark.name, expires_in=7200)
            
#             if video_url:
#                 print(f"Successfully generated signed URL for video: {video_url}")
#             else:
#                 # Fall back to the regular URL if signed URL generation fails
#                 video_url = video.output.url
#                 print(f"Failed to generate signed URL, falling back to: {video_url}")
#         else:
#             print(f"Video has no output file. Video ID: {video.id}")
        
#         # Handle POST request for background music
#         if request.method == 'POST':
#             print("==== Background Music Form Data ====")
#             print(f"Video ID: {video_id}")
            
#             # Track existing music IDs to identify which ones were removed
#             existing_music_ids = set(background_music.values_list('id', flat=True))
#             processed_music_ids = set()
            
#             # Process existing music tracks updates
#             for key in request.POST:
#                 print(f"Processing key: {key}")
#                 print(f"Value: {request.POST[key]}")
#                 if key.startswith('existing_music_') and '_id' in key:
#                     try:
#                         music_id = request.POST[key]
#                         processed_music_ids.add(int(music_id))
                        
#                         bg_music = BackgroundMusic.objects.get(id=music_id, video=video)
                        
#                         # Get the base name for this music's form fields
#                         base_name = f'existing_music_{music_id}'
                        
#                         # Update start time
#                         from_when_key = f'{base_name}_from_when'
#                         if from_when_key in request.POST:
#                             from_when_str = request.POST[from_when_key]
#                             start_seconds = 0
                            
#                             # Try to get value from _seconds field first
#                             seconds_key = f'{from_when_key}_seconds'
#                             if seconds_key in request.POST and request.POST[seconds_key]:
#                                 start_seconds = int(request.POST[seconds_key])
#                             # Otherwise parse from MM:SS format
#                             elif from_when_str:
#                                 if ':' in from_when_str:
#                                     parts = from_when_str.split(':')
#                                     if len(parts) == 2:
#                                         start_seconds = int(parts[0]) * 60 + int(parts[1])
#                                 else:
#                                     start_seconds = int(from_when_str)
                            
#                             bg_music.start_time = start_seconds
                        
#                         # Update end time
#                         to_when_key = f'{base_name}_to_when'
#                         if to_when_key in request.POST:
#                             to_when_str = request.POST[to_when_key]
#                             end_seconds = None
                            
#                             # Try to get value from _seconds field first
#                             seconds_key = f'{to_when_key}_seconds'
#                             if seconds_key in request.POST and request.POST[seconds_key]:
#                                 end_seconds = int(request.POST[seconds_key])
#                             # Otherwise parse from MM:SS format
#                             elif to_when_str:
#                                 if ':' in to_when_str:
#                                     parts = to_when_str.split(':')
#                                     if len(parts) == 2:
#                                         end_seconds = int(parts[0]) * 60 + int(parts[1])
#                                 else:
#                                     end_seconds = int(to_when_str)
                            
#                             bg_music.end_time = end_seconds
                        
#                         # Update volume level
#                         bg_level_key = f'{base_name}_bg_level'
#                         if bg_level_key in request.POST:
#                             bg_music.volumn = float(request.POST[bg_level_key])/100
                        
#                         # Check if a new file was uploaded for this existing music
#                         file_key = f'{base_name}_file'
#                         if file_key in request.FILES:
#                             bg_music.audio_file = request.FILES[file_key]
                        
#                         # Save the updated music
#                         bg_music.save()
                        
#                         # Re-apply the background music - UNCOMMENTED
#                         # video_processor = VideoProcessorService(video)
#                         # result = video_processor.apply_background_music(bg_music)
#                         # result = video_processor.apply_background_music_watermark(bg_music)
#                         print(f"Updated background music: {bg_music}")
                        
#                     except (BackgroundMusic.DoesNotExist, ValueError) as e:
#                         print(f"Error updating background music: {e}")
            
#             # Delete music tracks that were removed in the frontend - UNCOMMENTED
#             music_to_delete = existing_music_ids - processed_music_ids
#             if music_to_delete:
#                 BackgroundMusic.objects.filter(id__in=music_to_delete).delete()
#                 print(f"Deleted background music IDs: {music_to_delete}")
            
#             # Process new music tracks
#             i = 1
#             # Check for new form fields with patterns like bg_music_1, bg_music_2, etc.
#             while i <= 10:  # Assuming a maximum of 10 new music tracks
#                 if f'bg_music_{i}' in request.POST or f'bg_music_{i}' in request.FILES:
#                     # Get time values in format like "00:00"
#                     from_when_str = request.POST.get(f'from_when_{i}', '00:00')
#                     to_when_str = request.POST.get(f'to_when_{i}', '')
                    
#                     # Convert time strings to seconds
#                     start_seconds = 0
#                     if from_when_str:
#                         # If there's a _seconds field, use that
#                         seconds_key = f"from_when_{i}_seconds"
#                         if seconds_key in request.POST and request.POST[seconds_key]:
#                             start_seconds = int(request.POST[seconds_key])
#                         else:
#                             # Otherwise parse the time string
#                             if ':' in from_when_str:
#                                 parts = from_when_str.split(':')
#                                 if len(parts) == 2:
#                                     start_seconds = int(parts[0]) * 60 + int(parts[1])
#                             else:
#                                 try:
#                                     start_seconds = int(from_when_str)
#                                 except ValueError:
#                                     start_seconds = 0
                        
#                     end_seconds = None
#                     if to_when_str:
#                         # If there's a _seconds field, use that
#                         seconds_key = f"to_when_{i}_seconds"
#                         if seconds_key in request.POST and request.POST[seconds_key]:
#                             end_seconds = int(request.POST[seconds_key])
#                         else:
#                             # Otherwise parse the time string
#                             if ':' in to_when_str:
#                                 parts = to_when_str.split(':')
#                                 if len(parts) == 2:
#                                     end_seconds = int(parts[0]) * 60 + int(parts[1])
#                             else:
#                                 try:
#                                     end_seconds = int(to_when_str)
#                                 except ValueError:
#                                     end_seconds = None
                    
#                     # Get volume level
#                     bg_level = request.POST.get(f'bg_level_{i}', '50')
                    
#                     # Create new background music - handle both cases with and without file
#                     if f'bg_music_{i}' in request.FILES:
#                         # Create with uploaded file
#                         bg_music = BackgroundMusic.objects.create(
#                             video=video,
#                             audio_file=request.FILES[f'bg_music_{i}'],
#                             start_time=start_seconds,
#                             end_time=end_seconds,
#                             volumn=float(bg_level)/100
#                         )
#                     elif f'bg_music_{i}' in request.POST:
#                         # Create without file (empty audio_file)
#                         bg_music = BackgroundMusic.objects.create(
#                             video=video,
#                             start_time=start_seconds,
#                             end_time=end_seconds,
#                             volumn=float(bg_level)/100
#                         )
                    
#                     # Apply the new background music if a file was provided
#                     if f'bg_music_{i}' in request.FILES:
#                         video_processor = VideoProcessorService(video)
#                         result = video_processor.apply_background_music(bg_music)
#                         result = video_processor.apply_background_music_watermark(bg_music)
                    
#                     print(f"Added new background music: {bg_music}")
#                 i += 1

#             return redirect('download_video', video_id=video.id)
    
#         return render(request, 'home/background-music.html', {
#             'video': video,
#             'background_music': background_music,
#             "user_subscription": request.user.subscription,
#             "video_url": video_url,
#         })
#     except Video.DoesNotExist:
#         return JsonResponse({'success': False, 'error': 'Video not found'}, status=404)

@csrf_exempt
@login_required(login_url='login')
def background_music_view(request, video_id):
    """
    View to handle background music for a specific video
    """
    try:
        video = Video.objects.get(id=video_id, user=request.user)
        # Get all background music associated with this video
        background_music = BackgroundMusic.objects.filter(video=video)
        
        # Process file names for each background music object
        for music in background_music:
            if music.audio_file:
                # Extract the filename from the full path
                music.file_name = os.path.basename(music.audio_file.name)
            else:
                music.file_name = "No file"
        
        # Generate a signed URL for direct access to the video in S3
        video_url = None
        if video.output and video.output.name:
            # Generate a signed URL that's valid for 2 hours
            video_url = generate_signed_url(video.output_with_watermark.name, expires_in=7200)
            
            if video_url:
                print(f"Successfully generated signed URL for video: {video_url}")
            else:
                # Fall back to the regular URL if signed URL generation fails
                video_url = video.output.url
                print(f"Failed to generate signed URL, falling back to: {video_url}")
        else:
            print(f"Video has no output file. Video ID: {video.id}")
        
        # Handle POST request for background music
        if request.method == 'POST':
            print("==== Background Music Form Data ====")
            print(f"Video ID: {video_id}")
            
            # Track existing music IDs to identify which ones were removed
            existing_music_ids = set(background_music.values_list('id', flat=True))
            processed_music_ids = set()
            
            # Process existing music tracks updates
            for key in request.POST:
                print(f"Processing key: {key}")
                print(f"Value: {request.POST[key]}")
                if key.startswith('existing_music_') and '_id' in key:
                    try:
                        music_id = request.POST[key]
                        processed_music_ids.add(int(music_id))
                        
                        bg_music = BackgroundMusic.objects.get(id=music_id, video=video)
                        
                        # Get the base name for this music's form fields
                        base_name = f'existing_music_{music_id}'
                        
                        # Update start time
                        from_when_key = f'{base_name}_from_when'
                        if from_when_key in request.POST:
                            from_when_str = request.POST[from_when_key]
                            start_seconds = 0
                            
                            # Try to get value from _seconds field first
                            seconds_key = f'{from_when_key}_seconds'
                            if seconds_key in request.POST and request.POST[seconds_key]:
                                start_seconds = int(request.POST[seconds_key])
                            # Otherwise parse from MM:SS format
                            elif from_when_str:
                                if ':' in from_when_str:
                                    parts = from_when_str.split(':')
                                    if len(parts) == 2:
                                        start_seconds = int(parts[0]) * 60 + int(parts[1])
                                else:
                                    start_seconds = int(from_when_str)
                            
                            bg_music.start_time = start_seconds
                        
                        # Update end time
                        to_when_key = f'{base_name}_to_when'
                        if to_when_key in request.POST:
                            to_when_str = request.POST[to_when_key]
                            end_seconds = None
                            
                            # Try to get value from _seconds field first
                            seconds_key = f'{to_when_key}_seconds'
                            if seconds_key in request.POST and request.POST[seconds_key]:
                                end_seconds = int(request.POST[seconds_key])
                            # Otherwise parse from MM:SS format
                            elif to_when_str:
                                if ':' in to_when_str:
                                    parts = to_when_str.split(':')
                                    if len(parts) == 2:
                                        end_seconds = int(parts[0]) * 60 + int(parts[1])
                                else:
                                    end_seconds = int(to_when_str)
                            
                            # Set a default end_time if empty to satisfy NOT NULL constraint
                            if end_seconds is None:
                                end_seconds = 0  # Or any default value that makes sense for your application
                                
                            bg_music.end_time = end_seconds
                        
                        # Update volume level
                        bg_level_key = f'{base_name}_bg_level'
                        if bg_level_key in request.POST:
                            bg_music.volumn = float(request.POST[bg_level_key])/100
                          # Check if a new file was uploaded for this existing music                      
                        file_key = f'{base_name}_file'
                        if file_key in request.FILES:
                            print(f"Updating file for existing music {music_id} with new file {request.FILES[file_key].name}")
                            # Delete the old file first if it exists
                            if bg_music.audio_file:
                                try:
                                    storage = bg_music.audio_file.storage
                                    if storage.exists(bg_music.audio_file.name):
                                        storage.delete(bg_music.audio_file.name)
                                except Exception as e:
                                    print(f"Error deleting old file: {e}")
                            
                            # Now assign the new file
                            bg_music.audio_file = request.FILES[file_key]
                        
                        # Save the updated music
                        bg_music.save()
                        
                        # # Re-apply the background music
                        # video_processor = VideoProcessorService(video)
                        # result = video_processor.apply_background_music(bg_music)
                        # result = video_processor.apply_background_music_watermark(bg_music)
                        print(f"Updated background music: {bg_music}")
                    except (BackgroundMusic.DoesNotExist, ValueError) as e:
                        print(f"Error updating background music: {e}")
            
            # Delete music tracks that were removed in the frontend - UNCOMMENTED
            music_to_delete = existing_music_ids - processed_music_ids
            if music_to_delete:
                BackgroundMusic.objects.filter(id__in=music_to_delete).delete()
                print(f"Deleted background music IDs: {music_to_delete}")
            
            # Process new music tracks
            i = 1
            # Check for new form fields with patterns like bg_music_1, bg_music_2, etc.
            while i <= 10:  # Assuming a maximum of 10 new music tracks                    # For new track creation - only process if there's no existing track reference
                    existing_id_key = f'existing_music_{i}_id'
                    if not request.POST.get(existing_id_key) and (f'bg_music_{i}' in request.FILES or (f'bg_music_{i}' in request.POST and request.POST[f'bg_music_{i}'].strip())):
                        # Get time values in format like "00:00" 
                        from_when_str = request.POST.get(f'from_when_{i}', '00:00')
                        to_when_str = request.POST.get(f'to_when_{i}', '')
                        
                        # Convert time strings to seconds
                        start_seconds = 0
                        if from_when_str:
                            # If there's a _seconds field, use that
                            seconds_key = f"from_when_{i}_seconds"
                        if seconds_key in request.POST and request.POST[seconds_key]:
                            start_seconds = int(request.POST[seconds_key])
                        else:
                            # Otherwise parse the time string
                            if ':' in from_when_str:
                                parts = from_when_str.split(':')
                                if len(parts) == 2:
                                    start_seconds = int(parts[0]) * 60 + int(parts[1])
                            else:
                                try:
                                    start_seconds = int(from_when_str)
                                except ValueError:
                                    start_seconds = 0
                        
                    # Set a default end_time to prevent NOT NULL constraint violation
                    end_seconds = 0  # Default value
                    if to_when_str:
                        # If there's a _seconds field, use that
                        seconds_key = f"to_when_{i}_seconds"
                        if seconds_key in request.POST and request.POST[seconds_key]:
                            end_seconds = int(request.POST[seconds_key])
                        else:
                            # Otherwise parse the time string
                            if ':' in to_when_str:
                                parts = to_when_str.split(':')
                                if len(parts) == 2:
                                    end_seconds = int(parts[0]) * 60 + int(parts[1])
                            else:
                                try:
                                    end_seconds = int(to_when_str)
                                except ValueError:
                                    end_seconds = 0  # Default to 0 instead of None
                    
                    # Get volume level
                    bg_level = request.POST.get(f'bg_level_{i}', '50')
                    
                    # Create new background music only if we have a file
                    if f'bg_music_{i}' in request.FILES:
                        # Create with uploaded file
                        bg_music = BackgroundMusic.objects.create(
                            video=video,
                            audio_file=request.FILES[f'bg_music_{i}'],
                            start_time=start_seconds,
                            end_time=end_seconds,  # This will never be None now
                            volumn=float(bg_level)/100
                        )
                        
                        # Apply the new background music
                        # video_processor = VideoProcessorService(video)
                        # result = video_processor.apply_background_music(bg_music)
                        # result = video_processor.apply_background_music_watermark(bg_music)
                        
                        print(f"Added new background music: {bg_music}")
                    i += 1

            return redirect('download_video', video_id=video.id)
    
        return render(request, 'home/background-music.html', {
            'video': video,
            'background_music': background_music,
            "user_subscription": request.user.subscription,
            "video_url": video_url,
        })
    except Video.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Video not found'}, status=404)
# @login_required(login_url='login')
# def background_music_view(request, video_id):
#     """
#     View to handle background music for a specific video
#     """
#     try:
#         video = Video.objects.get(id=video_id, user=request.user)
#         # Get all background music associated with this video
#         background_music = BackgroundMusic.objects.filter(video=video)
        
#         # Process file names for each background music object
#         for music in background_music:
#             if music.audio_file:
#                 # Extract the filename from the full path
#                 music.file_name = os.path.basename(music.audio_file.name)
#             else:
#                 music.file_name = "No file"
        
#         # Generate a signed URL for direct access to the video in S3
#         video_url = None
#         if video.output and video.output.name:
#             # Generate a signed URL that's valid for 2 hours
#             video_url = generate_signed_url(video.output_with_watermark.name, expires_in=7200)
            
#             if video_url:
#                 print(f"Successfully generated signed URL for video: {video_url}")
#             else:
#                 # Fall back to the regular URL if signed URL generation fails
#                 video_url = video.output.url
#                 print(f"Failed to generate signed URL, falling back to: {video_url}")
#         else:
#             print(f"Video has no output file. Video ID: {video.id}")
        
#         # Handle POST request for background music
#         if request.method == 'POST':
#             print("==== Background Music Form Data ====")
#             print(f"Video ID: {video_id}")
            
#             # Track existing music IDs to identify which ones were removed
#             existing_music_ids = set(background_music.values_list('id', flat=True))
#             processed_music_ids = set()
            
#             # Process existing music tracks updates
#             for key in request.POST:
#                 print(f"Processing key: {key}")
#                 print(f"Value: {request.POST[key]}")
#                 if key.startswith('existing_music_') and '_id' in key:
#                     try:
#                         music_id = request.POST[key]
#                         processed_music_ids.add(int(music_id))
                        
#                         bg_music = BackgroundMusic.objects.get(id=music_id, video=video)
                        
#                         # Get the base name for this music's form fields
#                         base_name = f'existing_music_{music_id}'
                        
#                         # Update start time
#                         from_when_key = f'{base_name}_from_when'
#                         if from_when_key in request.POST:
#                             from_when_str = request.POST[from_when_key]
#                             start_seconds = 0
                            
#                             # Try to get value from _seconds field first
#                             seconds_key = f'{from_when_key}_seconds'
#                             if seconds_key in request.POST and request.POST[seconds_key]:
#                                 start_seconds = int(request.POST[seconds_key])
#                             # Otherwise parse from MM:SS format
#                             elif from_when_str:
#                                 if ':' in from_when_str:
#                                     parts = from_when_str.split(':')
#                                     if len(parts) == 2:
#                                         start_seconds = int(parts[0]) * 60 + int(parts[1])
#                                 else:
#                                     start_seconds = int(from_when_str)
                            
#                             bg_music.start_time = start_seconds
                        
#                         # Update end time
#                         to_when_key = f'{base_name}_to_when'
#                         if to_when_key in request.POST:
#                             to_when_str = request.POST[to_when_key]
#                             end_seconds = None
                            
#                             # Try to get value from _seconds field first
#                             seconds_key = f'{to_when_key}_seconds'
#                             if seconds_key in request.POST and request.POST[seconds_key]:
#                                 end_seconds = int(request.POST[seconds_key])
#                             # Otherwise parse from MM:SS format
#                             elif to_when_str:
#                                 if ':' in to_when_str:
#                                     parts = to_when_str.split(':')
#                                     if len(parts) == 2:
#                                         end_seconds = int(parts[0]) * 60 + int(parts[1])
#                                 else:
#                                     end_seconds = int(to_when_str)
                            
#                             bg_music.end_time = end_seconds
                        
#                         # Update volume level
#                         bg_level_key = f'{base_name}_bg_level'
#                         if bg_level_key in request.POST:
#                             bg_music.volumn = float(request.POST[bg_level_key])/100
                        
#                         # Check if a new file was uploaded for this existing music
#                         file_key = f'{base_name}_file'
#                         if file_key in request.FILES:
#                             bg_music.audio_file = request.FILES[file_key]
                        
#                         # Save the updated music
#                         bg_music.save()
                        
#                         # Re-apply the background music
#                         # video_processor = VideoProcessorService(video)
#                         # result = video_processor.apply_background_music(bg_music)
#                         # result = video_processor.apply_background_music_watermark(bg_music)
#                         print(f"Updated background music: {bg_music}")
                        
#                     except (BackgroundMusic.DoesNotExist, ValueError) as e:
#                         print(f"Error updating background music: {e}")
            
#             # Delete music tracks that were removed in the frontend
#             # music_to_delete = existing_music_ids - processed_music_ids
#             # if music_to_delete:
#             #     BackgroundMusic.objects.filter(id__in=music_to_delete).delete()
#             #     print(f"Deleted background music IDs: {music_to_delete}")
            
#             # Process new music tracks
#             i = 1
#             while f'bg_music_{i}' in request.FILES:
#                 # Get time values in format like "00:00"
#                 from_when_str = request.POST.get(f'from_when_{i}', '00:00')
#                 to_when_str = request.POST.get(f'to_when_{i}', '')
                
#                 # Convert time strings to seconds
#                 start_seconds = 0
#                 if from_when_str:
#                     # If there's a _seconds field, use that
#                     seconds_key = f"from_when_{i}_seconds"
#                     if seconds_key in request.POST and request.POST[seconds_key]:
#                         start_seconds = int(request.POST[seconds_key])
#                     else:
#                         # Otherwise parse the time string
#                         if ':' in from_when_str:
#                             parts = from_when_str.split(':')
#                             if len(parts) == 2:
#                                 start_seconds = int(parts[0]) * 60 + int(parts[1])
#                         else:
#                             start_seconds = int(from_when_str)
                    
#                 end_seconds = None
#                 if to_when_str:
#                     # If there's a _seconds field, use that
#                     seconds_key = f"to_when_{i}_seconds"
#                     if seconds_key in request.POST and request.POST[seconds_key]:
#                         end_seconds = int(request.POST[seconds_key])
#                     else:
#                         # Otherwise parse the time string
#                         if ':' in to_when_str:
#                             parts = to_when_str.split(':')
#                             if len(parts) == 2:
#                                 end_seconds = int(parts[0]) * 60 + int(parts[1])
#                         else:
#                             end_seconds = int(to_when_str)
                
#                 # Create new background music
#                 bg_level = request.POST.get(f'bg_level_{i}', '50')
#                 bg_music = BackgroundMusic.objects.create(
#                     video=video,
#                     audio_file=request.FILES[f'bg_music_{i}'],
#                     start_time=start_seconds,
#                     end_time=end_seconds,
#                     volumn=float(bg_level)/100
#                 )
                
#                 # Apply the new background music
#                 # video_processor = VideoProcessorService(video)
#                 # result = video_processor.apply_background_music(bg_music)
#                 # result = video_processor.apply_background_music_watermark(bg_music)
                
#                 print(f"Added new background music: {bg_music}")
#                 i += 1

#             # If no background music exists after processing
#             if not BackgroundMusic.objects.filter(video=video).exists():
#                 video.output_with_bg = video.output
#                 video.output_with_bg_watermark = video.output_with_watermark
#                 video.save()

#             return redirect('download_video', video_id=video.id)
    
#         return render(request, 'home/background-music.html', {
#             'video': video,
#             'background_music': background_music,
#             "user_subscription": request.user.subscription,
#             "video_url": video_url,
#         })
#     except Video.DoesNotExist:
#         return JsonResponse({'success': False, 'error': 'Video not found'}, status=404)

@require_POST
@login_required(login_url='login')
def handle_clip_assignment(request):
    """
    API endpoint to handle clip assignment for text selections
    Accepts: selected text, clip ID, and uploaded video
    """
    try:
        # Handle multipart form data for file uploads
        if request.FILES and 'slide_file' in request.FILES:
            # Handle file upload
            video_file = request.FILES.get('slide_file')
            selected_text = request.POST.get('slide_text')
            clip_id = int(request.POST.get('clipId'))
            
            # Save the uploaded file
            if video_file:
                try:
                    clip = Clips.objects.get(id=clip_id)
                    # Create a unique filename
                    filename = f"subclip_{uuid.uuid4()}.{video_file.name.split('.')[-1]}"
                    
                    # Create or update the subclip
                    clip.is_changed = True
                    clip.save()
                    pre_save.disconnect(configure_subclip, sender=Subclip)
                    subclip, created = Subclip.objects.get_or_create(
                        clip=clip, 
                        text=selected_text,
                        defaults={
                            'start_time': 0.0,
                            'end_time': 5.0
                        }
                    )
                    # Save the file directly to the FileField - this handles storage automatically
                    subclip.video_file.save(filename, video_file, save=True)
                    pre_save.connect(configure_subclip, sender=Subclip)
    
                    return JsonResponse({
                        'success': True,
                        'message': 'Clip assigned successfully',
                        'file_url': subclip.video_file.url
                    })
                except Clips.DoesNotExist:
                    return JsonResponse({'success': False, 'error': 'Clip not found'}, status=404)
        else:
            # Handle JSON data for asset selection
            data = json.loads(request.body)
            selected_text = data.get('slide_text')
            clip_id = int(data.get('clipId'))
            asset_key = data.get('selected_video')
            
            if not all([selected_text, clip_id, asset_key]):
                return JsonResponse({'success': False, 'error': 'Missing required fields'}, status=400)
            
            try:
                clip = Clips.objects.get(id=clip_id)
                
                # Find the asset
                try:
                    # Find the asset
                    asset = UserAsset.objects.get(user=request.user, key=asset_key)
                    
                    # Create a temporary file to handle the transfer
                    import tempfile
                    from django.core.files import File
                    
                    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(asset.filename)[1]) as tmp:
                        # Download the asset from S3
                        s3_client = get_s3_client()
                        s3_client.download_fileobj(
                            settings.AWS_STORAGE_BUCKET_NAME, 
                            asset_key,
                            tmp
                        )
                        tmp_path = tmp.name
                    
                    # Create or update the subclip
                    subclip, created = Subclip.objects.get_or_create(
                        clip=clip, 
                        text=selected_text,
                        defaults={
                            'start_time': 0.0,
                            'end_time': 5.0
                        }
                    )
                    clip.is_changed = True
                    clip.save()
                    # Save the asset to the subclip's video_file field
                    # This works with any storage backend including S3
                    with open(tmp_path, 'rb') as f:
                        subclip.video_file.save(asset.filename, File(f))
                    
                    # Clean up the temp file
                    os.unlink(tmp_path)
                    
                    return JsonResponse({
                        'success': True,
                        'message': 'Clip assigned successfully',
                        'file_url': subclip.video_file.url
                    })
                    
                except UserAsset.DoesNotExist:
                    return JsonResponse(
                        {"success": False, "error": "Asset not found"},
                        status=404
                    )
                except Exception as e:
                    return JsonResponse(
                        {"success": False, "error": f"Error downloading asset: {str(e)}"},
                        status=500
                    )
                
            except Clips.DoesNotExist:
                return JsonResponse({'success': False, 'error': 'Clip not found'}, status=404)
            
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
    
@csrf_exempt
@require_POST
@login_required(login_url='login')
def save_slides_data(request):
    """
    Save all slides data before proceeding to background music selection
    """
    try:
        # Check if we have multipart form data
        if request.content_type and 'multipart/form-data' in request.content_type:
            # Get data from form data
            video_id = request.POST.get('video_id')
            slides_data = request.POST.get('slides_data')
            
            if slides_data:
                try:
                    slides = json.loads(slides_data)
                except json.JSONDecodeError:
                    return JsonResponse({'success': False, 'error': 'Invalid slides data format'}, status=400)
            else:
                return JsonResponse({'success': False, 'error': 'No slides data provided'}, status=400)
                
            # Process files that were uploaded
            file_uploads = {}
            for key in request.FILES:
                if key.startswith('file_'):
                    highlight_id = key.replace('file_', '')
                    file_uploads[highlight_id] = request.FILES[key]
                    
            print(f"Received {len(file_uploads)} files for processing")
        else:
            # Regular JSON request
            try:
                data = json.loads(request.body)
                video_id = data.get('video_id')
                slides = data.get('slides', [])
            except json.JSONDecodeError:
                return JsonResponse({'success': False, 'error': 'Invalid JSON data'}, status=400)
            
            # No files in a regular JSON request
            file_uploads = {}
        
        # Validate inputs
        if not video_id:
            return JsonResponse({'success': False, 'error': 'Video ID is required'}, status=400)
            
        if not slides:
            return JsonResponse({'success': False, 'error': 'No slides data provided'}, status=400)
            
        # Get the video object
        try:
            video = Video.objects.get(id=video_id, user=request.user)
        except Video.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Video not found'}, status=404)
            
        print("**Slides data received:", slides)
        
        # Flag to track if we actually made any changes that require regenerating the video
        changes_made = False
            
        # Process each slide
        for slide_data in slides:
            clip_id = slide_data.get('id')
            text = slide_data.get('text', '')
            marked_text = slide_data.get('markedText', '')
            sequence = slide_data.get('sequence', 0)
            highlights = slide_data.get('highlights', [])
            
            # Update or create clip
            if clip_id > 0:  # Existing clip
                try:
                    clip = Clips.objects.get(id=clip_id, video=video)
                    
                    # Check if text or sequence has changed
                    if clip.text != text or clip.sequence != sequence:
                        clip.text = text
                        clip.sequence = sequence
                        clip.save()
                        changes_made = True
                    
                    # Process highlights and file uploads
                    if highlights:
                        # Get existing subclips for this clip
                        existing_subclips = {sc.text: sc for sc in Subclip.objects.filter(clip=clip)}
                        
                        # Track which existing subclips are still needed
                        preserved_subclips = set()
                        
                        # First, handle all highlights that match existing subclips
                        for highlight in highlights:
                            highlighted_text = highlight.get('text')
                            highlight_id = highlight.get('highlightId')
                            
                            if not highlighted_text or not highlight_id:
                                continue
                                
                            # Check if this is a resubmission of an existing highlight
                            if highlighted_text in existing_subclips:
                                # Preserve the reference for later
                                preserved_subclips.add(highlighted_text)
                                
                                # Check if we have a new file upload for this highlight
                                if highlight_id in file_uploads:
                                    # This is a resubmission - delete the old subclip and create a new one
                                    existing_subclips[highlighted_text].delete()
                                    
                                    # Process the new file upload
                                    uploaded_file = file_uploads[highlight_id]
                                    
                                    # Create a new subclip
                                    subclip = Subclip.objects.create(
                                        clip=clip,
                                        text=highlighted_text,
                                    )
                                    
                                    # Generate a unique filename based on the original name
                                    filename = f"subclip_{uuid.uuid4()}{os.path.splitext(uploaded_file.name)[1]}"
                                    
                                    # Save the file using Django's file storage system
                                    # Don't use absolute paths with S3 storage
                                    subclip.video_file.save(
                                        filename, 
                                        uploaded_file, 
                                        save=True
                                    )
                                    
                                    changes_made = True
                                    print(f"Replaced existing highlight: {highlight_id}, text: {highlighted_text}")
                                    
                                # Otherwise, no changes are needed for this highlight
                            else:
                                # This is a new highlight - will be processed in the next loop
                                pass
                        
                        # Now process new highlights
                        for highlight in highlights:
                            highlighted_text = highlight.get('text')
                            highlight_id = highlight.get('highlightId')
                            
                            if not highlighted_text or not highlight_id:
                                continue
                                
                            # Skip already processed highlights (those that matched existing subclips)
                            if highlighted_text in existing_subclips:
                                continue
                                
                            # This is a new highlight
                            changes_made = True
                            
                            # Check if we have a file upload for this highlight
                            if highlight_id in file_uploads:
                                # Process the file upload
                                uploaded_file = file_uploads[highlight_id]

                                # Create a new subclip
                                subclip = Subclip.objects.create(
                                    clip=clip,
                                    text=highlighted_text,
                                )

                                # Generate a unique filename
                                filename = f"subclip_{uuid.uuid4()}.{uploaded_file.name.split('.')[-1]}"

                                # Save the file using Django's file storage system
                                subclip.video_file.save(
                                    filename, 
                                    uploaded_file, 
                                    save=True
                                )
                                
                                print(f"Processed new file for highlight: {highlight_id}, text: {highlighted_text}")
                            else:
                                # No file upload, create a placeholder subclip
                                Subclip.objects.create(
                                    clip=clip,
                                    text=highlighted_text,
                                    video_file="",  # Empty placeholder
                                )
                        
                        # Delete subclips that are no longer in the highlights
                        for subclip_text, subclip in existing_subclips.items():
                            if subclip_text not in preserved_subclips:
                                # This subclip is no longer needed
                                changes_made = True
                                subclip.delete()
                                print(f"Deleted obsolete subclip: {subclip_text}")
                        
                        print(f"Processed subclips for clip {clip_id}")
                
                except Clips.DoesNotExist:
                    return JsonResponse({'success': False, 'error': f'Clip with ID {clip_id} not found'}, status=404)
            
            # We don't handle creating new clips here as it should have been done through update_clip
        
        # Only regenerate video files if changes were made
        if changes_made or Clips.objects.filter(video=video, is_changed=True).exists():
            print("Changes detected, regenerating video files...")
            # generate_audio_file(video, request.user.id)
            # generate_srt_file(video, request.user.id)
            # generate_clips_from_srt(video)
            # Subscription.objects.filter(user=request.user).update(unused_credits=F('unused_credits') - 1)            
            # generate_final_video(video)
            # video.output_with_bg = video.output
            # video.save()
            return redirect('loading', video_id=video.id)
        else:
            print("No changes detected, skipping video regeneration")
                    
        return JsonResponse({'success': True, 'message': 'Slides data saved successfully'})
        
    except Exception as e:

        print("Error in save_slides_data:", str(e))
        print(traceback.format_exc())
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required(login_url='login')
def recent_videos_view(request):
    """
    View to display recent videos for the authenticated user
    """
    if not request.user.is_authenticated:
        return redirect('login')
        
    # Get videos for the current user, ordered by creation date (newest first)
    # Make sure we get only videos with a non-empty output_with_bg field
    videos = Video.objects.filter(
        user=request.user, 
        output_with_bg__isnull=False
    ).exclude(
        output_with_bg__exact=''
    ).order_by('-created_at')[:10]
    
    return render(request, 'manage/recent-videos.html', {
        'videos': videos,
        'user_subscription': getattr(request.user, 'subscription', None)
    })

@login_required(login_url='login')
def process_video_view(request, video_id):
    """
    View to start processing a video and show loading screen
    """
    try:
        # Get the video
        video = get_object_or_404(Video, id=video_id, user=request.user)
        
        # Render the loading page
        return render(request, 'home/loading.html', {
            'video': video,
            'user_subscription': getattr(request.user, 'subscription', None)
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@csrf_exempt
@require_POST
@login_required(login_url='login')
def start_video_processing(request, video_id):
    """
    API endpoint to start processing a video
    """
    try:
        # Get the video
        video = get_object_or_404(Video, id=video_id, user=request.user)
        ProcessingStatus.objects.filter(video=video, status='completed').delete()
        # Check if processing is already in progress
        try:
            status_obj = ProcessingStatus.objects.get(video=video)
            if status_obj.status == 'processing':
                return JsonResponse({
                    "message": "Video is already being processed", 
                    "status": status_obj.status, 
                    "progress": status_obj.progress
                })
                
        except ProcessingStatus.DoesNotExist:
            # Create a new processing status object
            status_obj = ProcessingStatus.objects.create(video=video, status='processing', progress=0)
        
        # Start the processing in a background thread
        thread = threading.Thread(
            target=_process_video_background,
            args=(video, request.user.id, status_obj)
        )
        thread.daemon = True
        thread.start()
        
        return JsonResponse({
            "message": "Video processing started", 
            "status": "processing", 
            "progress": 0
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required(login_url='login')
def get_processing_status(request, video_id):
    """
    API endpoint to get the current processing status of a video
    """
    try:
        # Get the video
        video = get_object_or_404(Video, id=video_id, user=request.user)
        
        try:
            status_obj = ProcessingStatus.objects.get(video=video)
            return JsonResponse({
                "status": status_obj.status,
                "progress": status_obj.progress,
                "current_step": status_obj.current_step,
                "error_message": status_obj.error_message,
                "updated_at": status_obj.updated_at.isoformat() if status_obj.updated_at else None,
                "output": video.output.url if video.output else None,
            })
        except ProcessingStatus.DoesNotExist:
            return JsonResponse(
                {"status": "not_started", "progress": 0}
            )
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

# def _process_video_background(video, user_id, status_obj):
#     """Background task to process the video"""

#     try:
#         # Step 1: Generate audio (20% of progress)
#         status_obj.progress = 5
#         status_obj.current_step = "Generating audio"
#         status_obj.save()
        
#         success = generate_audio_file(video, user_id)
#         if not success:
#             status_obj.status = 'error'
#             status_obj.error_message = "Failed to generate audio file"
#             status_obj.save()
#             return
        
#         status_obj.progress = 20
#         status_obj.save()
        
#         # Step 2: Generate SRT file (40% of progress)
#         status_obj.current_step = "Generating SRT file"
#         status_obj.save()
        
#         success = generate_srt_file(video, user_id)
#         if not success:
#             status_obj.status = 'error'
#             status_obj.error_message = "Failed to generate SRT file"
#             status_obj.save()
#             return
        
#         status_obj.progress = 40
#         status_obj.save()


        
#         # Step 4: Generate clips from SRT (80% of progress)
#         status_obj.current_step = "Generating video clips"
#         status_obj.save()
        
#         generate_clips_from_srt(video)
        
#         status_obj.progress = 80
#         status_obj.save()
        
#         # Step 5: Generate final video (100% of progress)
#         status_obj.current_step = "Generating final video"
#         status_obj.save()
        
#         generate_final_video(video)
        
#         # Update video with the output
#         video.output_with_bg = video.output
#         video.save()
        
#         # Deduct a credit from the user's subscription
#         try:
#             Subscription.objects.filter(user_id=user_id).update(unused_credits=F('unused_credits') - 1)
#         except Exception as e:
#             print(f"Error updating credits: {str(e)}")
        
#         # Update status to completed
#         status_obj.progress = 100
#         status_obj.status = 'completed'
#         status_obj.current_step = "Processing complete"
#         status_obj.save()
        
#     except Exception as e:
#         # Update status to error
#         status_obj.status = 'error'
#         status_obj.error_message = str(e)
#         status_obj.save()
#         print(f"Error processing video: {str(e)}")
#         print(traceback.format_exc())



def _process_video_background(video:Video, user_id, status_obj):
    """Background task to process the video"""
    
    try:
        all_clips = Clips.objects.filter(video=video).order_by('sequence')
        is_text_changed = False
        clips_text = ""
        for clip in all_clips:
            if clip.text != clips_text:
                clips_text += clip.text + "\n"
        if video.content != clips_text or video.content in ["", None]:
            is_text_changed = True
            video.content = clips_text
            video.save()

        # Step 1: Generate audio (20% of progress)
        status_obj.progress = 5
        status_obj.current_step = "Generating audio"
        status_obj.save()
        if is_text_changed is True:
            success = generate_audio_file(video, user_id)

            if not success:
                status_obj.status = 'error'
                status_obj.error_message = "Failed to generate audio file"
                status_obj.save()
                return
        
        status_obj.progress = 20
        status_obj.save()
        
        # Step 2: Generate SRT file (40% of progress)
        status_obj.current_step = "Generating SRT file"
        status_obj.save()

        if is_text_changed is True:
            success = generate_srt_file(video, user_id)

            if not success:
                status_obj.status = 'error'
                status_obj.error_message = "Failed to generate SRT file"
                status_obj.save()
                return
            
        status_obj.progress = 40
        status_obj.save()
        
        # Step 3: Generate clips from SRT (60% of progress)
        status_obj.current_step = "Generating video clips"
        status_obj.save()
        if is_text_changed is True:
            generate_clips_from_srt(video)
        
        status_obj.progress = 60
        status_obj.save()
        
        # Step 4: Submit to RunPod for video processing (70% of progress)
        status_obj.current_step = "Submitting to RunPod for processing"
        status_obj.save()
        
        # Initialize RunPod processor
        from apps.processors.services.runpod_videoprocessor import RunPodVideoProcessor
        processor = RunPodVideoProcessor(video.id)

        for subclip in Subclip.objects.filter(clip__video=video).order_by('clip__sequence', 'start_time'):
            subclip.save()
        # Submit job to RunPod
        if is_text_changed is False:

            result = processor.replace_subclips(video)
        else:
            result = processor.process_video(video)
        
        if not result["success"]:
            status_obj.status = 'error'
            status_obj.error_message = f"Failed to submit job to RunPod: {result.get('error', 'Unknown error')}"
            status_obj.save()
            return
        
        # Job submitted successfully
        print(result)
        job_id = result["job_id"]
        status_obj.current_step = "Processing on RunPod"
        status_obj.progress = 70
        status_obj.save()
        
        # Step 5: Poll RunPod until job completes (up to 90% progress)
        max_attempts = 60  # Adjust based on your expected processing time
        delay_seconds = 10  # Check every 10 seconds
        print("Polling RunPod for job completion...")
        print("Job ID:", job_id)
        # Poll for results
        poll_result = processor.poll_until_complete(job_id, max_attempts, delay_seconds)
        
        if not poll_result["success"]:
            status_obj.status = 'error'
            status_obj.error_message = f"RunPod processing failed: {poll_result.get('error', 'Unknown error')}"
            status_obj.save()
            return
        
        # Processing successful, save results
        output_data = poll_result["output"]
        save_success = processor.save_results(video, output_data)
        
        if not save_success:
            status_obj.status = 'error'
            status_obj.error_message = "Failed to save results from RunPod"
            status_obj.save()
            return
        
        status_obj.progress = 90
        status_obj.save()
        
        # Step 6: Apply any additional processing if needed (100% progress)
        status_obj.current_step = "Finalizing video"
        status_obj.save()
        
        # Check if we need to set output_with_bg from output
        if video.output:
            video.output_with_bg = video.output
            video.save()

        if video.output_with_watermark: 
            video.output_with_bg_watermark = video.output_with_watermark
            video.save()

        Clips.objects.filter(video=video).update(is_changed=False)
        
        # Update status to completed
        status_obj.progress = 100
        status_obj.status = 'completed'
        status_obj.current_step = "Processing complete"
        status_obj.save()
    
    except Exception as e:
        # Update status to error
        status_obj.status = 'error'
        status_obj.error_message = str(e)
        status_obj.save()
        print(f"Error processing video: {str(e)}")
        print(traceback.format_exc())

@csrf_exempt
@require_POST
@login_required(login_url='login')
def delete_background_music(request):
    """
    Delete a background music object based on the provided ID
    """
    try:
        data = json.loads(request.body)
        bg_music_id = data.get('bg_music_id')
        
        # Validate input
        if not bg_music_id:
            return JsonResponse({'success': False, 'error': 'Background music ID is required'}, status=400)
            
        try:
            # Get the background music object, ensuring it belongs to the current user
            bg_music = BackgroundMusic.objects.get(id=bg_music_id, video__user=request.user)
            
            # Delete the actual file from storage if it exists
            if bg_music.audio_file:
                bg_music.audio_file.delete(save=False)
                
            # Delete the database record
            bg_music.delete()
            
            return JsonResponse({'success': True, 'message': 'Background music deleted successfully'})
        except BackgroundMusic.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Background music not found'}, status=404)
            
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@api_view(['POST'])
# @permission_classes([IsAuthenticated])
def generate_scene_suggestions(request):
    """
    API endpoint to generate video scene suggestions using OpenAI.
    
    Expected request body:
    {
        "prompt": "Are you struggling with sciatica?"
    }
    
    Returns:
        JSON response with scene suggestions and search URLs
    """
    try:
        data = request.data
        prompt = data.get('prompt')
        print("--- Prompt received:", prompt)
        if not prompt:
            return Response({
                'status': 'error',
                'message': 'Prompt is required'
            }, status=400)
        
        # Initialize the OpenAI handler
        openai_handler = OpenAIHandler()
        
        # Generate scene suggestions
        result = openai_handler.generate_scene_suggestions(prompt)
        
        return Response(result)
        
    except Exception as e:
        logger.error(f"Error generating scene suggestions: {str(e)}")
        return Response({
            'status': 'error',
            'message': f'Failed to generate scene suggestions: {str(e)}'
        }, status=500)
