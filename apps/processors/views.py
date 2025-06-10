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
from django.views.decorators.http import require_http_methods
from apps.processors.handler.elevenlabs import ElevenLabsHandler

import traceback
from apps.core.models import UserAsset
from apps.core.services.s3_service import get_s3_client
from django.db.models import Count, Min

import tempfile
from django.core.files import File
import time
from .handler.openai import OpenAIHandler
import logging
from django.db.models.signals import pre_save, post_save
from .signals import configure_subclip
from django.db.models import Q

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
    all_user_videos = Video.objects.filter(user=request.user)
    
    # Then, filter for videos with a name
    named_videos = all_user_videos.filter(name__isnull=False).exclude(name="")
    
    # Get videos with output
    output_videos = all_user_videos.filter(output__isnull=False).exclude(output="")
    
    # Combine the two querysets using union
    # The "|" operator on querysets performs a SQL UNION operation
    videos = (named_videos | output_videos).distinct().order_by('-created_at')
    
    print(f"All user videos: {all_user_videos.count()}")
    print(f"Named videos: {named_videos.count()}")
    print(f"Output videos: {output_videos.count()}")
    print(f"Combined videos: {videos.count()}")
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

# def _process_video_background(video:Video, user_id, status_obj):
#     """Background task to process the video"""
    
#     try:
#         all_clips = Clips.objects.filter(video=video).order_by('sequence')
#         is_text_changed = False
#         clips_text = ""
#         for clip in all_clips:
#             if clip.text != clips_text:
#                 clips_text += clip.text + "\n"
#         if video.content != clips_text or video.content in ["", None]:
#             is_text_changed = True
#             video.content = clips_text
#             video.save()

#         # Step 1: Generate audio (20% of progress)
#         status_obj.progress = 5
#         status_obj.current_step = "Generating audio"
#         status_obj.save()
#         if is_text_changed is True:
#             success = generate_audio_file(video, user_id)

#             if not success:
#                 status_obj.status = 'error'
#                 status_obj.error_message = "Failed to generate audio file"
#                 status_obj.save()
#                 return
        
#         status_obj.progress = 20
#         status_obj.save()
        
#         # Step 2: Generate SRT file (40% of progress)
#         status_obj.current_step = "Generating SRT file"
#         status_obj.save()

#         if is_text_changed is True:
#             success = generate_srt_file(video, user_id)

#             if not success:
#                 status_obj.status = 'error'
#                 status_obj.error_message = "Failed to generate SRT file"
#                 status_obj.save()
#                 return
            
#         status_obj.progress = 40
#         status_obj.save()
        
#         # Step 3: Generate clips from SRT (60% of progress)
#         status_obj.current_step = "Generating video clips"
#         status_obj.save()
#         if is_text_changed is True:
#             generate_clips_from_srt(video)
        
#         status_obj.progress = 60
#         status_obj.save()
        
#         # Step 4: Submit to RunPod for video processing (70% of progress)
#         status_obj.current_step = "Submitting to RunPod for processing"
#         status_obj.save()
        
#         # Initialize RunPod processor
#         from apps.processors.services.runpod_videoprocessor import RunPodVideoProcessor
#         processor = RunPodVideoProcessor(video.id)

#         for subclip in Subclip.objects.filter(clip__video=video).order_by('clip__sequence', 'start_time'):
#             subclip.save()
#         # Submit job to RunPod
#         if is_text_changed is False and video.output:

#             result = processor.replace_subclips(video)
#         else:
#             result = processor.process_video(video)
        
#         if not result["success"]:
#             status_obj.status = 'error'
#             status_obj.error_message = f"Failed to submit job to RunPod: {result.get('error', 'Unknown error')}"
#             status_obj.save()
#             return
        
#         # Job submitted successfully
#         print(result)
#         job_id = result["job_id"]
#         status_obj.current_step = "Processing on RunPod"
#         status_obj.progress = 70
#         status_obj.save()
        
#         # Step 5: Poll RunPod until job completes (up to 90% progress)
#         max_attempts = 60  # Adjust based on your expected processing time
#         delay_seconds = 10  # Check every 10 seconds
#         print("Polling RunPod for job completion...")
#         print("Job ID:", job_id)
#         # Poll for results
#         poll_result = processor.poll_until_complete(job_id, max_attempts, delay_seconds)
        
#         if not poll_result["success"]:
#             status_obj.status = 'error'
#             status_obj.error_message = f"RunPod processing failed: {poll_result.get('error', 'Unknown error')}"
#             status_obj.save()
#             return
        
