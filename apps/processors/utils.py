import os
import chardet
import json
import re
import datetime
import boto3
from django.core.files.base import ContentFile
# from .services.text_alignment_service import TextAudioAligner
from .services.elevenlabs_text_alignment import ElevenLabsTextAlignment
from .handler.elevenlabs import ElevenLabsHandler
from .services.video_processor import VideoProcessorService
from .models import Clips, Video, ProcessingStatus, Subclip, BackgroundMusic
import subprocess
from django.conf import settings
from django.core.files import File
from apps.core.services.s3_service import get_s3_client
import tempfile
import hashlib
import logging
import requests
from urllib.parse import urlparse
from django.core.files.temp import NamedTemporaryFile
from apps.core.models import Subscription
from django.core.files.storage import default_storage
from apps.core.models import AppVariables

def generate_final_video(video: Video) -> bool:
    """Generate the final video for a Video instance with progress tracking."""
    # Ensure all subclips are saved
    for subclip in Subclip.objects.filter(clip__video=video):
        subclip.save()
        
    try:
        # Get or create processing status
        status_obj, created = ProcessingStatus.objects.get_or_create(
            video=video,
            defaults={
                "status": "processing",
                "progress": 0,
                "current_step": "Initializing video generation",
            },
        )

        # Update status if it exists
        if not created:
            status_obj.status = "processing"
            status_obj.progress = 0
            status_obj.current_step = "Initializing video generation"
            status_obj.error_message = None
            status_obj.save()

        # Create processor with progress callback
        processor = VideoProcessorService(
            video, status_callback=update_processing_status
        )
        
        # Check if we need to process a specific subclip
        clips = Clips.objects.filter(video=video, is_changed=True)
        updated_successfully = False
        update_processing_status(video.id, 20, "Replacing changed subclip")
        for clip in clips:
                for subclip in Subclip.objects.filter(clip=clip):
                    try:
                        # Try to replace the subclip
                        success = processor.replace_subclip(subclip=subclip)
                        if success:
                            updated_successfully = True
                            update_processing_status(video.id, 90, "Subclip replaced successfully")
                        else:
                            update_processing_status(video.id, 0, error=f"Failed to replace subclip {subclip.id}")
                    except Exception as e:
                        # Log the specific subclip error but continue processing other subclips
                        print(f"Error processing subclip {subclip.id}: {str(e)}")
                        continue
            
        if updated_successfully:
            # Update status to completed
            status_obj.progress = 100
            status_obj.status = "completed"
            status_obj.current_step = "Video generation complete"
            status_obj.save()            
            cleanup_temp_files()
            
            return True

        output_path = processor.generate_video(
            add_watermark="free"
            in Subscription.objects.filter(user=video.user).first().plan.name.lower()
        )

        # Process background music if needed
        if BackgroundMusic.objects.filter(video=video).exists():
            update_processing_status(video.id, 80, "Adding background music")
            output_path = apply_background_music(video, output_path)

        # Save the output file to the video model using Django's File API
        with open(output_path, "rb") as f:
            output_filename = f"video_{video.id}_output.mp4"
            video.output.save(output_filename, File(f), save=True)

        # Update status to completed
        status_obj.progress = 100
        status_obj.status = "completed"
        status_obj.current_step = "Video generation complete"
        status_obj.save()

        # Clean up temporary files older than an hour
        cleanup_temp_files()
        
        return True

    except Exception as e:
        # Log the error
        print(f"Error generating final video for Video #{video.id}: {str(e)}")

        # Update status to error
        try:
            status_obj = ProcessingStatus.objects.get(video=video)
            status_obj.status = "error"
            status_obj.error_message = str(e)
            status_obj.save()
        except:
            pass

        return False

def cleanup_temp_files():
    """Clean up temporary files older than an hour, but preserve recently streamed files"""
    try:
        # Find temporary directories used for video processing
        temp_dir = tempfile.gettempdir()
        current_time = datetime.datetime.now()

        # Check for files/folders in temp directory
        for item in os.listdir(temp_dir):
            item_path = os.path.join(temp_dir, item)

            # Skip if it's not a file or directory
            if not os.path.isfile(item_path) and not os.path.isdir(item_path):
                continue

            # Check if the item is a folder created by our app or a temp file
            is_our_temp = False
            is_stream_file = False

            # Check for our video files - identify temp stream files separately
            if os.path.isfile(item_path):
                if (
                    item.startswith("video_")
                    and "_stream_" in item
                    and item.endswith(".mp4")
                ):
                    is_stream_file = True
                elif item.endswith((".mp4", ".mov", ".avi", ".srt")):
                    is_our_temp = True

            # Check for our temporary directories
            if os.path.isdir(item_path) and "videocrafter_temp" in item:
                is_our_temp = True

            # Process each type differently
            if is_our_temp or is_stream_file:
                # Get last modification time
                modified_time = datetime.datetime.fromtimestamp(
                    os.path.getmtime(item_path)
                )

                # For stream files, use a longer threshold (4 hours)
                threshold = 14400 if is_stream_file else 3600  # 4 hours or 1 hour

                # Delete if older than threshold
                if (current_time - modified_time).total_seconds() > threshold:
                    try:
                        if os.path.isfile(item_path):
                            os.remove(item_path)
                        else:
                            # Use shutil to remove directory and all its contents
                            import shutil

                            shutil.rmtree(item_path)

                        print(f"Cleaned up: {item_path}")
                    except Exception as e:
                        print(f"Error cleaning up {item_path}: {str(e)}")
    except Exception as e:
        print(f"Error during temp cleanup: {str(e)}")


