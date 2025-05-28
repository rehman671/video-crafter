from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
import json
import os
import tempfile
import logging
from django.core.files import File
import subprocess  # Add this import

from apps.processors.models import Subclip, Clips, BackgroundMusic, Video, ProcessingStatus
from apps.processors.services.video_processor import VideoProcessorService, Video
import time
import traceback


logger = logging.getLogger(__name__)

# @receiver(pre_save, sender=Subclip)
# def configure_subclip(sender, instance:Subclip, **kwargs):
#     """
#     Calculate start and end times for a subclip based on its text content.
#     The end time will be the start time of the next fragment when available.
#     """
#     # Check if this is an existing instance being updated
#     if instance.pk:
#         try:
#             original = Subclip.objects.get(pk=instance.pk)
#             # If text changed, reset timings to recalculate
#             if original.text != instance.text:
#                 instance.start_time = None
#                 instance.end_time = None
#         except Subclip.DoesNotExist:
#             pass
    
#     # If the text is the same as the clip's text, use clip's times
#     # if instance.clip.text.strip() == instance.text.strip():
#     #     instance.start_time = instance.clip.start_time
#     #     instance.end_time = instance.clip.end_time
#     #     return
    
#     # Process the SRT file to find matching fragments
#     clip = instance.clip        
#     video = clip.video
#     if not video.srt_file:
#         return
    
#     try:
#         # Load the SRT JSON content
#         print(video.id)
#         with video.srt_file.open('r') as srt_file:
#             srt_data = json.load(srt_file)
        
#         # Get all fragments sorted by begin time
#         all_fragments = sorted(srt_data.get('fragments', []), key=lambda x: float(x.get('begin', 0)))
#         print(f"Total fragments in SRT: {len(all_fragments)}")
        
#         # Get subclip text in lowercase for comparison
#         subclip_text = instance.text.lower().strip()
        
#         # Concatenate all fragment texts to form a transcript
#         full_transcript = ""
#         fragment_positions = []  # Keep track of which fragment each position belongs to
        
#         for i, fragment in enumerate(all_fragments):
#             fragment_text = ' '.join(fragment.get('lines', [])).lower()
#             fragment_positions.extend([i] * (len(fragment_text) + 1))  # +1 for the space
#             full_transcript += fragment_text + " "
            
#         full_transcript = full_transcript.strip()
        
#         # If transcript is longer than our positions mapping, trim the positions
#         if len(fragment_positions) > len(full_transcript):
#             fragment_positions = fragment_positions[:len(full_transcript)]
        
#         print(f"Full transcript: '{full_transcript}'")
#         print(f"Searching for: '{subclip_text}'")
#         print("-----------------------------------")
#         print(srt_data)
#         print("-----------------------------------")
#         # Find the subclip text in the transcript
#         if subclip_text in full_transcript:
#             # Find the start and end positions
#             start_pos = full_transcript.find(subclip_text)
#             end_pos = start_pos + len(subclip_text) - 1
            
#             # Get the corresponding fragments
#             if 0 <= start_pos < len(fragment_positions) and 0 <= end_pos < len(fragment_positions):
#                 start_fragment_index = fragment_positions[start_pos]
#                 end_fragment_index = fragment_positions[end_pos]
                
#                 # Set the start time
#                 start_fragment = all_fragments[start_fragment_index]
#                 instance.start_time = float(start_fragment.get('begin', 0))
#                 print(f"Start fragment: {start_fragment.get('lines')} at {instance.start_time}")
                
#                 # Set the end time
#                 end_fragment = all_fragments[end_fragment_index]
#                 end_fragment_id = end_fragment.get('id')
#                 print(f"End fragment ID: {end_fragment_id}, text: {end_fragment.get('lines')}")
                
#                 # Find the next fragment that actually starts after this one ends
#                 end_fragment_end_time = float(end_fragment.get('end', 0))
#                 next_fragment = None
                
#                 for i in range(end_fragment_index + 1, len(all_fragments)):
#                     potential_next = all_fragments[i]
#                     if float(potential_next.get('begin', 0)) >= end_fragment_end_time:
#                         next_fragment = potential_next
#                         break
                
#                 if next_fragment:
#                     # Use the start time of the next fragment that starts after this one ends
#                     instance.end_time = float(next_fragment.get('begin', 0))
#                     print( float(next_fragment.get('begin', 0)))
#                     print(f"End time set to next fragment start: {instance.end_time}, ID: {next_fragment.get('id')}, text: {next_fragment.get('lines')}")
#                 else:
#                     # Use the end time of the current fragment
#                     instance.end_time = end_fragment_end_time
#                     print(f"No next fragment after this one ends, using current end: {instance.end_time}")
                
#                 return
        
#         # Fallback method - try partial matching
#         print("Exact match not found, trying partial matching...")
#         matching_fragments = []
        
#         for fragment in all_fragments:
#             fragment_text = ' '.join(fragment.get('lines', [])).lower()
            
#             # Check if the fragment text is in the subclip or vice versa
#             if fragment_text in subclip_text or subclip_text in fragment_text:
#                 matching_fragments.append(fragment)
        
#         if matching_fragments:
#             # Sort matching fragments by start time
#             matching_fragments.sort(key=lambda x: float(x.get('begin', 0)))
            
#             # Set start time to the first matching fragment
#             instance.start_time = float(matching_fragments[0].get('begin', 0))
            
#             # Get the last matching fragment's index in the full list
#             last_match = matching_fragments[-1]
#             last_match_index = -1
            
