import logging
from typing import Dict, List, Optional, Set, Any, Union
from pathlib import Path
from .services.s3_service import StorageFactory, S3Config
import os

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
