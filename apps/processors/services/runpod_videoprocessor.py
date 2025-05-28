import json
import requests
import os
import tempfile
import time
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files import File

from apps.processors.utils import generate_signed_url, generate_signed_url_for_upload
from apps.processors.models import Video, Clips, Subclip, BackgroundMusic

class RunPodVideoProcessor:
    def __init__(self, video_id, api_key=None, endpoint_id=None):
        self.video_id = video_id
        self.api_key = api_key or settings.RUNPOD_API_KEY
        self.endpoint_id = endpoint_id or settings.RUNPOD_ENDPOINT_ID
        self.api_url = f"https://api.runpod.ai/v2/{self.endpoint_id}/run"
        
    def _download_to_temp(self, s3_path):
        """Download a file from S3 to a local temp file"""
        if not s3_path:
            return None
        s3_path = s3_path.replace('media/', '')
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(s3_path)[1]) as tmp:
                with default_storage.open(s3_path, 'rb') as s3_file:
                    tmp.write(s3_file.read())
                return tmp.name
        except Exception as e:
            print(f"Error downloading {s3_path}: {str(e)}")
            return None
                
    def _get_s3_urls(self, file_paths):
        """Convert S3 paths to pre-signed URLs that RunPod can access"""
        urls = {}
        for key, path in file_paths.items():
            if path:
                # Special case for font_file - it's a CharField path, not a FileField
                if key == "font_file":
                    urls[key] = path
                else:
                    # Generate a pre-signed URL with an expiration time
                    url = generate_signed_url_for_upload(path, expires_in=3600)  # 1 hour expiration
                    urls[key] = url
        return urls
        
    def replace_subclips(self, video:Video):
        """Submit a job to replace changed subclips in an existing video"""
        from apps.processors.models import Clips, Subclip, BackgroundMusic
        
        # Get all clips marked as changed
        clips = Clips.objects.filter(video=video, is_changed=True).order_by("start_time")
        
        # If no clips are marked as changed, return early
        if not clips.exists():
            return {
                "success": False,
                "error": "No changed clips found"
            }
            
        # Prepare clip data with changed clips only
        clip_data = []
        for clip in clips:
            clip_info = {
                "id": clip.id,
                "start_time": clip.start_time,
                "end_time": clip.end_time,
                "text": clip.text,
                "sequence": clip.sequence,
                "is_changed": True,  # This is always True for these clips
            }
            
            # Add subclips
            subclips = Subclip.objects.filter(clip=clip).order_by("start_time")
            if subclips.exists():
                clip_info["subclips"] = []
                for subclip in subclips:
                    subclip_info = {
                        "id": subclip.id,
                        "start_time": subclip.start_time,
                        "end_time": subclip.end_time,
                        "text": subclip.text,
                    }
                    if subclip.video_file:
                        subclip_info["video_file"] = subclip.video_file.name
                    clip_info["subclips"].append(subclip_info)
            
            # Add to clip data array
            clip_data.append(clip_info)
            
        # Build video configuration
        video_config = {
            "id": video.id,
            "dimensions": video.dimensions,
            "font_size": video.font_size,
            "font_color": video.font_color,
            "subtitle_box_color": video.subtitle_box_color,
            "box_roundness": video.box_roundness,
        }
        
        # Check for background music
        bg_music = None
        try:
            bg_music = BackgroundMusic.objects.get(video=video)
            if bg_music and bg_music.audio_file:
                video_config["bg_music"] = {
                    "start_time": bg_music.start_time,
                    "end_time": bg_music.end_time,
                    "volume": bg_music.volumn
                }
        except BackgroundMusic.DoesNotExist:
            pass
        
        # Add file paths - must include output video for replacement
        file_paths = {}
        
        # The output video is required for clip replacement
        if not (video.output and hasattr(video.output, 'name') and video.output.name):
            return {
                "success": False,
                "error": "No output video available for replacement"
            }
            
        file_paths["output_video"] = video.output.name
        
        # Add font if available
        if video.subtitle_font and hasattr(video.subtitle_font, 'font_path'):
            file_paths["font_file"] = video.subtitle_font.font_path
            
        # Add bg music if available
        if bg_music and bg_music.audio_file:
            file_paths["bg_music_file"] = bg_music.audio_file.name
        
        # Add all subclip video files for changed clips
        for clip in clip_data:
            if "subclips" in clip:
                for subclip in clip["subclips"]:
                    if "video_file" in subclip:
                        file_key = f"subclip_{subclip['id']}_video"
                        file_paths[file_key] = subclip["video_file"]
                        subclip["video_file_key"] = file_key
        
        # Generate pre-signed URLs for all files
        print("File paths for RunPod clip replacement:", file_paths)
        file_urls = self._get_s3_urls(file_paths)
        
        # Prepare payload for RunPod
        payload = {
            "input": {
                "task_type": "replace_subclips",  # Specify task type for clip replacement
                "video_id": video.id,
                "video_config": video_config,
                "clips": clip_data,
                "file_urls": file_urls,
                "s3_config": {
                    "bucket": settings.AWS_STORAGE_BUCKET_NAME,
                    "region": settings.AWS_REGION,
                    "output_folder": "output/",
                    "output_bg_folder": "output_bg/"
                }
            }
        }

        
        # Submit job to RunPod
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.post(self.api_url, headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()
            
            # Return the job ID for status checking
            return {
                "success": True,
                "job_id": result.get("id"),
                "status": "submitted"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def process_video(self, video:Video):
        """Submit a full video processing job to RunPod"""
        from apps.processors.models import Clips, Subclip, BackgroundMusic
        
        # Get all related data
        clips = Clips.objects.filter(video=video).order_by("start_time")
        clip_data = []
        
        for clip in clips:
            clip_info = {
                "id": clip.id,
                "start_time": clip.start_time,
                "end_time": clip.end_time,
                "text": clip.text,
                "sequence": clip.sequence,
                "is_changed": clip.is_changed,
            }
            
            if clip.video_file:
                clip_info["video_file"] = clip.video_file.name
                
            # Add subclips if any
            subclips = Subclip.objects.filter(clip=clip).order_by("start_time")
            if subclips.exists():
                clip_info["subclips"] = []
                for subclip in subclips:
                    subclip_info = {
                        "id": subclip.id,
                        "start_time": subclip.start_time,
                        "end_time": subclip.end_time,
                        "text": subclip.text,
                    }
                    if subclip.video_file:
                        subclip_info["video_file"] = subclip.video_file.name
                    clip_info["subclips"].append(subclip_info)
                    
            clip_data.append(clip_info)
        
        # Check for background music
        bg_music = None
        try:
            bg_music = BackgroundMusic.objects.get(video=video)
        except BackgroundMusic.DoesNotExist:
            pass
            
        # Build video configuration
        video_config = {
            "id": video.id,
            "dimensions": video.dimensions,
            "font_size": video.font_size,
            "font_color": video.font_color,
            "subtitle_box_color": video.subtitle_box_color,
            "box_roundness": video.box_roundness,
        }
        
        # Add file paths
        file_paths = {}
        if video.audio_file:
            file_paths["audio_file"] = video.audio_file.name
            
        if video.subtitle_font and hasattr(video.subtitle_font, 'font_path'):
            file_paths["font_file"] = video.subtitle_font.font_path
        if video.output and hasattr(video.output, 'name') and video.output.name:
            file_paths["output_video"] = video.output.name
        if bg_music and bg_music.audio_file:
            file_paths["bg_music_file"] = bg_music.audio_file.name
            video_config["bg_music"] = {
                "start_time": bg_music.start_time,
                "end_time": bg_music.end_time,
                "volume": bg_music.volumn
            }
        
        # Add all clip and subclip video files
        for clip in clip_data:
            if "video_file" in clip:
                file_key = f"clip_{clip['id']}_video"
                file_paths[file_key] = clip["video_file"]
                clip["video_file_key"] = file_key
                
            if "subclips" in clip:
                for subclip in clip["subclips"]:
                    if "video_file" in subclip:
                        file_key = f"subclip_{subclip['id']}_video"
                        file_paths[file_key] = subclip["video_file"]
                        subclip["video_file_key"] = file_key
        
        # Generate pre-signed URLs for all files
        print("File paths for RunPod:", file_paths)
        file_urls = self._get_s3_urls(file_paths)

        
        # Prepare payload for RunPod
        payload = {
            "input": {
                "task_type": "generate_video",  # Specify task type for full video generation
                "video_id": video.id,
                "video_config": video_config,
                "clips": clip_data,
                "file_urls": file_urls,
                "s3_config": {
                    "bucket": settings.AWS_STORAGE_BUCKET_NAME,
                    "region": settings.AWS_REGION,
                    "output_folder": "output/",
                    "output_bg_folder": "output_bg/"
                }
            }
        }
        print("----Payload for RunPod:", json.dumps(payload, indent=2))
        # Submit job to RunPod
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.post(self.api_url, headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()
            
            # Return the job ID for status checking
            print(f"RunPod job submitted successfully: {result}")
            return {
                "success": True,
                "job_id": result.get("id"),
                "status": "submitted"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
        
            
    def check_job_status(self, job_id):
        """Check the status of a submitted job"""
        status_url = f"https://api.runpod.ai/v2/{self.endpoint_id}/status/{job_id}"
        print("STATUS URL:", status_url)
        headers = {
            "Authorization": f"Bearer {self.api_key}"
        }
        
        try:
            response = requests.get(status_url, headers=headers)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
            
    # def save_results(self, video:Video, result_data):
    #     """Save the results from RunPod back to the video model"""
    #     try:
    #         import base64
    #         import tempfile
    #         from django.core.files.base import ContentFile

    #         success = False
    #         # Handle case where RunPod returns base64-encoded video
    #         if "output" in result_data and result_data.get("success", False):
    #             try:
    #                 # Decode the base64 data
    #                 output_base64 = result_data["output"]
    #                 video_data = base64.b64decode(output_base64)
    #                 video.output.save(f"output_{video.id}.mp4", ContentFile(video_data), save=False)

    #                 output_base64_watermarked = result_data["output_watermarked"]
    #                 video_data = base64.b64decode(output_base64_watermarked)
    #                 video.output_with_watermark.save(f"output_watermarked_{video.id}.mp4", ContentFile(video_data), save=False)
                    
    #                 print(f"Saved output video to: {video.output.name}")
    #                 success = True
    #             except Exception as e:
    #                 print(f"Error processing base64 output: {str(e)}")
            
    #         video.save()
    #         return success
    #     except Exception as e:
    #         print(f"Error saving results: {str(e)}")
    #         return False
        
    def save_results(self, video:Video, result_data):
        """Save the results from RunPod back to the video model"""
        try:
            success = False
            # Handle case where RunPod returns S3 paths instead of base64 data
            if result_data.get("success", False):
                # Main output video
                if "output_key" in result_data and result_data["output_key"]:
                    output_key = result_data["output_key"]
                    # Save the S3 key to the video model
                    video.output.name = output_key
                    print(f"Saved output video reference to: {output_key}")
                    success = True
                
                # Watermarked output video
                if "output_watermarked_key" in result_data and result_data["output_watermarked_key"]:
                    output_watermarked_key = result_data["output_watermarked_key"]
                    # Save the S3 key to the video model
                    video.output_with_watermark.name = output_watermarked_key
                    print(f"Saved watermarked output video reference to: {output_watermarked_key}")
            
            video.save()
            return success
            
        except Exception as e:
            print(f"Error saving results: {str(e)}")
            return False


    def poll_until_complete(self, job_id, max_attempts=1000, delay=10):
        """Poll the job status until it completes or fails
        
        Args:
            job_id: The RunPod job ID
            max_attempts: Maximum number of polling attempts
            delay: Delay between polling attempts in seconds
            
        Returns:
            dict: Status information including success, status, and output data
        """
        attempt = 0
        
        while True:
            attempt += 1
            
            # Get the job status
            status_result = self.check_job_status(job_id)
            
            status = status_result.get("status")
            
            # Check if the job is completed or failed
            if status == "COMPLETED":
                output = status_result.get("output", {})
                return {
                    "success": True,
                    "status": "completed",
                    "output": output
                }
            elif status == "FAILED":
                error = status_result.get("error", "Unknown error")
                return {
                    "success": False,
                    "status": "failed",
                    "error": error
                }
                
            # Job is still running, get progress if available
            progress = None
            if "progress" in status_result:
                progress = status_result["progress"]
                
            print(f"Job {job_id} is still running. Status: {status}, Progress: {progress}")
            
            # Wait before checking again
            time.sleep(delay)
            
        # If we've reached the maximum attempts, return a timeout error
        return {
            "success": False,
            "status": "timeout",
            "error": f"Job processing timed out after {max_attempts} attempts"
        }