#             for i, fragment in enumerate(all_fragments):
#                 if fragment.get('id') == last_match.get('id'):
#                     last_match_index = i
#                     break
            
#             # Set end time
#             if last_match_index + 1 < len(all_fragments):
#                 # Use start time of next fragment
#                 next_fragment = all_fragments[last_match_index + 1]
#                 instance.end_time = float(next_fragment.get('begin', 0))
#                 print(f"Partial match: using next fragment start: {instance.end_time}")
#             else:
#                 # Use end time of last matching fragment
#                 instance.end_time = float(last_match.get('end', 0))
#                 print(f"Partial match: no next fragment, using last fragment end: {instance.end_time}")
    
#     except (json.JSONDecodeError, IOError, ValueError) as e:
#         logger.error(f"Error processing SRT file: {e}")



# from django.db.models import Min

# @receiver(pre_save, sender=Subclip)
# def configure_subclip(sender, instance:Subclip, **kwargs):
#     """
#     Calculate start and end times for a subclip based on its text content.
#     The end time will be the start time of the next fragment when available.
#     The first subclip of a clip will have a start time based on its position.
#     """
#     # Check if this is the first subclip for this clip
#     is_first_subclip = False
#     try:
#         # Get all subclips for this clip, ordered by sequence
#         existing_subclips = Subclip.objects.filter(clip=instance.clip).order_by('sequence')
        
#         # Check if this subclip has the minimum sequence value for this clip
#         min_sequence = existing_subclips.aggregate(Min('sequence'))['sequence__min']
        
#         # If this is a new subclip (no pk) and there are no other subclips, it's the first one
#         if not instance.pk and not existing_subclips.exists():
#             is_first_subclip = True
#         # If this is a new subclip and its sequence is less than the minimum existing sequence
#         elif not instance.pk and min_sequence is not None and instance.sequence < min_sequence:
#             is_first_subclip = True
#         # If this is updating an existing subclip, check if it has the minimum sequence
#         elif instance.pk and min_sequence is not None and instance.sequence == min_sequence:
#             is_first_subclip = True
#     except:
#         # If any error occurs during this check, we'll proceed with regular processing
#         pass
            
#     # Check if this is an existing instance being updated
#     if instance.pk:
#         try:
#             original = Subclip.objects.get(pk=instance.pk)
#             # If text changed, reset timings to recalculate
#             if original.text != instance.text:
#                 instance.start_time = None
#                 instance.end_time = None
#         except Subclip.DoesNotExist:
#             pass
    
#     # Set start_time to 0 for first subclip and skip SRT processing for start_time
#     if is_first_subclip is True:
#         instance.start_time = 0
        
#     # Process the SRT file to find matching fragments
#     clip = instance.clip        
#     video = clip.video
#     if not video.srt_file:
#         return
    
#     try:
#         # Load the SRT JSON content
#         print(f"Processing video ID: {video.id}")
#         with video.srt_file.open('r') as srt_file:
#             srt_data = json.load(srt_file)
        
#         # Calculate threshold based on previous subclips
#         threshold = (
#             Subclip.objects
#             .filter(clip=instance.clip, sequence__lt=instance.sequence)
#             .order_by('sequence')
#             .last()
#             .end_time
#             if Subclip.objects.filter(clip=instance.clip, sequence__lt=instance.sequence).exists()
#             else 0
#         )
#         print(f"Threshold for subclip: {threshold}")
        
#         # Convert threshold to float if needed
#         threshold = 0 if threshold is None else threshold
#         threshold = float(threshold)
        
#         # Filter fragments after the threshold
#         filtered_fragments = [
#             fragment for fragment in srt_data['fragments']
#             if float(fragment['begin']) >= threshold
#         ]

#         # Get all fragments sorted by begin time
#         all_fragments = sorted(filtered_fragments, key=lambda x: float(x.get('begin', 0)))

#         print(f"Total fragments in SRT after threshold: {len(all_fragments)}")
        
#         # Get subclip text in lowercase for comparison
#         subclip_text = instance.text.lower().strip()
        
#         # Concatenate all fragment texts to form a transcript
#         full_transcript = ""
#         fragment_positions = []  # Keep track of which fragment each position belongs to
        
#         for i, fragment in enumerate(all_fragments):
#             fragment_text = ' '.join(fragment.get('lines', [])).lower()
#             fragment_positions.extend([i] * (len(fragment_text) + 1))  # +1 for the space
#             full_transcript += fragment_text + " "
            
#         full_transcript = full_transcript.strip()
        
#         # If transcript is longer than our positions mapping, trim the positions
#         if len(fragment_positions) > len(full_transcript):
#             fragment_positions = fragment_positions[:len(full_transcript)]
        
#         print(f"Full transcript: '{full_transcript}'")
#         print(f"Searching for: '{subclip_text}'")
#         print("-----------------------------------")
#         print(f"Filtered fragments count: {len(filtered_fragments)}")
#         print("-----------------------------------")
        
#         # Find the subclip text in the transcript
#         if subclip_text in full_transcript:
#             # Find the start and end positions
#             start_pos = full_transcript.find(subclip_text)
#             end_pos = start_pos + len(subclip_text) - 1
            
#             # Get the corresponding fragments
#             if 0 <= start_pos < len(fragment_positions) and 0 <= end_pos < len(fragment_positions):
#                 start_fragment_index = fragment_positions[start_pos]
#                 end_fragment_index = fragment_positions[end_pos]
                