def update_processing_status(video_id, progress, step=None, error=None):
    """Update the processing status for a video."""
    try:
        status_obj = ProcessingStatus.objects.get(video_id=video_id)
        status_obj.progress = progress

        if step:
            status_obj.current_step = step

        if error:
            status_obj.status = "error"
            status_obj.error_message = error

        status_obj.save()
    except ProcessingStatus.DoesNotExist:
        # Create a new status object if it doesn't exist
        ProcessingStatus.objects.create(
            video_id=video_id,
            status="processing" if not error else "error",
            progress=progress,
            current_step=step or "Processing",
            error_message=error,
        )
    except Exception as e:
        # Log error but don't interrupt processing
        print(f"Error updating processing status: {e}")


def generate_audio_file(video, user_id):
    """
    Generate audio file from text using ElevenLabs with better error handling
    """
    try:
        # # Check for required fields
        # if not video.elevenlabs_api_key or not video.voice_id:
        #     raise ValueError("ElevenLabs API key and voice ID are required")
        
        clips = Clips.objects.filter(video=video)
        if not clips.exists():
            # Check if text file exists
            if not video.text_file:
                raise ValueError("Text file not available")

            # Read text using storage API instead of direct file access
            from django.core.files.storage import default_storage
            import chardet
            
            # Read the file using Django's storage API
            with default_storage.open(video.text_file.name, 'rb') as file:
                raw_data = file.read()
                # Detect encoding
                encoding_result = chardet.detect(raw_data)
                encoding = encoding_result["encoding"]
                
                # Decode text using detected encoding
                text_content = raw_data.decode(encoding)
        else:
            text_content = ""
            for clip in clips.order_by("sequence"):
                text_content += clip.text + ' '

        # Generate a temp file for ElevenLabs
        import tempfile
        import os
        from django.core.files import File
        
        # Create temporary output file
        temp_audio_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        temp_audio_file.close()
        temp_audio_path = temp_audio_file.name
        
        # Generate voiceover using ElevenLabs
        handler = ElevenLabsHandler(
            api_key=video.elevenlabs_api_key
        )
        
        # Check credits before attempting generation
        if not handler.has_sufficient_credits(len(text_content)):
            # Clean up temp file before raising exception
            os.unlink(temp_audio_path)
            raise Exception("Insufficient credits to generate voiceover")
        if video.history_id:
            handler.get_history_audio(video.history_id, output_path=temp_audio_path)
        else:
            handler.generate_voiceover(text=text_content, output_path=temp_audio_path)
        
        # Save audio file to the video model using Django's File API
        with open(temp_audio_path, "rb") as f:
            video.audio_file.save(f"video_{video.id}_audio.mp3", File(f), save=True)
        
        # Clean up temp file
        os.unlink(temp_audio_path)
        
        return True
        
    except Exception as e:
        print(f"Error generating audio file: {str(e)}")
        # Re-raise the exception to be caught by the background processor
        raise e


# def generate_audio_file(video, user_id):
#     """
#     Generate audio file from text using ElevenLabs

#     Args:
#         video: Video object
#         user_id: User ID

#     Returns:
#         True if successful, False otherwise
#     """
#     try:
#         # Check for required fields
#         if not video.elevenlabs_api_key or not video.voice_id:
#             raise ValueError("ElevenLabs API key and voice ID are required")
        
#         clips = Clips.objects.filter(video=video)
#         if not clips.exists():
#             # Check if text file exists
#             if not video.text_file:
#                 raise ValueError("Text file not available")

#             # Read text using storage API instead of direct file access
#             from django.core.files.storage import default_storage
#             import chardet
            
#             # Read the file using Django's storage API
#             with default_storage.open(video.text_file.name, 'rb') as file:
#                 raw_data = file.read()
#                 # Detect encoding
#                 encoding_result = chardet.detect(raw_data)
#                 encoding = encoding_result["encoding"]
                
#                 # Decode text using detected encoding
#                 text_content = raw_data.decode(encoding)
#         else:
#             text_content = ""
#             for clip in clips.order_by("sequence"):
#                 # text_content += clip.text + '. '
#                 text_content += clip.text + '. '

#         # Generate a temp file for ElevenLabs
#         import tempfile
#         import os
#         from django.core.files import File
        
#         # Create temporary output file
#         temp_audio_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
#         temp_audio_file.close()
#         temp_audio_path = temp_audio_file.name
        
#         # Generate voiceover using ElevenLabs
#         handler = ElevenLabsHandler(
#             api_key=video.elevenlabs_api_key, voice_id=video.voice_id
#         )
#         handler.generate_voiceover(text=text_content, output_path=temp_audio_path)
        
#         # Save audio file to the video model using Django's File API
#         with open(temp_audio_path, "rb") as f:
#             # This will work with both local and S3 storage
#             video.audio_file.save(f"video_{video.id}_audio.mp3", File(f), save=True)
        