#         # Processing successful, save results
#         output_data = poll_result["output"]
#         print("RunPod processing completed successfully.")
#         print("Output data:", output_data)
#         save_success = processor.save_results(video, output_data)
        
#         if not save_success:
#             status_obj.status = 'error'
#             status_obj.error_message = "Failed to save results from RunPod"
#             status_obj.save()
#             return
        
#         status_obj.progress = 90
#         status_obj.save()
        
#         # Step 6: Apply any additional processing if needed (100% progress)
#         status_obj.current_step = "Finalizing video"
#         status_obj.save()
        
#         # Check if we need to set output_with_bg from output
#         if video.output:
#             video.output_with_bg = video.output
#             video.save()

#         if video.output_with_watermark: 
#             video.output_with_bg_watermark = video.output_with_watermark
#             video.save()

#         Clips.objects.filter(video=video).update(is_changed=False)
        
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


def _process_video_background(video: Video, user_id, status_obj):
    """Background task to process the video with better error handling"""
    
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

        if not video.audio_file:
            is_text_changed = True
        # Step 1: Generate audio (20% of progress)
        status_obj.progress = 5
        status_obj.current_step = "Generating audio"
        status_obj.save()
        
        if is_text_changed is True:
            try:
                success = generate_audio_file(video, user_id)
                if not success:
                    status_obj.status = 'error'
                    status_obj.error_message = "Failed to generate audio file"
                    status_obj.save()
                    return
            except Exception as e:
                error_msg = str(e)
                # Check if it's a credits issue
                if "Insufficient credits" in error_msg:
                    status_obj.status = 'error'
                    status_obj.error_message = "Insufficient credits to generate voiceover"
                    status_obj.save()
                    return
                elif "payment_issue" in error_msg or "failed or incomplete payment" in error_msg:
                    status_obj.status = 'error'
                    status_obj.error_message = "ElevenLabs payment issue: Your subscription has a failed or incomplete payment. Complete the latest invoice to continue usage."
                    status_obj.save()
                    return
                elif "Invalid ElevenLabs API key" in error_msg:
                    status_obj.status = 'error'  
                    status_obj.error_message = "Invalid ElevenLabs API key"
                    status_obj.save()
                    return
                elif "Invalid Voice ID" in error_msg:
                    status_obj.status = 'error'
                    status_obj.error_message = "Invalid Voice ID"  
                    status_obj.save()
                    return
                else:
                    # Re-raise other exceptions
                    raise e
                    
        status_obj.progress = 20
        status_obj.save()
        
        # Rest of your existing processing code remains the same...
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

        # Find subclips with duplicate start_time, delete those with lower IDs
        duplicate_start_times = (
            Subclip.objects.filter(clip__video=video)
            .values('start_time')
            .annotate(count=Count('id'), min_id=Min('id'))
            .filter(count__gt=1)
        )

        for item in duplicate_start_times:
            Subclip.objects.filter(
                clip__video=video,
                start_time=item['start_time']
            ).exclude(id=item['min_id']).delete()

        # Find subclips with duplicate end_time, delete those with lower IDs
        duplicate_end_times = (
            Subclip.objects.filter(clip__video=video)
            .values('end_time')
            .annotate(count=Count('id'), min_id=Min('id'))
            .filter(count__gt=1)
        )

        for item in duplicate_end_times:
            Subclip.objects.filter(
                clip__video=video,
                end_time=item['end_time']
            ).exclude(id=item['min_id']).delete()


        # Submit job to RunPod
        if is_text_changed is False and video.output:
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
        print("RunPod processing completed successfully.")
        print("Output data:", output_data)
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
        import traceback
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

@csrf_exempt
@require_POST
@login_required(login_url='login')
def save_draft(request):
    """
    Save video draft with a name
    """
    try:
        data = json.loads(request.body)
        video_id = data.get('video_id')
        name = data.get('name')
        
        if not video_id or not name:
            return JsonResponse({'success': False, 'error': 'Missing required fields'}, status=400)
            
        try:
            video = Video.objects.get(id=video_id, user=request.user)
            video.name = name
            video.save()
            return JsonResponse({'success': True})
        except Video.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Video not found'}, status=404)
            
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)