#                 # Set the start time only if this is not the first subclip
#                 if not is_first_subclip:
#                     start_fragment = all_fragments[start_fragment_index]
#                     instance.start_time = float(start_fragment.get('begin', 0))
#                     print(f"Start fragment: {start_fragment.get('lines')} at {instance.start_time}")
                
#                 # Set the end time
#                 end_fragment = all_fragments[end_fragment_index]
#                 end_fragment_id = end_fragment.get('id')
#                 print(f"End fragment ID: {end_fragment_id}, text: {end_fragment.get('lines')}")
                
#                 # Find the next fragment that actually starts after this one ends
#                 end_fragment_end_time = float(end_fragment.get('end', 0))
#                 next_fragment = None
                
#                 for i in range(end_fragment_index + 1, len(all_fragments)):
#                     potential_next = all_fragments[i]
#                     if float(potential_next.get('begin', 0)) >= end_fragment_end_time:
#                         next_fragment = potential_next
#                         break
                
#                 if next_fragment:
#                     # Use the start time of the next fragment that starts after this one ends
#                     instance.end_time = float(next_fragment.get('begin', 0))
#                     print(f"End time set to next fragment start: {instance.end_time}")
#                     print(f"Next fragment ID: {next_fragment.get('id')}, text: {next_fragment.get('lines')}")
#                 else:
#                     # Use the end time of the current fragment
#                     instance.end_time = end_fragment_end_time
#                     print(f"No next fragment after this one ends, using current end: {instance.end_time}")
                
#                 return
        
#         # Fallback method - try partial matching
#         print("Exact match not found, trying partial matching...")
#         matching_fragments = []
        
#         for fragment in all_fragments:
#             fragment_text = ' '.join(fragment.get('lines', [])).lower()
            
#             # Check if the fragment text is in the subclip text or vice versa
#             if fragment_text in subclip_text or subclip_text in fragment_text:
#                 matching_fragments.append(fragment)
        
#         if matching_fragments:
#             # Sort matching fragments by start time
#             matching_fragments.sort(key=lambda x: float(x.get('begin', 0)))
            
#             # Set start time to the first matching fragment only if not the first subclip
#             if not is_first_subclip:
#                 instance.start_time = float(matching_fragments[0].get('begin', 0))
#                 print(f"Partial match start time: {instance.start_time}")
            
#             # Get the last matching fragment's index in the full list
#             last_match = matching_fragments[-1]
#             last_match_index = -1
            
#             for i, fragment in enumerate(all_fragments):
#                 if fragment.get('id') == last_match.get('id'):
#                     last_match_index = i
#                     break
            
#             # Set end time
#             if last_match_index + 1 < len(all_fragments):
#                 # Use start time of next fragment
#                 next_fragment = all_fragments[last_match_index + 1]
#                 instance.end_time = float(next_fragment.get('begin', 0))
#                 print(f"Partial match: using next fragment start: {instance.end_time}")
#             else:
#                 # Use end time of last matching fragment
#                 instance.end_time = float(last_match.get('end', 0))
#                 print(f"Partial match: no next fragment, using last fragment end: {instance.end_time}")
#         else:
#             print("No matching fragments found")
            
#     except (json.JSONDecodeError, IOError, ValueError) as e:
#         logger.error(f"Error processing SRT file: {e}")
        
#     # Ensure end time is always after start time
#     if instance.start_time is not None and instance.end_time is not None:
#         if instance.end_time <= instance.start_time:
#             # Add a minimum duration of 0.5 seconds
#             instance.end_time = instance.start_time + 0.5
#             print(f"Adjusted end time to ensure duration > 0: {instance.start_time} -> {instance.end_time}")

