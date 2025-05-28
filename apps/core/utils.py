import logging
from typing import Dict, List, Optional, Set, Any, Union
from pathlib import Path
from .services.s3_service import StorageFactory, S3Config
import os
import subprocess
import os
from pathlib import Path
import tempfile
import logging
import time
from apps.processors.models import Video, Clips, Subclip, BackgroundMusic
import concurrent.futures
from functools import partial
from django.core.files import File
from django.core.files.storage import default_storage
from django.conf import settings
# Set up logging
logger = logging.getLogger(__name__)

def get_user_asset_tree(user_id: str, 
                       file_extensions: Optional[Set[str]] = None, 
                       storage=None) -> Dict[str, Any]:
    """
    Get a hierarchical folder tree for user assets from S3 or local storage.
    
    Args:
        user_id: The user ID to get assets for
        file_extensions: Optional set of file extensions to filter by (e.g. {'.mp4', '.png'})
        storage: Optional storage interface (if None, one will be created using StorageFactory)
        
    Returns:
        Dict representing the folder tree structure
    """
    if not storage:
        storage = StorageFactory.get_storage()
    
    prefix = f"videocrafter/users/{user_id}/assetlibrary/"
    
    # For S3 storage, we need to list objects by prefix
    if hasattr(storage, 's3_client'):
        tree = _get_s3_folder_tree(storage, prefix, file_extensions)
    else:
        # For local storage
        tree = _get_local_folder_tree(storage, prefix, file_extensions)
    
    return tree

def _get_s3_folder_tree(storage, prefix: str, file_extensions: Optional[Set[str]] = None) -> Dict[str, Any]:
    """Build a folder tree from S3 storage."""
    try:
        # Use boto3 client to list objects with the given prefix
        response = storage.s3_client.list_objects_v2(
            Bucket=storage.bucket_name,
            Prefix=prefix,
            Delimiter='/'  # Use delimiter to simulate folder structure
        )
        
        tree = {"name": Path(prefix).name or "root", "type": "folder", "children": []}
        
        # Process common prefixes (folders)
        if 'CommonPrefixes' in response:
            for common_prefix in response['CommonPrefixes']:
                subfolder = common_prefix['Prefix']
                # Recursively get the tree for this subfolder
                subtree = _get_s3_folder_tree(storage, subfolder, file_extensions)
                tree["children"].append(subtree)
        
        # Process objects (files)
        if 'Contents' in response:
            for item in response['Contents']:
                key = item['Key']
                # Skip the prefix itself
                if key == prefix:
                    continue
                
                # Get the filename without the prefix
                filename = key[len(prefix):]
                
                # Skip files that don't match the extension filter
                if file_extensions and not any(filename.lower().endswith(ext.lower()) for ext in file_extensions):
                    continue
                
                file_info = {
                    "name": filename,
                    "type": "file",
                    "size": item['Size'],
                    "path": key,
                    "modified": item['LastModified']
                }
                tree["children"].append(file_info)
        
        return tree
    except Exception as e:
        logger.error(f"Error getting S3 folder tree: {e}")
        return {"name": Path(prefix).name or "root", "type": "folder", "children": [], "error": str(e)}

def _get_local_folder_tree(storage, prefix: str, file_extensions: Optional[Set[str]] = None) -> Dict[str, Any]:
    """Build a folder tree from local storage."""
    try:
        base_path = storage._get_full_path(prefix)
        if not base_path.exists():
            return {"name": Path(prefix).name or "root", "type": "folder", "children": []}
        
        tree = {"name": base_path.name or "root", "type": "folder", "children": []}
        
        for item in base_path.iterdir():
            relative_path = str(item.relative_to(storage.base_dir))
            
            if item.is_dir():
                # Recursively get the tree for this subfolder
                subtree = _get_local_folder_tree(storage, relative_path, file_extensions)
                tree["children"].append(subtree)
            else:
                # Skip files that don't match the extension filter
                if file_extensions and not any(item.name.lower().endswith(ext.lower()) for ext in file_extensions):
                    continue
                
                file_info = {
                    "name": item.name,
                    "type": "file",
                    "size": item.stat().st_size,
                    "path": relative_path,
                    "modified": item.stat().st_mtime
                }
                tree["children"].append(file_info)
        
        return tree
    except Exception as e:
        logger.error(f"Error getting local folder tree: {e}")
        return {"name": Path(prefix).name or "root", "type": "folder", "children": [], "error": str(e)}

