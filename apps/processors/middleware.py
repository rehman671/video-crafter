import logging
import os
import tempfile
import glob
from django.conf import settings
from django.core.files.storage import default_storage

class MediaFileAccessMiddleware:
    """
    Middleware to track access to media files and update their access times.
    Compatible with both local filesystem and S3 storage.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.media_url = settings.MEDIA_URL
        # Keep media_root for local cached files
        self.media_root = getattr(settings, 'MEDIA_ROOT', '')
        # Determine storage type - useful for conditional logic
        self.is_s3_storage = 'S3' in str(default_storage.__class__)
        
    def __call__(self, request):
        response = self.get_response(request)
        
        # Update access time for update_clip files
        if request.path.startswith(self.media_url):
            try:
                # Extract the file path from the URL
                rel_path = request.path[len(self.media_url):]
                
                # Log media file access regardless of storage backend
                logging.debug(f"Media file accessed: {rel_path}")
                
                # Get filename for potential cached files
                file_name = os.path.basename(rel_path)
                base_name = os.path.splitext(file_name)[0]
                
                # For local storage, we can update the access times
                if not self.is_s3_storage and self.media_root:
                    file_path = os.path.join(self.media_root, rel_path)
                    if os.path.exists(file_path):
                        # Touch the file to update access time
                        os.utime(file_path, None)
                
                # Check if this is a video file - this part still works with S3
                # since cached files are local regardless of storage backend
                if "_output.mp4" in file_name:
                    video_id = base_name.replace("video_", "").replace("_output", "")
                    
                    # Look for cached versions in temp directory
                    pattern = os.path.join(tempfile.gettempdir(), f"video_{video_id}_*.mp4")
                    for cached_file in glob.glob(pattern):
                        try:
                            # Update access time of cached file
                            os.utime(cached_file, None)
                            logging.debug(f"Updated access time for cached file: {cached_file}")
                        except OSError as e:
                            logging.error(f"Error updating cached file access time: {str(e)}")
                            
            except Exception as e:
                logging.error(f"Error in media file access tracking: {str(e)}")
                
        return response
    
    def _get_normalized_path(self, path):
        """
        Helper method to normalize paths depending on storage backend
        """
        # Remove any leading slash if present
        if path.startswith('/'):
            path = path[1:]
        return path