@receiver(pre_save, sender=Subclip)
def configure_subclip(sender, instance:Subclip, **kwargs):
    """
    Calculate start and end times for a subclip based on its text content.
    The end time will be the start time of the next fragment when available.
    The first subclip of a video will always have a start time of zero.
    """
    # Check if this is the first subclip for this clip
    is_first_subclip = False
    if instance.clip.sequence == 1:
        try:
            # Get all subclips for this clip, ordered by start_time
            existing_subclips = Subclip.objects.filter(clip=instance.clip).order_by('start_time')
            
            # If this is a new subclip (no pk) and there are no other subclips, it's the first one
            if not instance.pk and not existing_subclips.exists():
                is_first_subclip = True
            # If this is updating an existing subclip, check if it was the first one
            elif instance.pk and existing_subclips.first() and existing_subclips.first().pk == instance.pk:
                is_first_subclip = True
        except:
            # If any error occurs during this check, we'll proceed with regular processing
            pass
            
    # Check if this is an existing instance being updated
    if instance.pk:
        try:
            original = Subclip.objects.get(pk=instance.pk)
            # If text changed, reset timings to recalculate
            if original.text != instance.text:
                instance.start_time = None
                instance.end_time = None
        except Subclip.DoesNotExist:
            pass
    
    # Set start_time to 0 for first subclip and skip SRT processing for start_time
    if is_first_subclip is True:
        instance.start_time = 0
        
    # Process the SRT file to find matching fragments
    clip = instance.clip        
    video = clip.video
    if not video.srt_file:
        return
    
    try:
        # Load the SRT JSON content
        print(video.id)
        with video.srt_file.open('r') as srt_file:
            srt_data = json.load(srt_file)
        threshold = (
            Subclip.objects
            .filter(clip__sequence__lt=instance.clip.sequence, clip__video=instance.clip.video)
            .order_by('clip__sequence')
            .last()
            .end_time
            if Subclip.objects.filter(clip__sequence__lt=instance.clip.sequence).exists()
            else 0
        )
        print(f"Threshold for subclip: {threshold}")
        print(Subclip.objects
            .filter(clip__sequence__lt=instance.clip.sequence)
            .order_by('clip__sequence')
            .last())
        # Convert threshold to float if needed
        threshold = 0 if threshold is None else threshold
        threshold = float(threshold)
        # Filter fragments after the threshold
        filtered_fragments = [
            fragment for fragment in srt_data['fragments']
            if float(fragment['begin']) >= threshold
]

        # Get all fragments sorted by begin time
        all_fragments = sorted(filtered_fragments, key=lambda x: float(x.get('begin', 0)))

        print(f"Total fragments in SRT: {len(all_fragments)}")
        
        # Get subclip text in lowercase for comparison
        subclip_text = instance.text.lower().strip()
        
        # Concatenate all fragment texts to form a transcript
        full_transcript = ""
        fragment_positions = []  # Keep track of which fragment each position belongs to
        
        for i, fragment in enumerate(all_fragments):
            fragment_text = ' '.join(fragment.get('lines', [])).lower()
            fragment_positions.extend([i] * (len(fragment_text) + 1))  # +1 for the space
            full_transcript += fragment_text + " "
            
        full_transcript = full_transcript.strip()
        
        # If transcript is longer than our positions mapping, trim the positions
        if len(fragment_positions) > len(full_transcript):
            fragment_positions = fragment_positions[:len(full_transcript)]
        
        print(f"Full transcript: '{full_transcript}'")
        print(f"Searching for: '{subclip_text}'")
        print("-----------------------------------")
        print(filtered_fragments)
        print("-----------------------------------")
        # Find the subclip text in the transcript
        if subclip_text in full_transcript:
            # Find the start and end positions
            start_pos = full_transcript.find(subclip_text)
            end_pos = start_pos + len(subclip_text) - 1
            
            # Get the corresponding fragments
            if 0 <= start_pos < len(fragment_positions) and 0 <= end_pos < len(fragment_positions):
                start_fragment_index = fragment_positions[start_pos]
                end_fragment_index = fragment_positions[end_pos]
                
                # Set the start time only if this is not the first subclip
                if not is_first_subclip:
                    start_fragment = all_fragments[start_fragment_index]
                    instance.start_time = float(start_fragment.get('begin', 0))
                    print(f"Start fragment: {start_fragment.get('lines')} at {instance.start_time}")
                
                # Set the end time
                end_fragment = all_fragments[end_fragment_index]
                end_fragment_id = end_fragment.get('id')
                print(f"End fragment ID: {end_fragment_id}, text: {end_fragment.get('lines')}")
                
                # Find the next fragment that actually starts after this one ends
                end_fragment_end_time = float(end_fragment.get('end', 0))
                next_fragment = None
                
                for i in range(end_fragment_index + 1, len(all_fragments)):
                    potential_next = all_fragments[i]
                    if float(potential_next.get('begin', 0)) >= end_fragment_end_time:
                        next_fragment = potential_next
                        break
                
                if next_fragment:
                    # Use the start time of the next fragment that starts after this one ends
                    instance.end_time = float(next_fragment.get('begin', 0))
                    print( float(next_fragment.get('begin', 0)))
                    print(f"End time set to next fragment start: {instance.end_time}, ID: {next_fragment.get('id')}, text: {next_fragment.get('lines')}")
                else:
                    # Use the end time of the current fragment
                    instance.end_time = end_fragment_end_time
                    print(f"No next fragment after this one ends, using current end: {instance.end_time}")
                
                return
        
        # Fallback method - try partial matching
        print("Exact match not found, trying partial matching...")
        matching_fragments = []
        
        for fragment in all_fragments:
            fragment_text = ' '.join(fragment.get('lines', [])).lower()
            
            # Check if the fragment text is in the subclip or vice versa
            if fragment_text in subclip_text or subclip_text in fragment_text:
                matching_fragments.append(fragment)
        
        if matching_fragments:
            # Sort matching fragments by start time
            matching_fragments.sort(key=lambda x: float(x.get('begin', 0)))
            
            # Set start time to the first matching fragment only if not the first subclip
            if not is_first_subclip:
                instance.start_time = float(matching_fragments[0].get('begin', 0))
            
            # Get the last matching fragment's index in the full list
            last_match = matching_fragments[-1]
            last_match_index = -1
            
            for i, fragment in enumerate(all_fragments):
                if fragment.get('id') == last_match.get('id'):
                    last_match_index = i
                    break
            
            # Set end time
            if last_match_index + 1 < len(all_fragments):
                # Use start time of next fragment
                next_fragment = all_fragments[last_match_index + 1]
                instance.end_time = float(next_fragment.get('begin', 0))
                print(f"Partial match: using next fragment start: {instance.end_time}")
            else:
                # Use end time of last matching fragment
                instance.end_time = float(last_match.get('end', 0))
                print(f"Partial match: no next fragment, using last fragment end: {instance.end_time}")
    except (json.JSONDecodeError, IOError, ValueError) as e:
        logger.error(f"Error processing SRT file: {e}")
# @receiver(post_save, sender=Clips)
# def assign_black_video_to_clip(sender, instance:Clips, created, **__):
#     """
#     Assigns a black video to a clip when it's created if no video file exists.
#     """
#     # Only proceed if the clip doesn't have a video file
#     if not instance.video_file or not os.path.exists(instance.video_file.path if instance.video_file else ''):
#         try:
#             # Get clip duration
#             duration = instance.end_time - instance.start_time
            