#         # Clean up temp file
#         os.unlink(temp_audio_path)
        
#         return True
#     except Exception as e:
#         print(f"Error generating audio file: {str(e)}")
#         return False
    
def generate_srt_file(video, user_id):
    """Generate SRT file from text and audio"""
    try:
        # Check if audio file exists
        if not video.audio_file:
            raise ValueError(f"Video #{video.id} doesn't have an audio file.")
        
        # Import necessary modules
        import tempfile
        import os
        from django.core.files import File
        from django.core.files.storage import default_storage
        
        # Create temporary files for processing
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_audio:
            # Download the audio file to the temp location
            with default_storage.open(video.audio_file.name, 'rb') as s3_file:
                temp_audio.write(s3_file.read())
            temp_audio_path = temp_audio.name
        
        # Get text content
        clips = Clips.objects.filter(video=video).order_by("sequence")
        if not clips.exists():
            if not video.text_file:
                raise ValueError(f"Video #{video.id} doesn't have text content.")
                
            # Read text using storage API instead of direct file access
            with default_storage.open(video.text_file.name, 'rb') as file:
                raw_data = file.read()
                # Detect encoding
                encoding_result = chardet.detect(raw_data)
                encoding = encoding_result["encoding"]
                # Decode text using detected encoding
                text = raw_data.decode(encoding)
        else:
            text = ""
            for clip in clips:
                text += clip.text + "\n"
                
        # Split text into words and join with newlines
        words = text.split()
        text_one_word_per_line = "\n".join(words)
        
        # Create a temp output JSON file
        tmp_json = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        tmp_json.close()
        json_path = tmp_json.name
        
        # Generate SRT file from text and audio
        aligner = ElevenLabsTextAlignment(AppVariables.objects.get(key="ELEVENLABS_ALIGNMENT_KEY").value)
        srt_path = aligner.align_text_with_audio(
            script=text_one_word_per_line,
            output_json_path=json_path,
            audio_path=temp_audio_path,  # Use the temporary audio file
        )
        
        # Save the SRT file to the model
        if srt_path and os.path.exists(srt_path):
            with open(srt_path, "rb") as srt_file:
                file_name = f"video_{video.id}_subtitles.srt"
                video.srt_file.save(file_name, ContentFile(srt_file.read()), save=True)
                
                # Clean up temp files
                os.unlink(temp_audio_path)
                os.unlink(json_path)
                if os.path.exists(srt_path) and srt_path != json_path:
                    os.unlink(srt_path)
                
                return True
                
        # Clean up temp files
        os.unlink(temp_audio_path)
        if os.path.exists(json_path):
            os.unlink(json_path)
            
        print(f"Failed to generate SRT file for video #{video.id}")
        return False
    except Exception as e:
        print(f"Error generating SRT file: {str(e)}")
        return False
    
def update_clip_timings_from_alignment(video, alignment_data):
    """
    Update clip timings based on audio-text alignment data

    Args:
        video: Video object
        alignment_data: Alignment data from TextAudioAligner
    """
    # Get all clips
    clips = Clips.objects.filter(video=video).order_by("id")

    if not clips.exists():
        return

    # Extract fragments from alignment data
    fragments = alignment_data.get("fragments", [])

    # Match clips to fragments based on text content
    for clip in clips:
        clip_text = clip.text.lower().strip()

        # Find matching fragment(s) for this clip
        matching_fragments = []
        for fragment in fragments:
            fragment_text = (
                fragment.get("text", "").lower().strip()
                or " ".join(fragment.get("lines", [])).lower().strip()
            )

            if fragment_text in clip_text or clip_text in fragment_text:
                matching_fragments.append(fragment)

        # If we found matching fragments, update the clip timing
        if matching_fragments:
            # Use the earliest start time and latest end time
            start_time = min(
                float(fragment.get("begin", 0)) for fragment in matching_fragments
            )
            end_time = max(
                float(fragment.get("end", 0)) for fragment in matching_fragments
            )

            # Update clip
            clip.start_time = start_time
            clip.end_time = end_time
            clip.save()

            # Update any subclips proportionally within the new clip timing
            subclips = Subclip.objects.filter(clip=clip).order_by("id")
            if subclips.exists():
                # Calculate new duration
                new_duration = end_time - start_time

                for subclip in subclips:
                    # Distribute evenly if we don't have existing timings
                    if subclip.start_time is None or subclip.end_time is None:
                        count = subclips.count()
                        subclip_idx = list(subclips).index(subclip)
                        segment_duration = new_duration / count

                        subclip.start_time = start_time + (
                            segment_duration * subclip_idx
                        )
                        subclip.end_time = subclip.start_time + segment_duration
                    else:
                        # Adjust existing timings proportionally
                        rel_start = (subclip.start_time - clip.start_time) / (
                            clip.end_time - clip.start_time
                        )
                        rel_end = (subclip.end_time - clip.start_time) / (
                            clip.end_time - clip.start_time
                        )

                        subclip.start_time = start_time + (rel_start * new_duration)
                        subclip.end_time = start_time + (rel_end * new_duration)

                    subclip.save()


