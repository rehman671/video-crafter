import os
import shutil
import glob
import logging
from datetime import datetime, timedelta
import tempfile

def cleanup_temp_files(temp_dir=None, max_age_days=1, file_patterns=None):
    """
    Clean up temporary files in the specified directory.
    
    Args:
        temp_dir (str): Directory containing temporary files. If None, uses system temp directory.
        max_age_days (int): Files older than this many days will be removed.
        file_patterns (list): List of file patterns to clean up (e.g., ["*.mp4", "*.tmp"]).
                            If None, all files in temp_dir will be considered.
    
    Returns:
        tuple: (int, list) - Count of files removed and list of errors encountered
    """
    try:
        # Set default temp directory if not provided
        if temp_dir is None:
            temp_dir = tempfile.gettempdir()
        
        # Set default patterns if not provided
        if file_patterns is None:
            file_patterns = ["*"]
            
        logging.info(f"Cleaning up temporary files in {temp_dir}")
        
        # Calculate cutoff date
        cutoff_date = datetime.now() - timedelta(days=max_age_days)
        
        files_removed = 0
        errors = []
        
        # Process each pattern
        for pattern in file_patterns:
            file_path_pattern = os.path.join(temp_dir, pattern)
            for file_path in glob.glob(file_path_pattern):
                try:
                    # Skip directories unless explicitly asked to remove them
                    if os.path.isdir(file_path) and pattern != '**/':
                        continue
                        
                    # Check file modification time
                    mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
                    if mtime < cutoff_date:
                        if os.path.isdir(file_path):
                            shutil.rmtree(file_path)
                        else:
                            os.remove(file_path)
                        files_removed += 1
                        logging.debug(f"Removed: {file_path}")
                except Exception as e:
                    errors.append(f"Error removing {file_path}: {str(e)}")
                    logging.error(f"Failed to remove {file_path}: {str(e)}")
        
        logging.info(f"Cleanup completed: {files_removed} files removed, {len(errors)} errors")
        return files_removed, errors
        
    except Exception as e:
        logging.error(f"Cleanup failed: {str(e)}")
        return 0, [f"Cleanup operation failed: {str(e)}"]