#             # Determine video dimensions based on the video's dimension setting
#             video = instance.video
#             dimensions = video.dimensions
#             if dimensions == "16:9":
#                 width, height = 1920, 1080
#             elif dimensions == "9:16":
#                 width, height = 1080, 1920
#             elif dimensions == "1:1":
#                 width, height = 1080, 1080
#             else:
#                 width, height = 1920, 1080  # Default to 16:9
                
#             # Check if we already have a black clip with similar dimensions and duration for this video
#             existing_clips = Clips.objects.filter(
#                 video=video,
#                 video_file__icontains='black.mp4'
#             )
            
#             # Try to find a suitable existing black clip to reuse
#             suitable_clip = None
#             for clip in existing_clips:
#                 # Skip the current clip
#                 if clip.id == instance.id:
#                     continue
                    
#                 # Check if dimensions match (based on aspect ratio)
#                 clip_dimensions_match = False
#                 if clip.video_file and os.path.exists(clip.video_file.path):
#                     clip_dimensions = video.dimensions
#                     if clip_dimensions == dimensions:
#                         clip_dimensions_match = True
                
#                 # Check if duration is close enough (within 1 second)
#                 clip_duration = clip.end_time - clip.start_time
#                 duration_match = abs(clip_duration - duration) <= 1
                
#                 if clip_dimensions_match and duration_match:
#                     suitable_clip = clip
#                     break
            
#             if suitable_clip and suitable_clip.video_file and os.path.exists(suitable_clip.video_file.path):
#                 # Reuse the existing black clip's video file
#                 logger.info(f"Reusing existing black video from clip {suitable_clip.id} for clip {instance.id}")
                
#                 # Create a new reference to the same file
#                 with open(suitable_clip.video_file.path, 'rb') as f:
#                     instance.video_file.save(f"clip_{instance.id}_black.mp4", File(f), save=True)
#             else:
#                 # Create a new black video
#                 with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp:
#                     temp_path = tmp.name
                
#                 # Create VideoProcessorService temporary instance to reuse its method
#                 video_processor = VideoProcessorService(video)
                
#                 # Use the existing method to create black video
#                 video_processor._create_black_video(
#                     temp_path,
#                     duration,
#                     width,
#                     height
#                 )
                
#                 # Save the black video to the clip
#                 clip_filename = f"clip_{instance.id}_black.mp4"
#                 with open(temp_path, 'rb') as f:
#                     instance.video_file.save(clip_filename, File(f), save=True)
                    
#                 # Clean up the temporary file
#                 os.unlink(temp_path)
                
#                 logger.info(f"Created and assigned new black video for clip {instance.id}")
            
#         except Exception as e:
#             logger.error(f"Error creating black video for clip {instance.id}: {str(e)}")
#             # Don't re-raise the exception, just log it to avoid breaking the save process

# @receiver(post_save, sender=BackgroundMusic)
# def apply_background_music(sender, instance:BackgroundMusic, created, **__):
#     """
#     Applies background music to the output video when a BackgroundMusic object is created.
#     """
#     if created:  # Only process when a new BackgroundMusic object is created
#         video = instance.video
        
#         # Check if the video has an output file and background music has an audio file
#         if not video.output or not os.path.exists(video.output.path if video.output else ''):
#             logger.error(f"No output file found for video {video.id}")
#             return

#         if not instance.audio_file:
#             logger.error(f"No audio file found in BackgroundMusic object for video {video.id}")
#             return
            
#         if not instance.audio_file.name or not os.path.exists(instance.audio_file.path if instance.audio_file else ''):
#             logger.error(f"Invalid audio file in BackgroundMusic object for video {video.id}")
#             return
        
#         try:
#             # Create VideoProcessorService instance and apply background music
#             video_processor = VideoProcessorService(video)
#             result = video_processor.apply_background_music(instance)
            
#             if result:
#                 logger.info(f"Successfully applied background music to video {video.id}")
#             else:
#                 logger.error(f"Failed to apply background music to video {video.id}")
                
#         except Exception as e:
#             logger.error(f"Error applying background music to video {video.id}: {str(e)}")
#             # Don't re-raise the exception to avoid breaking the save process