def list_user_assets(user_id: str, 
                    file_extensions: Optional[Set[str]] = None, 
                    storage=None) -> List[Dict[str, Any]]:
    """
    Get a flat list of all assets for a user.
    
    Args:
        user_id: The user ID to get assets for
        file_extensions: Optional set of file extensions to filter by
        storage: Optional storage interface
    
    Returns:
        List of dicts with file information
    """
    tree = get_user_asset_tree(user_id, file_extensions, storage)
    flat_list = []
    
    def _flatten_tree(node):
        if node["type"] == "file":
            flat_list.append(node)
        elif node["type"] == "folder" and "children" in node:
            for child in node["children"]:
                _flatten_tree(child)
    
    _flatten_tree(tree)
    return flat_list

def download_user_assets(user_id: str, 
                        local_path: Union[str, Path],
                        file_extensions: Optional[Set[str]] = None, 
                        storage=None) -> List[Dict[str, Any]]:
    """
    Download a user's asset library from S3 to local storage.
    
    Args:
        user_id: The user ID to download assets for
        local_path: Local path to save the downloaded files
        file_extensions: Optional set of file extensions to filter by
        storage: Optional storage interface (if None, one will be created using StorageFactory)
        
    Returns:
        List of dictionaries with information about downloaded files
    """
    if not storage:
        storage = StorageFactory.get_storage()
        
    # Get the list of files in the user's asset library
    asset_list = list_user_assets(user_id, file_extensions, storage)
    local_path = Path(local_path)
    downloaded_files = []
    
    # Create the local directory structure if it doesn't exist
    os.makedirs(local_path, exist_ok=True)
    
    # Download each file
    for asset in asset_list:
        try:
            s3_key = asset["path"]
            relative_path = s3_key.split(f"videocrafter/users/{user_id}/assetlibrary/", 1)[1]
            target_path = local_path / relative_path
            
            # Ensure the directory exists
            os.makedirs(target_path.parent, exist_ok=True)
            
            # Download the file
            if storage.download(s3_key, target_path):
                asset["local_path"] = str(target_path)
                downloaded_files.append(asset)
                logger.info(f"Downloaded {s3_key} to {target_path}")
            else:
                logger.error(f"Failed to download {s3_key}")
                
        except Exception as e:
            logger.error(f"Error downloading asset {asset.get('path', 'unknown')}: {e}")
            
    return downloaded_files

def upload_to_user_library(user_id: str, 
                          local_path: Union[str, Path],
                          s3_subpath: str = "",
                          file_extensions: Optional[Set[str]] = None, 
                          storage=None) -> List[Dict[str, Any]]:
    """
    Upload files from local path to a user's asset library in S3.
    
    Args:
        user_id: The user ID to upload assets for
        local_path: Local path containing files to upload
        s3_subpath: Optional subpath within the asset library to place the files
        file_extensions: Optional set of file extensions to filter by
        storage: Optional storage interface
        
    Returns:
        List of dictionaries with information about uploaded files
    """
    if not storage:
        storage = StorageFactory.get_storage()
        
    local_path = Path(local_path)
    if not local_path.exists() or not local_path.is_dir():
        logger.error(f"Local path {local_path} does not exist or is not a directory")
        return []
        
    s3_prefix = f"videocrafter/users/{user_id}/assetlibrary/"
    if s3_subpath:
        s3_prefix = f"{s3_prefix}{s3_subpath.strip('/')}/"
        
    uploaded_files = []
    
    # Walk through the directory and upload files
    for root, _, files in os.walk(local_path):
        for filename in files:
            try:
                local_file = Path(root) / filename
                
                # Skip files with unwanted extensions
                if file_extensions and not any(filename.lower().endswith(ext.lower()) for ext in file_extensions):
                    continue
                    
                # Calculate the relative path from the base local_path
                rel_path = local_file.relative_to(local_path)
                s3_key = f"{s3_prefix}{rel_path}"
                
                # Upload the file
                if storage.upload(local_file, s3_key):
                    uploaded_info = {
                        "name": filename,
                        "local_path": str(local_file),
                        "path": s3_key,
                        "size": local_file.stat().st_size,
                        "type": "file"
                    }
                    uploaded_files.append(uploaded_info)
                    logger.info(f"Uploaded {local_file} to {s3_key}")
                else:
                    logger.error(f"Failed to upload {local_file}")
                    
            except Exception as e:
                logger.error(f"Error uploading file {os.path.join(root, filename)}: {e}")
                
    return uploaded_files