def format_srt_time(seconds):
    """
    Format time in seconds to SRT format (HH:MM:SS,mmm)

    Args:
        seconds: Time in seconds

    Returns:
        Formatted time string
    """
    # Handle negative time (shouldn't happen, but just in case)
    seconds = max(0, seconds)

    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = seconds % 60
    milliseconds = int((seconds - int(seconds)) * 1000)

    return f"{hours:02d}:{minutes:02d}:{int(seconds):02d},{milliseconds:03d}"

def update_clip_timings(video):
    """
    Update clip and subclip start and end times based on audio file duration

    Args:
        video: Video object

    Returns:
        True if successful, False otherwise
    """
    try:
        # Check if audio file exists
        if not video.audio_file:
            raise ValueError("Audio file not available")

        # Import necessary modules
        import tempfile
        import os
        import subprocess
        from django.core.files.storage import default_storage
        
        # Create temporary file for processing
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_audio:
            # Download the audio file to the temp location
            with default_storage.open(video.audio_file.name, 'rb') as s3_file:
                temp_audio.write(s3_file.read())
            temp_audio_path = temp_audio.name

        # Get audio duration using ffprobe
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            temp_audio_path,
        ]
        audio_duration = float(subprocess.check_output(cmd).decode("utf-8").strip())

        # Get all clips
        clips = Clips.objects.filter(video=video).order_by("id")

        if not clips.exists():
            # Clean up temp file
            os.unlink(temp_audio_path)
            raise ValueError("No clips found")

        # Calculate time per clip
        clip_count = clips.count()
        time_per_clip = audio_duration / clip_count

        # Update clip timings
        current_time = 0.0
        for clip in clips:
            # Set start and end time
            clip.start_time = current_time
            clip.end_time = current_time + time_per_clip
            clip.save()

            # Update subclips for this clip
            subclips = Subclip.objects.filter(clip=clip).order_by("id")
            if subclips.exists():
                # If subclips exist, distribute them within clip's time range
                subclip_count = subclips.count()
                time_per_subclip = time_per_clip / subclip_count

                subclip_time = current_time
                for subclip in subclips:
                    subclip.start_time = subclip_time
                    subclip.end_time = subclip_time + time_per_subclip
                    subclip.save()
                    subclip_time += time_per_subclip

            current_time += time_per_clip

        # Clean up temp file
        os.unlink(temp_audio_path)
        
        return True
    except Exception as e:
        print(f"Error updating clip timings: {str(e)}")
        return False
def generate_clips_from_text_file(video: Video):
    """Generate clips from text file"""
    import chardet
    import re
    from django.core.files.storage import default_storage
    
    Clips.objects.filter(video=video).delete()  # Clear existing clips
    if not video.text_file:
        return

    # Use storage API instead of direct file access
    try:
        # Read the file using Django's storage API
        with default_storage.open(video.text_file.name, 'rb') as file:
            raw_data = file.read()
            # Detect encoding
            encoding_result = chardet.detect(raw_data)
            encoding = encoding_result["encoding"]
            
            # Decode text using detected encoding
            text_content = raw_data.decode(encoding)
    except Exception as e:
        print(f"Error reading text file: {str(e)}")
        raise

    # Split text into sentences (basic split by periods, question marks, exclamation marks)
    # sentences = re.split(r"(?<=[.])\s+|\n+", text_content.strip())
    sentences = re.split(r"\n", text_content.strip())


    # Create clips for each sentence
    clips_created = 0
    for sentence in sentences:
        # Create clip
        clip = Clips.objects.create(
            video=video,
            start_time=clips_created
            * 5,  # Example: each clip starts at intervals of 5 seconds
            end_time=(clips_created + 1) * 5,
            text=sentence,
            sequence=clips_created + 1,  # Optional: sequence number for ordering
        )
        clips_created += 1

    return clips_created


# def generate_clips_from_srt(video):
#     """Update existing clips with timing information from SRT file"""
#     try:
#         # Import necessary modules
#         import tempfile
#         import os
#         import json
#         from django.core.files.storage import default_storage
        
#         if not video.srt_file:
#             raise ValueError(f"Video #{video.id} doesn't have an SRT file.")

#         # Get all existing clips
#         clips = list(Clips.objects.filter(video=video).order_by("sequence"))
#         if not clips:
#             raise ValueError(f"No clips found for video #{video.id}.")

#         # Download SRT file to temporary location
#         with tempfile.NamedTemporaryFile(delete=False, suffix=".srt") as temp_srt:
#             # Download the SRT file
#             with default_storage.open(video.srt_file.name, 'rb') as s3_file:
#                 temp_srt.write(s3_file.read())
#             srt_file_path = temp_srt.name

#         # Read SRT file as JSON
#         with open(srt_file_path, "r", encoding="utf-8") as file:
#             srt_data = json.load(file)

#         # Clean up temp file
#         os.unlink(srt_file_path)

#         # Extract all words from SRT fragments
#         all_words = []
#         for fragment in srt_data.get("fragments", []):
#             begin_time = float(fragment.get("begin", "0"))
#             end_time = float(fragment.get("end", "0"))
#             word = " ".join(fragment.get("lines", []))
#             if word:
#                 all_words.append({"word": word, "begin": begin_time, "end": end_time})

#         # Update each clip
#         word_index = 0  # Track our position in all_words

#         for clip in clips:
#             clip_text = clip.text
#             clip_words = clip_text.split()
#             clip_start_time = None
#             clip_end_time = None
#             words_matched = 0