@csrf_exempt  
@require_http_methods(["POST"])
@login_required(login_url='login')
def update_video_credentials(request, video_id):

    """
    API endpoint to update video ElevenLabs credentials
    """
    try:
        video = get_object_or_404(Video, id=video_id, user=request.user)
        
        data = json.loads(request.body)
        api_key = data.get('elevenlabs_api_key', '').strip()
        voice_id = data.get('voice_id', '').strip()
        
        if not api_key or not voice_id:
            return JsonResponse({
                'success': False, 
                'error': 'Both API key and Voice ID are required'
            })
        
        # Validate the credentials before saving
        try:
            handler = ElevenLabsHandler(api_key=api_key, voice_id=voice_id)
            # This will raise an exception if invalid
            handler._verify_api_key()
            print(video.content)
            if handler.has_sufficient_credits(len(video.content)) is False:
                return JsonResponse({
                    'success': False, 
                    'error': 'Insufficient credits to generate voiceover'
                })
            video.elevenlabs_api_key = api_key
            video.voice_id = voice_id
            video.save()
        except Exception as e:
            error_msg = str(e)
            if "Insufficient credits" in error_msg:
                error_to_return = "Insufficient credits to generate voiceover"
            elif "payment_issue" in error_msg or "failed or incomplete payment" in error_msg:
                error_to_return = "ElevenLabs payment issue: Your subscription has a failed or incomplete payment. Complete the latest invoice to continue usage."
            elif "Invalid ElevenLabs API key" in error_msg:
                error_to_return = "Invalid ElevenLabs API key"
            elif "Invalid Voice ID" in error_msg:
                error_to_return = "Invalid Voice ID"  
            else:
                error_to_return = f"Error validating credentials: {error_msg}"
            return JsonResponse({
                'success': False, 
                'error': error_to_return
            })
        
        # Update video with new credentials
        
        # Reset processing status to allow reprocessing
        video.audio_file = None
        video.srt_file = None
        video.output = None
        video.output_with_bg = None
        video.output_with_watermark = None
        video.output_with_bg_watermark = None
        video.save()

        # Mark all clips as changed to force regeneration
        Clips.objects.filter(video=video).update(is_changed=True)

        # Reset processing status to allow reprocessing
        ProcessingStatus.objects.filter(video=video).delete()
        
        return JsonResponse({
            'success': True, 
            'message': 'Credentials updated successfully'
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False, 
            'error': str(e)
        }, status=500)


# Add this endpoint to get processing status with credentials info
@login_required(login_url='login')
def get_processing_status_with_credentials(request, video_id):
    """
    Get processing status including current credentials for error handling
    """
    try:
        video = get_object_or_404(Video, id=video_id, user=request.user)
        
        try:
            status_obj = ProcessingStatus.objects.get(video=video)
            response_data = {
                'status': status_obj.status,
                'progress': status_obj.progress,
                'current_step': status_obj.current_step,
                'error_message': status_obj.error_message,
                'current_api_key': video.elevenlabs_api_key or '',
                'current_voice_id': video.voice_id or ''
            }
            return JsonResponse(response_data)
        except ProcessingStatus.DoesNotExist:
            return JsonResponse({
                'status': 'not_started',
                'progress': 0,
                'current_api_key': video.elevenlabs_api_key or '',
                'current_voice_id': video.voice_id or ''
            })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required(login_url='login')