def sync_user_assets(user_id: str, 
                    local_path: Union[str, Path],
                    direction: str = "both",
                    file_extensions: Optional[Set[str]] = None, 
                    storage=None) -> Dict[str, List[Dict[str, Any]]]:
    """
    Synchronize assets between S3 and local storage.
    
    Args:
        user_id: The user ID to sync assets for
        local_path: Local path for syncing
        direction: Direction to sync: "download", "upload", or "both"
        file_extensions: Optional set of file extensions to filter by
        storage: Optional storage interface
        
    Returns:
        Dictionary with lists of downloaded and uploaded files
    """
    result = {"downloaded": [], "uploaded": []}
    
    if direction.lower() in ["download", "both"]:
        result["downloaded"] = download_user_assets(user_id, local_path, file_extensions, storage)
        
    if direction.lower() in ["upload", "both"]:
        result["uploaded"] = upload_to_user_library(user_id, local_path, "", file_extensions, storage)
        
    return result

def cleanup_old_assets(days: int = 1, storage=None) -> Dict[str, Any]:
    """
    Clean up assets older than the specified number of days.
    
    Args:
        days: Number of days to keep assets (default: 1)
        storage: Optional storage interface
        
    Returns:
        Dictionary with information about cleaned up files
    """
    if not storage:
        storage = StorageFactory.get_storage()
    
    from datetime import datetime, timedelta
    import pytz
    
    # Calculate cutoff date
    cutoff_date = datetime.now(pytz.UTC) - timedelta(days=days)
    deleted_count = 0
    deleted_files = []
    errors = []
    
    # For S3 storage
    if hasattr(storage, 's3_client'):
        try:
            # List all objects in the bucket
            paginator = storage.s3_client.get_paginator('list_objects_v2')
            # Only look at videocrafter/users/*/assetlibrary paths
            prefix = "videocrafter/users/"
            
            for page in paginator.paginate(Bucket=storage.bucket_name, Prefix=prefix):
                if 'Contents' not in page:
                    continue
                
                for obj in page['Contents']:
                    key = obj['Key']
                    last_modified = obj['LastModified']
                    
                    # Skip if not in assetlibrary
                    if 'assetlibrary' not in key:
                        continue
                        
                    # Check if the file is older than the cutoff date
                    if last_modified < cutoff_date:
                        # Delete the file
                        if storage.delete(key):
                            deleted_count += 1
                            deleted_files.append(key)
                            logger.info(f"Deleted old asset: {key}")
                        else:
                            errors.append(f"Failed to delete {key}")
            
        except Exception as e:
            error_msg = f"Error cleaning up S3 assets: {e}"
            logger.error(error_msg)
            errors.append(error_msg)
    
    # For local storage
    else:
        try:
            base_dir = storage.base_dir
            users_dir = base_dir / "videocrafter" / "users"
            
            if not users_dir.exists():
                return {
                    "deleted_count": 0,
                    "deleted_files": [],
                    "errors": ["Users directory does not exist"]
                }
            
            # Walk through all user directories
            for user_dir in users_dir.iterdir():
                if not user_dir.is_dir():
                    continue
                
                asset_lib_dir = user_dir / "assetlibrary"
                if not asset_lib_dir.exists() or not asset_lib_dir.is_dir():
                    continue
                
                # Walk through all files in the asset library
                for root, _, files in os.walk(asset_lib_dir):
                    for filename in files:
                        file_path = Path(root) / filename
                        # Get file modification time
                        mtime = datetime.fromtimestamp(file_path.stat().st_mtime, pytz.UTC)
                        
                        # Check if the file is older than the cutoff date
                        if mtime < cutoff_date:
                            try:
                                # Delete the file
                                relative_path = str(file_path.relative_to(base_dir))
                                if storage.delete(relative_path):
                                    deleted_count += 1
                                    deleted_files.append(relative_path)
                                    logger.info(f"Deleted old asset: {relative_path}")
                                else:
                                    errors.append(f"Failed to delete {relative_path}")
                            except Exception as e:
                                errors.append(f"Error deleting {file_path}: {e}")
                
        except Exception as e:
            error_msg = f"Error cleaning up local assets: {e}"
            logger.error(error_msg)
            errors.append(error_msg)
    
    # Return summary
    return {
        "deleted_count": deleted_count,
        "deleted_files": deleted_files,
        "errors": errors
    }