@receiver(pre_save, sender=Clips)
def configure_subclip_from_clips(sender, instance: Clips, **kwargs):
    """
    Calculate start and end times for a clip based on its text content.
    The end time will be the start time of the next fragment when available.
    The first clip of a video will always have a start time of zero.
    """
    # Check if this is the first clip for this video
    is_first_clip = False
    if instance.sequence == 1:
        try:
            # Get all clips for this video, ordered by sequence
            existing_clips = Clips.objects.filter(video=instance.video).order_by('sequence')
            
            # If this is a new clip (no pk) and there are no other clips, it's the first one
            if not instance.pk and not existing_clips.exists():
                is_first_clip = True
            # If this is updating an existing clip, check if it was the first one
            elif instance.pk and existing_clips.first() and existing_clips.first().pk == instance.pk:
                is_first_clip = True
        except:
            # If any error occurs during this check, we'll proceed with regular processing
            pass
            
    # Check if this is an existing instance being updated
    if instance.pk:
        try:
            original = Clips.objects.get(pk=instance.pk)
            # If text changed, reset timings to recalculate
            if original.text != instance.text:
                instance.start_time = None
                instance.end_time = None
        except Clips.DoesNotExist:
            pass
    
    # Set start_time to 0 for first clip and skip SRT processing for start_time
    if is_first_clip:
        instance.start_time = 0
        
    # Process the SRT file to find matching fragments
    video = instance.video
    if not video.srt_file:
        return
    
    try:
        # Load the SRT JSON content
        print(f"Processing video ID: {video.id}")
        with video.srt_file.open('r') as srt_file:
            srt_data = json.load(srt_file)
        
        # Calculate threshold based on previous clips
        threshold = (
            Clips.objects
            .filter(sequence__lt=instance.sequence, video=instance.video)
            .order_by('sequence')
            .last()
            .end_time
            if Clips.objects.filter(sequence__lt=instance.sequence, video=instance.video).exists()
            else 0
        )
        print(f"Threshold for clip: {threshold}")
        
        # Convert threshold to float if needed
        threshold = 0 if threshold is None else threshold
        threshold = float(threshold)
        
        # Filter fragments after the threshold
        filtered_fragments = [
            fragment for fragment in srt_data['fragments']
            if float(fragment['begin']) >= threshold
        ]

        # Get all fragments sorted by begin time
        all_fragments = sorted(filtered_fragments, key=lambda x: float(x.get('begin', 0)))

        print(f"Total fragments in SRT after threshold: {len(all_fragments)}")
        
        # Get clip text in lowercase for comparison
        clip_text = instance.text.lower().strip()
        
        # Concatenate all fragment texts to form a transcript
        full_transcript = ""
        fragment_positions = []  # Keep track of which fragment each position belongs to
        
        for i, fragment in enumerate(all_fragments):
            fragment_text = ' '.join(fragment.get('lines', [])).lower()
            fragment_positions.extend([i] * (len(fragment_text) + 1))  # +1 for the space
            full_transcript += fragment_text + " "
            
        full_transcript = full_transcript.strip()
        
        # If transcript is longer than our positions mapping, trim the positions
        if len(fragment_positions) > len(full_transcript):
            fragment_positions = fragment_positions[:len(full_transcript)]
        
        print(f"Full transcript: '{full_transcript}'")
        print(f"Searching for: '{clip_text}'")
        print("-----------------------------------")
        print(f"Filtered fragments count: {len(filtered_fragments)}")
        print("-----------------------------------")
        
        # Find the clip text in the transcript
        if clip_text in full_transcript:
            # Find the start and end positions
            start_pos = full_transcript.find(clip_text)
            end_pos = start_pos + len(clip_text) - 1
            
            # Get the corresponding fragments
            if 0 <= start_pos < len(fragment_positions) and 0 <= end_pos < len(fragment_positions):
                start_fragment_index = fragment_positions[start_pos]
                end_fragment_index = fragment_positions[end_pos]
                
                # Set the start time only if this is not the first clip
                if not is_first_clip:
                    start_fragment = all_fragments[start_fragment_index]
                    instance.start_time = float(start_fragment.get('begin', 0))
                    print(f"Start fragment: {start_fragment.get('lines')} at {instance.start_time}")
                
                # Set the end time
                end_fragment = all_fragments[end_fragment_index]
                end_fragment_id = end_fragment.get('id')
                print(f"End fragment ID: {end_fragment_id}, text: {end_fragment.get('lines')}")
                
                # Find the next fragment that actually starts after this one ends
                end_fragment_end_time = float(end_fragment.get('end', 0))
                next_fragment = None
                
                for i in range(end_fragment_index + 1, len(all_fragments)):
                    potential_next = all_fragments[i]
                    if float(potential_next.get('begin', 0)) >= end_fragment_end_time:
                        next_fragment = potential_next
                        break
                
                if next_fragment:
                    # Use the start time of the next fragment that starts after this one ends
                    instance.end_time = float(next_fragment.get('begin', 0))
                    print(f"End time set to next fragment start: {instance.end_time}")
                    print(f"Next fragment ID: {next_fragment.get('id')}, text: {next_fragment.get('lines')}")
                else:
                    # Use the end time of the current fragment
                    instance.end_time = end_fragment_end_time
                    print(f"No next fragment after this one ends, using current end: {instance.end_time}")
                
                return
        
        # Fallback method - try partial matching
        print("Exact match not found, trying partial matching...")
        matching_fragments = []
        
        for fragment in all_fragments:
            fragment_text = ' '.join(fragment.get('lines', [])).lower()
            
            # Check if the fragment text is in the clip text or vice versa
            if fragment_text in clip_text or clip_text in fragment_text:
                matching_fragments.append(fragment)
        
        if matching_fragments:
            # Sort matching fragments by start time
            matching_fragments.sort(key=lambda x: float(x.get('begin', 0)))
            
            # Set start time to the first matching fragment only if not the first clip
            if not is_first_clip:
                instance.start_time = float(matching_fragments[0].get('begin', 0))
                print(f"Partial match start time: {instance.start_time}")
            
            # Get the last matching fragment's index in the full list
            last_match = matching_fragments[-1]
            last_match_index = -1
            
            for i, fragment in enumerate(all_fragments):
                if fragment.get('id') == last_match.get('id'):
                    last_match_index = i
                    break
            
            # Set end time
            if last_match_index + 1 < len(all_fragments):
                # Use start time of next fragment
                next_fragment = all_fragments[last_match_index + 1]
                instance.end_time = float(next_fragment.get('begin', 0))
                print(f"Partial match: using next fragment start: {instance.end_time}")
            else:
                # Use end time of last matching fragment
                instance.end_time = float(last_match.get('end', 0))
                print(f"Partial match: no next fragment, using last fragment end: {instance.end_time}")
        else:
            print("No matching fragments found")
            
    except (json.JSONDecodeError, IOError, ValueError) as e:
        logger.error(f"Error processing SRT file: {e}")
        
    # Ensure end time is always after start time
    if instance.start_time is not None and instance.end_time is not None:
        if instance.end_time <= instance.start_time:
            # Add a minimum duration of 0.5 seconds
            instance.end_time = instance.start_time + 0.5
            print(f"Adjusted end time to ensure duration > 0: {instance.start_time} -> {instance.end_time}")