#             # Start from the current position in all_words
#             temp_word_index = word_index
#             while temp_word_index < len(all_words) and words_matched < len(clip_words):
#                 word_data = all_words[temp_word_index]
#                 srt_word = word_data["word"].lower()

#                 if srt_word == clip_words[words_matched].lower():
#                     if clip_start_time is None:
#                         clip_start_time = word_data["begin"]

#                     clip_end_time = word_data["end"]
#                     words_matched += 1

#                 temp_word_index += 1

#             # If we've found all words in the clip
#             if (
#                 words_matched > 0
#                 and clip_start_time is not None
#                 and clip_end_time is not None
#             ):
#                 clip.start_time = clip_start_time
#                 clip.end_time = clip_end_time
#                 clip.save()
#                 word_index = temp_word_index  # Update our position for the next clip

#         # Adjust clip times: first clip starts at 0, each clip ends at the start of the next
#         clips = list(Clips.objects.filter(video=video).order_by("start_time"))
#         if clips:
#             # Set first clip to start at 0
#             first_clip = clips[0]
#             first_clip.start_time = 0
#             first_clip.save()

#             # Adjust each clip to end at the start of the next clip
#             for i in range(len(clips) - 1):
#                 current_clip = clips[i]
#                 next_clip = clips[i + 1]
#                 current_clip.end_time = next_clip.start_time
#                 current_clip.save()

#         return len(clips)
#     except Exception as e:
#         print(f"Error in generate_clips_from_srt: {str(e)}")
#         raise

def generate_clips_from_srt(video):
    """
    Update existing clips with timing information from SRT file using the sophisticated
    matching algorithm from configure_subclip. Handles repeated sentences by maintaining
    proper sequence order in matching.
    """
    import json
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        if not video.srt_file:
            raise ValueError(f"Video #{video.id} doesn't have an SRT file.")

        # Get all existing clips
        clips = list(Clips.objects.filter(video=video).order_by("sequence"))
        if not clips:
            raise ValueError(f"No clips found for video #{video.id}.")

        # Load the SRT JSON content
        try:
            with video.srt_file.open('r') as srt_file:
                srt_data = json.load(srt_file)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error reading SRT file: {e}")
            raise ValueError(f"Could not read SRT file for video #{video.id}: {e}")
        
        # Get all fragments sorted by begin time
        all_fragments = sorted(
            srt_data.get('fragments', []), 
            key=lambda x: float(x.get('begin', 0))
        )
        
        if not all_fragments:
            raise ValueError(f"No fragments found in SRT file for video #{video.id}")
        
        logger.info(f"Total fragments in SRT: {len(all_fragments)}")
        
        # Concatenate all fragment texts to form a full transcript
        full_transcript = ""
        fragment_positions = []  # Track which fragment each position belongs to
        
        for j, fragment in enumerate(all_fragments):
            fragment_text = ' '.join(fragment.get('lines', [])).lower()
            fragment_positions.extend([j] * (len(fragment_text) + 1))  # +1 for the space
            full_transcript += fragment_text + " "
            
        full_transcript = full_transcript.strip()
        
        # If transcript is longer than our positions mapping, trim the positions
        if len(fragment_positions) > len(full_transcript):
            fragment_positions = fragment_positions[:len(full_transcript)]
        
        # Keep track of where we last found a match to handle repeated sentences
        last_matched_position = 0
        
        # First pass: Match clips to fragments using the sophisticated text matching algorithm
        updated_clips = 0
        
        for i, clip in enumerate(clips):
            # The first clip always starts at time 0
            if i == 0:
                clip.start_time = 0
                updated_clips += 1
            else:
                # Process clip text matching
                clip_text = clip.text.lower().strip()
                
                # For repeated sentences, search only from the last matched position
                search_transcript = full_transcript[last_matched_position:]
                
                # Find the clip text in the remaining transcript - exact match
                if clip_text in search_transcript:
                    # Find the start and end positions relative to the search segment
                    rel_start_pos = search_transcript.find(clip_text)
                    rel_end_pos = rel_start_pos + len(clip_text) - 1
                    
                    # Convert to absolute positions in the full transcript
                    start_pos = last_matched_position + rel_start_pos
                    end_pos = last_matched_position + rel_end_pos
                    
                    # Get the corresponding fragments
                    if 0 <= start_pos < len(fragment_positions) and 0 <= end_pos < len(fragment_positions):
                        start_fragment_index = fragment_positions[start_pos]
                        end_fragment_index = fragment_positions[end_pos]
                        
                        # Set the start time 
                        start_fragment = all_fragments[start_fragment_index]
                        clip.start_time = float(start_fragment.get('begin', 0))
                        logger.debug(f"Clip #{clip.id}: matched text exactly, start time: {clip.start_time}")
                        
                        # Update the last matched position to the end of this match
                        # This ensures we don't match the same text twice
                        last_matched_position = end_pos + 1
                        
                        updated_clips += 1
                    else:
                        logger.warning(f"Clip #{clip.id}: Match found but position out of bounds")
                else:
                    # Fallback method - partial matching
                    logger.debug(f"Clip #{clip.id}: exact match not found, trying partial matching...")
                    
                    # Only consider fragments that come after the last matched position
                    last_fragment_index = -1
                    if last_matched_position < len(fragment_positions):
                        last_fragment_index = fragment_positions[last_matched_position]
                    
                    # Get fragments that appear after our last match
                    candidate_fragments = []
                    if last_fragment_index >= 0:
                        candidate_fragments = all_fragments[last_fragment_index:]
                    else:
                        candidate_fragments = all_fragments
                    
                    matching_fragments = []
                    
                    for fragment in candidate_fragments:
                        fragment_text = ' '.join(fragment.get('lines', [])).lower()
                        
                        # Check if the fragment text is in the clip or vice versa
                        if fragment_text in clip_text or clip_text in fragment_text:
                            matching_fragments.append(fragment)
                    
                    if matching_fragments:
                        # Sort matching fragments by start time
                        matching_fragments.sort(key=lambda x: float(x.get('begin', 0)))
                        
                        # Set start time to the first matching fragment
                        clip.start_time = float(matching_fragments[0].get('begin', 0))
                        logger.debug(f"Clip #{clip.id}: matched text partially, start time: {clip.start_time}")
                        
                        # Get the last matching fragment
                        last_match = matching_fragments[-1]
                        
                        # Find this fragment's index in the original list
                        for idx, fragment in enumerate(all_fragments):
                            if fragment.get('id') == last_match.get('id'):
                                # Update last_matched_position based on the index of this fragment
                                # in the original transcript
                                for pos, frag_idx in enumerate(fragment_positions):
                                    if frag_idx > idx:
                                        last_matched_position = pos
                                        break
                                break
                        
                        updated_clips += 1
                    else:
                        logger.warning(f"Clip #{clip.id}: No match found, start time might be incorrect")
            
            # Save the clip with its new start time
            clip.save()
        
        # Second pass: Adjust end times so each clip ends at the start of the next clip
        clips = list(Clips.objects.filter(video=video).order_by("sequence"))
        
        for i in range(len(clips) - 1):
            current_clip = clips[i]
            next_clip = clips[i + 1]
            
            # Set the current clip's end time to the next clip's start time
            current_clip.end_time = next_clip.start_time
            current_clip.save()
            
        # Set the last clip's end time to the end of its last matching fragment or the video duration
        if clips:
            last_clip = clips[-1]
            # If we don't have an end time yet, try to determine it from SRT
            if last_clip.end_time is None:
                # Use the last fragment's end time as a fallback
                last_fragment = all_fragments[-1]
                last_clip.end_time = float(last_fragment.get('end', 0))
                last_clip.save()
            
            # Set video_end_time for all clips
            video_end_time = last_clip.end_time
            for clip in clips:
                clip.video_end_time = video_end_time
                clip.save()
        

        for subclip in Subclip.objects.filter(clip__video=video):
            subclip.save()
        return updated_clips
        
    except Exception as e:
        logger.error(f"Error in generate_clips_from_srt: {str(e)}")
        raise