def get_media_info(file_path):
    """Get duration and audio presence information from media file."""
    try:
        # Get duration
        duration_cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path
        ]
        duration = float(subprocess.check_output(duration_cmd).decode().strip())
        
        # Check for audio stream
        audio_cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "a",
            "-show_entries", "stream=codec_type",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path
        ]
        audio_result = subprocess.run(audio_cmd, capture_output=True, text=True)
        has_audio = audio_result.stdout.strip() == "audio"
        
        return {
            'duration': duration,
            'has_audio': has_audio
        }
    except Exception as e:
        logger.error(f"Error getting media info: {e}")
        return {'duration': 0, 'has_audio': False}


def process_background_track(audio_path, video_duration, start_time, end_time, volume, track_index):
    """Process a single background music track with timing and volume adjustments."""
    try:
        # Get audio duration
        audio_info = get_media_info(audio_path)
        audio_duration = audio_info['duration']
        
        # Calculate proper timing
        start_time = max(0, min(start_time, video_duration))
        
        if end_time <= start_time or end_time > video_duration:
            end_time = min(video_duration, start_time + audio_duration)
        else:
            end_time = min(end_time, video_duration)
        
        duration = end_time - start_time
        
        if duration <= 0:
            logger.warning(f"Invalid duration for track {track_index}")
            return None
        
        # Ensure volume is in valid range
        volume = max(0.0, min(1.0, volume))
        
        # Create processed audio file
        output_path = tempfile.mktemp(suffix='.mp3')
        
        cmd = [
            "ffmpeg", "-y",
            "-i", audio_path,
            "-ss", "0",  # Start from beginning of audio file
            "-t", str(duration),  # Duration to extract
            "-af", f"volume={volume},aformat=channel_layouts=stereo:sample_rates=44100",
            "-c:a", "mp3",
            "-b:a", "192k",
            output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True)
        
        if result.returncode != 0:
            logger.error(f"Failed to process track {track_index}: {result.stderr}")
            return None
        
        return {
            'processed_path': output_path,
            'start_time': start_time,
            'end_time': end_time,
            'duration': duration,
            'volume': volume,
            'index': track_index
        }
    
    except Exception as e:
        logger.error(f"Error processing track {track_index}: {e}")
        return None


def create_final_mix(video_path, processed_tracks, output_path, has_original_audio):
    """Create the final video with mixed audio tracks."""
    try:
        # Build FFmpeg command
        cmd = ["ffmpeg", "-y", "-i", video_path]
        
        # Add all processed audio tracks as inputs
        for track in processed_tracks:
            cmd.extend(["-i", track['processed_path']])
        
        # Build filter complex
        filter_parts = []
        
        if has_original_audio:
            # Convert original audio to stereo for consistent mixing
            filter_parts.append("[0:a]volume=2,aformat=channel_layouts=stereo:sample_rates=44100[orig]")
            
            # Add delay filters for each background track
            for i, track in enumerate(processed_tracks):
                delay_ms = int(track['start_time'] * 1000)
                filter_parts.append(f"[{i+1}:a]adelay={delay_ms}|{delay_ms}[bg{i}]")
            
            # Mix all audio streams
            if len(processed_tracks) == 1:
                # Single background track
                filter_parts.append("[orig][bg0]amix=inputs=2:duration=first:weights=2 2[final]")
            else:
                # Multiple background tracks
                bg_inputs = ''.join([f"[bg{i}]" for i in range(len(processed_tracks))])
                filter_parts.append(f"{bg_inputs}amix=inputs={len(processed_tracks)}:duration=longest[bgmix]")
                filter_parts.append("[orig][bgmix]amix=inputs=2:duration=first:weights=2 2[final]")
        else:
            # No original audio - just mix background tracks
            for i, track in enumerate(processed_tracks):
                delay_ms = int(track['start_time'] * 1000)
                filter_parts.append(f"[{i}:a]adelay={delay_ms}|{delay_ms}[bg{i}]")
            
            if len(processed_tracks) == 1:
                filter_parts.append("[bg0]anull[final]")
            else:
                bg_inputs = ''.join([f"[bg{i}]" for i in range(len(processed_tracks))])
                filter_parts.append(f"{bg_inputs}amix=inputs={len(processed_tracks)}:duration=longest[final]")
        
        # Combine filter parts
        filter_complex = ';'.join(filter_parts)
        
        # Complete the command
        cmd.extend([
            "-filter_complex", filter_complex,
            "-map", "0:v",  # Video from original
            "-map", "[final]",  # Mixed audio
            "-c:v", "copy",  # Copy video stream
            "-c:a", "aac",  # Encode audio as AAC
            "-b:a", "256k",  # Audio bitrate
            "-ar", "44100",  # Sample rate
            "-ac", "2",  # Stereo
            output_path
        ])
        
        print(f"\nCreating final mix with {len(processed_tracks)} background tracks")
        print(f"Filter: {filter_complex}")
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            logger.error(f"FFmpeg error: {result.stderr}")
            return False
        
        # Verify output
        output_info = get_media_info(output_path)
        print(f"Output: Duration={output_info['duration']:.2f}s, Has audio={output_info['has_audio']}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error creating final mix: {e}")
        return False