# @receiver(pre_save, sender=Clips)
# def configure_subclip_from_clips(sender, instance:Clips, **kwargs):
#     # Check if this is an existing instance being updated
#     # if instance.pk:
#     #     try:
#     #         # Get the original instance from the database
#     #         original = Clips.objects.get(pk=instance.pk)
#     #         # If text changed, reset timings to recalculate
#     #         if original.text != instance.text:
#     #             instance.start_time = None
#     #             instance.end_time = None
#     #     except Clips.DoesNotExist:
#     #         pass

#     # else:
#         clip = instance   
#         video = clip.video
#         if video.srt_file:
#             try:
#                 # Load the SRT JSON content
#                 with video.srt_file.open('r') as srt_file:
#                     srt_data = json.load(srt_file)
                
#                 # Filter fragments that are between clip's start and end times
#                 fragments = srt_data.get('fragments', [])
#                 print("-------------------------------------------------")
#                 print(fragments)
#                 print("-------------------------------------------------")
#                 clip_fragments = []
                
#                 for fragment in fragments:
#                     begin_time = float(fragment.get('begin', 0))
#                     end_time = float(fragment.get('end', 0))
                    
#                     # Check if fragment is within the clip's time range
#                     if begin_time >= clip.start_time and end_time <= clip.end_time:
#                         clip_fragments.append(fragment)
                
#                 subclip_text = instance.text.lower().strip()
#                 # First try to find an exact match
#                 exact_match_found = False
                
#                 # Get all fragments ordered by begin time for safer navigation
#                 ordered_fragments = sorted(clip_fragments, key=lambda x: float(x.get('begin', 0)))
                
#                 # Print debug info about available fragments
#                 print(f"Total SRT fragments: {len(fragments)}")
#                 print(f"Fragments within clip time range: {len(clip_fragments)}")
                
#                 # Concatenate all fragments to form the full transcript text
#                 full_transcript = ""
#                 fragment_positions = []  # Track start position of each fragment in transcript
                
#                 for fragment in clip_fragments:
#                     fragment_positions.append(len(full_transcript))
#                     fragment_text = ' '.join(fragment.get('lines', [])).lower()
#                     full_transcript += fragment_text + " "  # Add space after each fragment
                
#                 full_transcript = full_transcript.strip()
                
#                 print(f"Full transcript: '{full_transcript}'")
#                 print(f"Full transcript length: {len(full_transcript)}")
#                 print(f"Clip text to find: '{subclip_text}'")
#                 print(f"Clip text length: {len(subclip_text)}")
                
#                 # Find the start position of subclip text in the full transcript
#                 if subclip_text in full_transcript:
#                     text_start_pos = full_transcript.find(subclip_text)
#                     text_end_pos = text_start_pos + len(subclip_text) - 1
                    
#                     print(f"Found text at position {text_start_pos} to {text_end_pos}")
                    
#                     # Find which fragment contains the start position
#                     start_fragment_index = -1
#                     end_fragment_index = -1
                    
#                     # Find the fragment containing the start position
#                     for i, start_pos in enumerate(fragment_positions):
#                         # Calculate end position of this fragment
#                         end_pos = (fragment_positions[i+1] - 1) if i+1 < len(fragment_positions) else len(full_transcript) - 1
                        
#                         if start_pos <= text_start_pos <= end_pos:
#                             start_fragment_index = i
#                             instance.start_time = float(clip_fragments[i].get('begin', 0))
#                             exact_match_found = True
#                             print(f"Start position found in fragment {i}: '{' '.join(clip_fragments[i].get('lines', []))}'")
#                             print(f"Start time: {instance.start_time}")
#                             break
                    
#                     # Find the fragment containing the end position
#                     for i, start_pos in enumerate(fragment_positions):
#                         # Calculate end position of this fragment
#                         end_pos = (fragment_positions[i+1] - 1) if i+1 < len(fragment_positions) else len(full_transcript) - 1
                        
#                         if start_pos <= text_end_pos <= end_pos:
#                             end_fragment_index = i
#                             print(f"End position found in fragment {i}: '{' '.join(clip_fragments[i].get('lines', []))}'")
#                             print(f"Fragment exact end time from SRT: {clip_fragments[i].get('end')}")
#                             break

#                     # Handle end time calculation
#                     if end_fragment_index != -1:
#                         # First get the end time from the current fragment
#                         current_fragment_end = float(clip_fragments[end_fragment_index].get('end', 0))
                        
#                         # Check if there's a next fragment in chronological order
#                         if end_fragment_index + 1 < len(clip_fragments):
#                             next_fragment = clip_fragments[end_fragment_index + 1]
#                             next_fragment_start = float(next_fragment.get('begin', 0))
#                             instance.end_time = next_fragment_start
#                             print(f"Using next fragment '{next_fragment.get('lines')}' start time: {next_fragment_start}")
#                         else:
#                             # Check if there's a fragment after this in the full ordered fragments
#                             # Get current fragment's position in the complete ordered list
#                             current_fragment = clip_fragments[end_fragment_index]
                            