def process_background_music(video):
    """
    Process background music for a video

    Args:
        video: Video object

    Returns:
        List of processed background music file paths
    """
    try:
        # Import necessary modules
        import tempfile
        import os
        import subprocess
        import logging
        from django.core.files.storage import default_storage
        
        # Get all background music items for this video
        bg_music_items = BackgroundMusic.objects.filter(video=video).order_by(
            "start_time"
        )

        if not bg_music_items.exists():
            return []

        processed_paths = []

        for item in bg_music_items:
            # Check if we need to download the music file from URL
            if not item.audio_file:
                continue

            # Download audio file to temporary location
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_audio:
                # Download the audio file
                with default_storage.open(item.audio_file.name, 'rb') as s3_file:
                    temp_audio.write(s3_file.read())
                audio_file_path = temp_audio.name

            # Create a temporary file for the processed audio
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp_file:
                output_path = tmp_file.name

            # Use ffmpeg to trim the audio file if needed
            duration = item.end_time - item.start_time
            if duration > 0:
                cmd = [
                    "ffmpeg",
                    "-y",  # Overwrite output file if it exists
                    "-i",
                    audio_file_path,
                    "-ss",
                    str(item.start_time),  # Start time
                    "-t",
                    str(duration),  # Duration
                    "-c:a",
                    "libmp3lame",  # Audio codec
                    "-q:a",
                    "2",  # Audio quality
                    output_path,
                ]

                subprocess.run(cmd, check=True)
                processed_paths.append(output_path)
                
                # Clean up original temp file
                os.unlink(audio_file_path)
            else:
                # Just use the downloaded file if no trimming is needed
                processed_paths.append(audio_file_path)

        return processed_paths
    except Exception as e:
        logging.error(f"Error processing background music: {str(e)}")
        return []