def process_video_speed(video_file, speed):
    temp_file_path = None
    processed_video_path = None
    
    try:
        # Save uploaded file to a temporary location
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_file:
            for chunk in video_file.chunks():
                temp_file.write(chunk)
            temp_file_path = temp_file.name

        # Create temp output file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as output_file:
            processed_video_path = output_file.name

        # First check if the video has audio streams
        check_audio_cmd = [
            "ffprobe", "-v", "error", "-select_streams", "a:0", 
            "-show_entries", "stream=codec_type", "-of", "csv=p=0", temp_file_path
        ]
        
        has_audio = False
        try:
            result = subprocess.run(
                check_audio_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            has_audio = "audio" in result.stdout
            print(f"Audio stream detected: {has_audio}")
        except Exception as e:
            print(f"Error checking audio stream: {str(e)}")
            has_audio = False

        # FFmpeg command based on whether audio is present
        if has_audio:
            print(f"Processing video with audio at speed {speed}x")
            ffmpeg_cmd = [
                "ffmpeg", "-y", "-i", temp_file_path,
                "-filter_complex",
                f"[0:v]setpts={1/speed}*PTS[v];[0:a]atempo={min(speed, 2.0)}[a]",
                "-map", "[v]", "-map", "[a]",
                "-c:v", "libx264", "-preset", "fast", "-c:a", "aac", "-b:a", "192k",
                processed_video_path
            ]
        else:
            print(f"Processing video without audio at speed {speed}x")
            ffmpeg_cmd = [
                "ffmpeg", "-y", "-i", temp_file_path,
                "-filter:v", f"setpts={1/speed}*PTS",
                "-c:v", "libx264", "-preset", "fast",
                processed_video_path
            ]

        # Run FFmpeg
        print(f"FFmpeg command: {' '.join(ffmpeg_cmd)}")
        result = subprocess.run(
            ffmpeg_cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE
        )
        
        if result.returncode != 0:
            error_output = result.stderr.decode()
            print(f"FFmpeg error: {error_output}")
            return None

        # Clean up input temp file
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)
            
        return processed_video_path

    except Exception as e:
        print(f"Error processing video: {str(e)}")
        
        # Clean up in case of exceptions
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        if processed_video_path and os.path.exists(processed_video_path):
            os.remove(processed_video_path)
            
        return None
    temp_file_path = None
    processed_video_path = None
    
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
            f"[0:v]setpts={1/speed}*PTS[v];[0:a]atempo={min(speed, 2.0)}[a]",
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "fast", "-c:a", "aac", "-b:a", "192k",
            processed_video_path
        ]

        # Run FFmpeg
        print(f"Processing video with speed {speed}x")
        print(f"FFmpeg command: {' '.join(ffmpeg_cmd)}")
        result = subprocess.run(
            ffmpeg_cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE
        )
        
        if result.returncode != 0:
            print(f"FFmpeg error: {result.stderr.decode()}")
            return None

        # Clean up input temp file
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        print(f"Processed video saved to {processed_video_path}")
        return processed_video_path

    except Exception as e:
        print(f"Error processing video: {str(e)}")
        
        # Clean up in case of exceptions
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        if processed_video_path and os.path.exists(processed_video_path):
            os.remove(processed_video_path)
            
        return None