#                             # Find where it is in the ordered fragments list
#                             all_ordered_fragments = sorted(fragments, key=lambda x: float(x.get('begin', 0)))
#                             current_global_index = -1
                            
#                             for i, frag in enumerate(all_ordered_fragments):
#                                 if (frag.get('begin') == current_fragment.get('begin') and 
#                                     frag.get('end') == current_fragment.get('end') and
#                                     frag.get('lines') == current_fragment.get('lines')):
#                                     current_global_index = i
#                                     break
                            
#                             # If found and there's a next fragment in the global list
#                             if current_global_index != -1 and current_global_index + 1 < len(all_ordered_fragments):
#                                 next_global_fragment = all_ordered_fragments[current_global_index + 1]
#                                 next_global_start = float(next_global_fragment.get('begin', 0))
                                
#                                 # Only use if it's reasonably close to the clip end time
#                                 if next_global_start <= clip.end_time + 2.0:  # Allow 2 seconds beyond clip end
#                                     instance.end_time = next_global_start
#                                     print(f"Using next global fragment '{next_global_fragment.get('lines')}' start time: {next_global_start}")
#                                 else:
#                                     # Next fragment is too far, use current end
#                                     instance.end_time = current_fragment_end
#                                     print(f"Next global fragment too far, using current fragment end time: {current_fragment_end}")
#                             else:
#                                 # No next fragment, use the end time of the current fragment
#                                 instance.end_time = current_fragment_end
#                                 print(f"No next fragment available, using current fragment end time: {current_fragment_end}")
#                     else:
#                         # Fallback if no end fragment is found
#                         if start_fragment_index != -1:
#                             # If we found a start but not an end, use start fragment end time
#                             instance.end_time = float(clip_fragments[start_fragment_index].get('end', 0))
#                             print(f"No end fragment found, using start fragment end time: {instance.end_time}")
#                         else:
#                             # Last resort fallback - 1 second duration
#                             instance.end_time = instance.start_time + 1.0
#                             print(f"No end fragment found, using default duration. Start: {instance.start_time}, End: {instance.end_time}")
                
#                 # Fallback to the old method if exact match fails
#                 if not exact_match_found:
#                     matching_fragments = []
                    
#                     for fragment in clip_fragments:
#                         fragment_text = ' '.join(fragment.get('lines', [])).lower()
#                         if fragment_text in subclip_text or subclip_text in fragment_text:
#                             matching_fragments.append(fragment)
                    
#                     if matching_fragments:
#                         # Sort by begin time to ensure correct order
#                         matching_fragments = sorted(matching_fragments, key=lambda x: float(x.get('begin', 0)))
#                         begin_times = [float(f.get('begin', 0)) for f in matching_fragments]
#                         end_times = [float(f.get('end', 0)) for f in matching_fragments]
                        
#                         instance.start_time = min(begin_times)
                        
#                         # Find index of last matching fragment in the chronologically ordered fragments
#                         ordered_fragments = sorted(clip_fragments, key=lambda x: float(x.get('begin', 0)))
#                         last_match = matching_fragments[-1]
#                         last_match_ordered_index = -1
                        
#                         for i, frag in enumerate(ordered_fragments):
#                             if (frag.get('begin') == last_match.get('begin') and 
#                                 frag.get('end') == last_match.get('end') and
#                                 frag.get('lines') == last_match.get('lines')):
#                                 last_match_ordered_index = i
#                                 break
                        
#                         # Set end time to start time of next fragment if available
#                         if last_match_ordered_index != -1 and last_match_ordered_index + 1 < len(ordered_fragments):
#                             next_fragment = ordered_fragments[last_match_ordered_index + 1]
#                             next_fragment_start = float(next_fragment.get('begin', 0))
#                             print(f"FRAGMENT FOUND {next_fragment_start}")
#                             instance.end_time = next_fragment_start
#                         else:
#                             print("NO NEXT FRAGMENT")
#                             # No next fragment, use end time of last matching fragment
#                             last_fragment_end = max(end_times)
#                             instance.end_time = last_fragment_end
#                     else:
#                         print("NO MATCHING FRAGMENTS")
                
#                 # Ensure end time is always after start time
#                 if instance.start_time is not None and instance.end_time is not None:
#                     if instance.end_time <= instance.start_time:
#                         # Add a minimum duration of 0.5 seconds
#                         instance.end_time = instance.start_time + 0.5
#                         print(f"Adjusted end time to ensure duration > 0: {instance.start_time} -> {instance.end_time}")
                
#             except (json.JSONDecodeError, IOError, ValueError) as e:
#                 logger.error(f"Error processing SRT file: {e}")

@receiver(post_save, sender=Video)
def update_video_name(sender, instance:Video, created, **kwargs):

    if instance.name in [None, ''] and instance.output:
        clips =  Clips.objects.filter(video=instance)
        if clips.exists():
            clip = clips.order_by('sequence').first()
            text = clip.text[:20] + '...' if len(clip.text) > 20 else clip.text
            instance.name = text
            instance.save()


@receiver(post_save, sender=ProcessingStatus)
def delete_when_reach_hundred(sender, instance:ProcessingStatus, created, **kwargs):
    if instance.progress >= 100:
        # Sleep for 5 seconds before deleting
        time.sleep(5)
        instance.delete()
        logger.info(f"Deleted ProcessingStatus instance with ID {instance.id} as progress reached 100%.")