def add_background_music(
    video, music_url=None, music_file=None, start_time=0, end_time=None
):
    """
    Add background music to a video from URL or file

    Args:
        video: Video object
        music_url: URL to download music from (optional)
        music_file: Uploaded music file (optional)
        start_time: Start time in seconds (default: 0)
        end_time: End time in seconds (optional)

    Returns:
        BackgroundMusic object if successful, None otherwise
    """
    try:
        if not music_url and not music_file:
            raise ValueError("Either music_url or music_file must be provided")

        # Import necessary modules
        import tempfile
        import os
        import subprocess
        import requests
        import hashlib
        import datetime
        from urllib.parse import urlparse
        from django.core.files import File
        from django.core.files.temp import NamedTemporaryFile
        from django.core.files.storage import default_storage
        
        # No need to create directories explicitly in S3
        # Generate a unique filename
        file_hash = hashlib.md5(
            f"{video.id}_{datetime.datetime.now()}".encode()
        ).hexdigest()[:10]
        output_filename = f"bg_music_{video.id}_{file_hash}.mp3"

        # Get file from URL or uploaded file
        if music_url:
            # Download file from URL
            response = requests.get(music_url, stream=True)
            if response.status_code != 200:
                raise ValueError(
                    f"Failed to download music from URL: {response.status_code}"
                )

            # Extract filename from URL if possible
            url_path = urlparse(music_url).path
            orig_filename = os.path.basename(url_path) or output_filename

            # Save to temporary file
            with NamedTemporaryFile(delete=False, suffix=".mp3") as tmp_file:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        tmp_file.write(chunk)
                temp_path = tmp_file.name

            # Get audio duration using ffprobe
            cmd = [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                temp_path,
            ]
            audio_duration = float(subprocess.check_output(cmd).decode("utf-8").strip())

            # Create BackgroundMusic object
            bg_music = BackgroundMusic.objects.create(
                video=video, start_time=start_time, end_time=end_time or audio_duration
            )

            # Save the file to the model
            with open(temp_path, "rb") as f:
                bg_music.audio_file.save(output_filename, File(f))

            # Clean up temp file
            os.unlink(temp_path)

        else:  # music_file is provided
            # Get file duration using ffprobe
            with NamedTemporaryFile(delete=False) as tmp_file:
                for chunk in music_file.chunks():
                    tmp_file.write(chunk)
                temp_path = tmp_file.name

            cmd = [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                temp_path,
            ]
            audio_duration = float(subprocess.check_output(cmd).decode("utf-8").strip())

            # Create BackgroundMusic object
            bg_music = BackgroundMusic.objects.create(
                video=video, start_time=start_time, end_time=end_time or audio_duration
            )

            # Save the file to the model
            bg_music.audio_file.save(output_filename, music_file)

            # Clean up temp file
            os.unlink(temp_path)

        return bg_music
    except Exception as e:
        import logging
        logging.error(f"Error adding background music: {str(e)}")
        return None
    generate_clips_from_srt
def apply_background_music(video, video_path):
    """
    Apply background music to the video

    Args:
        video: Video object
        video_path: Path to the video file

    Returns:
        Path to the output video file with background music
    """
    try:
        # Import necessary modules
        import tempfile
        import os
        import subprocess
        import logging
        from django.core.files.storage import default_storage
        
        # Get background music items
        bg_music_items = BackgroundMusic.objects.filter(video=video).order_by(
            "start_time"
        )

        if not bg_music_items.exists():
            return video_path

        # Create temporary directory for processing
        temp_dir = tempfile.mkdtemp(prefix="videocrafter_temp_")

        # Get video duration
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            video_path,
        ]
        video_duration = float(subprocess.check_output(cmd).decode("utf-8").strip())

        # Create a silent audio track for the full video duration
        silence_path = os.path.join(temp_dir, "silence.mp3")
        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=r=44100:cl=stereo:d={video_duration}",
            "-c:a",
            "libmp3lame",
            silence_path,
        ]
        subprocess.run(cmd, check=True)

        # Process each background music file
        audio_inputs = [silence_path]
        audio_maps = []
        filter_complex = []

        for i, item in enumerate(bg_music_items):
            if not item.audio_file:
                continue

            # Download audio file to temporary location
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_audio:
                # Download the audio file
                with default_storage.open(item.audio_file.name, 'rb') as s3_file:
                    temp_audio.write(s3_file.read())
                audio_file_path = temp_audio.name

            # Create temp file for processed audio
            processed_audio_path = os.path.join(temp_dir, f"bg_music_{i}.mp3")

            # Trim audio if needed
            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                audio_file_path,
                "-ss",
                str(item.start_time),
            ]

            # Add duration if specified
            if item.end_time:
                duration = item.end_time - item.start_time
                cmd.extend(["-t", str(duration)])

            # Output options
            cmd.extend(["-c:a", "libmp3lame", "-q:a", "2", processed_audio_path])

            subprocess.run(cmd, check=True)
            
            # Clean up original temp file
            os.unlink(audio_file_path)

            # Add audio input
            audio_inputs.append(processed_audio_path)
            audio_maps.append(f"[a{i+1}]")

            # Create filter for this audio (start at specific time, fade in/out)
            filter_complex.append(
                f"[{i+1}:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo,volume=0.3[a{i+1}]"
            )

        # Generate the output path
        output_path = os.path.join(temp_dir, f"output_with_music_{video.id}.mp4")

        # Create the ffmpeg command
        cmd = ["ffmpeg", "-y", "-i", video_path]

        # Add audio input files
        for audio_path in audio_inputs:
            cmd.extend(["-i", audio_path])

        # Add filter complex
        filter_str = ";".join(filter_complex)

        # Add mixing filter for all audio streams
        if audio_maps:
            filter_str += f";[0:a]{' '.join(audio_maps)}amix=inputs={len(audio_maps)+1}:duration=longest[aout]"
            cmd.extend(["-filter_complex", filter_str, "-map", "0:v", "-map", "[aout]"])
        else:
            cmd.extend(["-map", "0:v", "-map", "0:a"])

        # Add output options
        cmd.extend(["-c:v", "copy", "-c:a", "aac", "-b:a", "192k", output_path])

        # Execute ffmpeg command
        subprocess.run(cmd, check=True)

        return output_path
    except Exception as e:
        logging.error(f"Error applying background music: {str(e)}")
        return video_path  # Return the original video path if there's an error