def get_elevenlabs_voices(request, video_id):
    """
    API endpoint to get available ElevenLabs voices for the current user
    """
    try:
        video = get_object_or_404(Video, id=video_id, user=request.user)
        
        if not video.elevenlabs_api_key:
            return JsonResponse({'success': False, 'error': 'API key is required to fetch voices'}, status=400)
        
        
        handler = ElevenLabsHandler(api_key=video.elevenlabs_api_key)
        voices = handler.get_available_voices()
        
        return JsonResponse({
            'success': True,
            'voices': voices
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required(login_url='login')
def get_voiceover_history(request, video_id):
    """
    API endpoint to get voiceover history for a video
    """
    try:
        print("Fetching voiceover history for video ID:", video_id)
        print("User:", request.user)
        video = get_object_or_404(Video, id=video_id)
        if not video.elevenlabs_api_key:
            return JsonResponse({'success': False, 'error': 'API key is required to fetch voiceover history'}, status=400)
        
        handler = ElevenLabsHandler(api_key=video.elevenlabs_api_key)  
        return JsonResponse({'success': False, 'history': handler.get_history().get('history')}, status=200)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required(login_url='login')
def get_saved_history(request, video_id):
    """
    API endpoint to get voiceover history for a video with saved HTML
    """
    try:
        print("Fetching voiceover history from history ID for video ID:", video_id)
        print("User:", request.user)
        video = get_object_or_404(Video, id=video_id)

        if not video.elevenlabs_api_key:
            return JsonResponse({'success': False, 'error': 'API key is required to fetch voiceover history'}, status=400)
        
        handler = ElevenLabsHandler(api_key=video.elevenlabs_api_key)
        history_item = handler.get_history_by_id(video.history_id)
        
        # ADD: Include saved HTML and split data
        response_data = {
            'success': False, 
            'history': [history_item],
            'saved_preview_html': getattr(video, 'history_preview_html', ''),
            'saved_split_positions': json.loads(getattr(video, 'split_positions', '[]')),
            'saved_preview_text': getattr(video, 'preview_text', '')
        }
        
        return JsonResponse(response_data, status=200)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required(login_url='login')
def update_video_history(request):
    """
    Update video history_id and save preview HTML
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            video_id = data.get('video_id')
            history_id = data.get('history_id')
            preview_html = data.get('preview_html', '')
            split_positions = data.get('split_positions', [])
            preview_text = data.get('preview_text', '')
            
            video = get_object_or_404(Video, id=video_id)
            video.history_id = history_id
            video.history_preview_html = preview_html  # ADD this field to your Video model
            video.split_positions = json.dumps(split_positions)  # ADD this field
            video.preview_text = preview_text  # ADD this field
            video.save()
            
            return JsonResponse({
                'success': True,
                'message': 'Video history_id and preview HTML updated successfully'
            })
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'}, status=405)


@csrf_exempt
@require_POST
@login_required(login_url='login')
def delete_all_clips(request):
    """
    Delete all clips and subclips for a specific video
    """
    try:
        data = json.loads(request.body)
        video_id = data.get('video_id')
        
        # Validate input
        if not video_id:
            return JsonResponse({'success': False, 'error': 'Video ID is required'}, status=400)
        
        # Get the video object
        try:
            video = Video.objects.get(id=video_id, user=request.user)
        except Video.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Video not found'}, status=404)
        
        # Get all clips for this video
        clips = Clips.objects.filter(video=video)
        clips_count = clips.count()
        
        # Get all subclips for these clips
        subclips = Subclip.objects.filter(clip__video=video)
        subclips_count = subclips.count()
        
        # Delete all subclips first (due to foreign key constraints)
        subclips.delete()
        
        # Delete all clips
        clips.delete()
        
        # Reset video content to empty
        video.content = ""
        video.save(update_fields=['content'])
        
        return JsonResponse({
            'success': True, 
            'message': f'Successfully deleted all clips and subclips for video {video_id}',
            'video_id': video_id,
            'deleted_count': clips_count,
            'subclips_deleted_count': subclips_count
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# Add these new views to your existing views.py file
# Add these new views to your existing views.py file

@csrf_exempt
@require_POST
@login_required(login_url='login')
def split_subtitle(request):
    """
    Split a subtitle into two subtitles at the specified position
    Remove highlights/subclips for text that crosses the split boundary
    """
    try:
        data = json.loads(request.body)
        clip_id = data.get('clip_id')
        split_position = data.get('split_position')
        first_part_text = data.get('first_part_text')
        second_part_text = data.get('second_part_text')
        first_part_marked = data.get('first_part_marked', '')
        second_part_marked = data.get('second_part_marked', '')
        
        # Validate input
        if not all([clip_id, first_part_text, second_part_text]):
            return JsonResponse({'success': False, 'error': 'Missing required fields'}, status=400)
        
        try:
            # Get the clip to split
            clip = Clips.objects.get(id=clip_id, video__user=request.user)
            original_sequence = clip.sequence
            original_text = getCleanTextContent(clip.text)
            
            # Get all existing subclips for this clip BEFORE any changes
            existing_subclips = list(Subclip.objects.filter(clip=clip))
            
            # Update the original clip with first part
            clip.text = first_part_text
            clip.is_changed = True
            clip.save()
            
            # Get clips that need sequence adjustment (those after current clip)
            clips_to_update = Clips.objects.filter(
                video=clip.video,
                sequence__gt=original_sequence
            ).order_by('sequence')
            
            # Increment sequence numbers for clips after the split point
            for clip_to_update in clips_to_update:
                clip_to_update.sequence += 1
                clip_to_update.save()
            
            # Create new clip for second part
            new_clip = Clips.objects.create(
                video=clip.video,
                text=second_part_text,
                start_time=0.0,
                end_time=5.0,
                sequence=original_sequence + 1,
                is_changed=True
            )
            
            # Handle subclip reassignment and removal
            if existing_subclips:
                # Get the clean text parts
                first_clean = getCleanTextContent(first_part_text)
                second_clean = getCleanTextContent(second_part_text)
                
                # Parse highlights that remain after split
                first_highlights = _extract_highlights_from_marked_text(first_part_marked)
                second_highlights = _extract_highlights_from_marked_text(second_part_marked)
                
                # Create sets of highlighted text that survived the split
                surviving_first_texts = {h['text'].strip() for h in first_highlights}
                surviving_second_texts = {h['text'].strip() for h in second_highlights}
                
                print(f"Original text length: {len(original_text)}, split at: {split_position}")
                print(f"Surviving highlights - First: {surviving_first_texts}, Second: {surviving_second_texts}")
                
                subclips_to_delete = []
                subclips_to_move = []
                subclips_to_keep = []
                
                for subclip in existing_subclips:
                    subclip_text = subclip.text.strip()
                    
                    # Check if this subclip's text survived in either part
                    if subclip_text in surviving_second_texts:
                        # This highlight survived in the second part
                        subclips_to_move.append(subclip)
                        print(f"Moving subclip '{subclip_text}' to second part")
                    elif subclip_text in surviving_first_texts:
                        # This highlight survived in the first part
                        subclips_to_keep.append(subclip)
                        print(f"Keeping subclip '{subclip_text}' in first part")
                    else:
                        # This highlight was removed during split (crossed boundary)
                        subclips_to_delete.append(subclip)
                        print(f"Deleting subclip '{subclip_text}' (crossed split boundary)")
                
                # Execute the changes
                for subclip in subclips_to_move:
                    subclip.clip = new_clip
                    subclip.save()
                
                for subclip in subclips_to_delete:
                    # Delete the video file if it exists
                    if subclip.video_file:
                        try:
                            subclip.video_file.delete(save=False)
                        except Exception as e:
                            print(f"Error deleting video file: {e}")
                    subclip.delete()
                
                print(f"Split complete: kept {len(subclips_to_keep)}, moved {len(subclips_to_move)}, deleted {len(subclips_to_delete)} subclips")
            
            return JsonResponse({
                'success': True,
                'message': 'Subtitle split successfully',
                'original_clip_id': clip.id,
                'new_clip_id': new_clip.id,
                'deleted_subclips': len([s for s in existing_subclips if s.text.strip() not in 
                                       {h['text'].strip() for h in first_highlights + second_highlights}])
            })
            
        except Clips.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Clip not found'}, status=404)
            
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        print(f"Error in split_subtitle: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def getCleanTextContent(text):
    """
    Helper function to extract clean text content from HTML text
    This should match the JavaScript function getCleanTextContent
    """
    if not text:
        return ""
    
    # Remove HTML tags
    import re
    clean_text = re.sub(r'<[^>]+>', '', text)
    
    # Normalize whitespace
    clean_text = ' '.join(clean_text.split())
    
    return clean_text.strip()


@csrf_exempt
@require_POST
@login_required(login_url='login')
def merge_subtitles(request):
    """
    Merge a subtitle with the previous subtitle
    """
    try:
        data = json.loads(request.body)
        current_clip_id = data.get('current_clip_id')
        previous_clip_id = data.get('previous_clip_id')
        merged_text = data.get('merged_text')
        merged_marked_text = data.get('merged_marked_text', '')
        
        # Validate input
        if not all([current_clip_id, previous_clip_id, merged_text]):
            return JsonResponse({'success': False, 'error': 'Missing required fields'}, status=400)
        
        try:
            # Get both clips
            current_clip = Clips.objects.get(id=current_clip_id, video__user=request.user)
            previous_clip = Clips.objects.get(id=previous_clip_id, video__user=request.user)
            
            # Verify they belong to the same video
            if current_clip.video_id != previous_clip.video_id:
                return JsonResponse({'success': False, 'error': 'Clips belong to different videos'}, status=400)
            
            # Verify sequence order
            if previous_clip.sequence >= current_clip.sequence:
                return JsonResponse({'success': False, 'error': 'Invalid clip order for merging'}, status=400)
            
            current_sequence = current_clip.sequence
            
            # Move all subclips from current clip to previous clip
            Subclip.objects.filter(clip=current_clip).update(clip=previous_clip)
            
            # Update previous clip with merged content
            previous_clip.text = merged_text
            previous_clip.is_changed = True
            previous_clip.save()
            
            # Delete the current clip
            current_clip.delete()
            
            # Update sequence numbers for clips after the deleted clip
            clips_to_update = Clips.objects.filter(
                video=previous_clip.video,
                sequence__gt=current_sequence
            ).order_by('sequence')
            
            for clip_to_update in clips_to_update:
                clip_to_update.sequence -= 1
                clip_to_update.save()
            
            return JsonResponse({
                'success': True,
                'message': 'Subtitles merged successfully',
                'merged_clip_id': previous_clip.id,
                'deleted_clip_id': current_clip_id
            })
            
        except Clips.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'One or both clips not found'}, status=404)
            
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def _extract_highlights_from_marked_text(marked_text):
    """
    Helper function to extract highlight information from marked HTML text
    """
    if not marked_text or '<mark' not in marked_text:
        return []
    
    import re
    from html.parser import HTMLParser
    
    class HighlightExtractor(HTMLParser):
        def __init__(self):
            super().__init__()
            self.highlights = []
            self.current_mark_attrs = {}
            self.current_text = ''
            self.in_mark = False
        
        def handle_starttag(self, tag, attrs):
            if tag == 'mark':
                self.in_mark = True
                self.current_mark_attrs = dict(attrs)
                self.current_text = ''
        
        def handle_endtag(self, tag):
            if tag == 'mark' and self.in_mark:
                self.highlights.append({
                    'text': self.current_text,
                    'attributes': self.current_mark_attrs
                })
                self.in_mark = False
                self.current_mark_attrs = {}
                self.current_text = ''
        
        def handle_data(self, data):
            if self.in_mark:
                self.current_text += data
    
    try:
        extractor = HighlightExtractor()
        extractor.feed(marked_text)
        return extractor.highlights
    except Exception as e:
        print(f"Error extracting highlights: {e}")
        return []


@csrf_exempt
@require_POST
@login_required(login_url='login')
def reorder_clips(request):
    """
    Reorder clips after split/merge operations to ensure proper sequencing
    """
    try:
        data = json.loads(request.body)
        video_id = data.get('video_id')
        clip_orders = data.get('clip_orders')  # List of {clip_id: sequence} pairs
        
        # Validate input
        if not video_id or not clip_orders:
            return JsonResponse({'success': False, 'error': 'Missing required fields'}, status=400)
        
        try:
            video = Video.objects.get(id=video_id, user=request.user)
            
            # Update clip sequences in a transaction to avoid conflicts
            from django.db import transaction
            
            with transaction.atomic():
                for clip_order in clip_orders:
                    clip_id = clip_order.get('clip_id')
                    sequence = clip_order.get('sequence')
                    
                    if clip_id and sequence is not None:
                        Clips.objects.filter(
                            id=clip_id, 
                            video=video
                        ).update(sequence=sequence)
            
            return JsonResponse({
                'success': True,
                'message': 'Clips reordered successfully'
            })
            
        except Video.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Video not found'}, status=404)
            
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
@require_POST
@login_required(login_url='login')
def batch_update_clips(request):
    """
    Batch update multiple clips after split/merge operations
    This is useful for updating sequences and content in one request
    """
    try:
        data = json.loads(request.body)
        video_id = data.get('video_id')
        clip_updates = data.get('clip_updates')  # List of clip update objects
        
        # Validate input
        if not video_id or not clip_updates:
            return JsonResponse({'success': False, 'error': 'Missing required fields'}, status=400)
        
        try:
            video = Video.objects.get(id=video_id, user=request.user)
            
            from django.db import transaction
            
            with transaction.atomic():
                for update in clip_updates:
                    clip_id = update.get('clip_id')
                    
                    if not clip_id:
                        continue
                    
                    try:
                        clip = Clips.objects.get(id=clip_id, video=video)
                        
                        # Update fields if provided
                        if 'text' in update:
                            clip.text = update['text']
                        if 'sequence' in update:
                            clip.sequence = update['sequence']
                        if 'start_time' in update:
                            clip.start_time = update['start_time']
                        if 'end_time' in update:
                            clip.end_time = update['end_time']
                        
                        clip.save()
                        
                    except Clips.DoesNotExist:
                        continue  # Skip non-existent clips
            
            return JsonResponse({
                'success': True,
                'message': 'Clips updated successfully'
            })
            
        except Video.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Video not found'}, status=404)
            
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)