def generate_signed_url_for_upload(s3_key, expires_in=3600):
    """
    Generate a signed URL for an S3 object, fallback if not exists.
    
    Args:
        s3_key: The S3 object key
        expires_in: URL expiration time in seconds (default: 1 hour)
        
    Returns:
        Signed URL if successful, direct URL if object not found, None on error
    """
    try:
        from django.conf import settings
        import boto3
        
        # Initialize the S3 client using settings from Django settings
        s3_client = boto3.client('s3', region_name='eu-west-2')

        # Now define the bucket and object key
        bucket_name = 'admultiplier'
        print("--- s3 key ---")
        print(s3_key)
        object_key = s3_key
        # Generate the signed URL
        signed_url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': bucket_name,
                'Key': "media/" + object_key
            },
            ExpiresIn=3600  # Valid for 1 hour
        )
        return signed_url
    except Exception as e:
        import logging
        
        # Check if this is a 404 error (object not found)
        if hasattr(e, 'response') and e.response.get('Error', {}).get('Code') == '404':
            logging.warning(f"S3 404: {s3_key} not found, falling back to direct URL.")
            from django.conf import settings
            region = getattr(settings, 'AWS_REGION', 'eu-west-2')
            bucket = getattr(settings, 'AWS_STORAGE_BUCKET_NAME', 'admultiplier')
            return f"https://{bucket}.s3.{region}.amazonaws.com/{s3_key}"
        else:
            logging.error(f"Error generating signed URL for {s3_key}: {str(e)}")
            return None
        
def generate_signed_url(s3_key, expires_in=3600):
    """
    Generate a pre-signed URL for an S3 object
    
    Args:
        s3_key (str): The S3 key of the object
        expires_in (int): Expiration time in seconds, default is 1 hour
        
    Returns:
        str: The pre-signed URL
    """
    try:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION
        )
        
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': settings.AWS_STORAGE_BUCKET_NAME,
                'Key': s3_key
            },
            ExpiresIn=expires_in
        )
        
        return url
    except Exception as e:
        print(f"Error generating signed URL for {s3_key}: {str(e)}")
        return None

def process_video_watermarks(video_id, bg_music=False):
    """
    Utility function to process watermarks for a video
    
    Args:
        video_id: ID of the video to process
        
    Returns:
        dict: Status information
    """
    from .services.runpod_videoprocessor import RunPodVideoProcessor

    try:
        video = Video.objects.get(id=video_id)
        processor = RunPodVideoProcessor(video_id)
        
        # Submit watermark jobs
        print("Submitting watermark jobs...")
        result = processor.watermark_videos(video, bg_music=bg_music)
        
        # Process results for regular video
        if result.get("regular_video") and result["regular_video"].get("success"):
            regular_job_id = result["regular_video"]["job_id"]
            processor.process_watermark_result(video, regular_job_id, is_bg=False)
        
        # Process results for background music video
        if result.get("bg_video") and result["bg_video"].get("success"):
            bg_job_id = result["bg_video"]["job_id"]
            processor.process_watermark_result(video, bg_job_id, is_bg=True)
        
        return result
    except Video.DoesNotExist:
        return {"success": False, "error": "Video not found"}
    except Exception as e:
        return {"success": False, "error": str(e)}


    try:
        # Save uploaded file to a temporary location
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_file:
            for chunk in video_file.chunks():
                temp_file.write(chunk)
            temp_file_path = temp_file.name

        # Create temp output file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as output_file:
            processed_video_path = output_file.name

        # FFmpeg command
        ffmpeg_cmd = [
            "ffmpeg", "-y", "-i", temp_file_path,
            "-filter_complex",
            f"[0:v]setpts={1/speed}*PTS[v];[0:a]atempo={speed}[a]",
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "fast", "-c:a", "aac", "-b:a", "192k",
            processed_video_path
        ]

        # Run FFmpeg
        subprocess.run(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

        return processed_video_path

    except subprocess.CalledProcessError as e:
        print(f"FFmpeg error: {e.stderr.decode()}")
        return None




def clean_text_for_alignment(text: str) -> str:
    # Remove symbols surrounded by spaces (e.g. " ? ")
    text = re.sub(r'\s[^\w\s]+\s', ' ', text)
    # Remove symbols preceded by space at end (e.g. "word !")
    text = re.sub(r'\s[^\w\s]+$', '', text)
    # Remove symbols followed by space at start (optional, e.g. "! hello")
    text = re.sub(r'^[^\w\s]+\s', '', text)
    text = text.replace("-", " ")  # Replace double hyphens with space

    # Normalize whitespace and lowercase
    return ' '.join(text.lower().split())


