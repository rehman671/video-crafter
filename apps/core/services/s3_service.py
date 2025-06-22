import os
import io
import logging
import boto3
from botocore.exceptions import ClientError
from typing import Optional, Union, BinaryIO
from pathlib import Path
from django.conf import settings

# from apps.core.api.serializers import UserAssetSerializer

logger = logging.getLogger(__name__)

class S3Config:
    """Configuration for S3 access."""
    
    def __init__(
        self,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        region: str = 'us-east-1',
        bucket_name: Optional[str] = None,
        endpoint_url: Optional[str] = None
    ):
        self.access_key = access_key or getattr(settings, 'AWS_ACCESS_KEY_ID', None)
        self.secret_key = secret_key or getattr(settings, 'AWS_SECRET_ACCESS_KEY', None)
        self.region = region or getattr(settings, 'AWS_REGION', 'us-east-1')
        self.bucket_name = bucket_name or getattr(settings, 'AWS_STORAGE_BUCKET_NAME', None)
        self.endpoint_url = endpoint_url or getattr(settings, 'AWS_S3_ENDPOINT_URL', None)
        
    @property
    def is_configured(self) -> bool:
        """Check if S3 is properly configured."""
        return bool(self.access_key and self.secret_key and self.bucket_name)


class StorageInterface:
    """Base interface for storage operations."""
    
    def upload(self, file_path: Union[str, Path], object_key: str) -> bool:
        """Upload a file to storage."""
        raise NotImplementedError
        
    def upload_fileobj(self, file_obj: BinaryIO, object_key: str) -> bool:
        """Upload a file-like object to storage."""
        raise NotImplementedError
        
    def download(self, object_key: str, file_path: Union[str, Path]) -> bool:
        """Download a file from storage."""
        raise NotImplementedError
        
    def download_fileobj(self, object_key: str) -> Optional[BinaryIO]:
        """Download and return a file-like object."""
        raise NotImplementedError
        
    def get_url(self, object_key: str) -> str:
        """Get URL for an object."""
        raise NotImplementedError
        
    def delete(self, object_key: str) -> bool:
        """Delete an object from storage."""
        raise NotImplementedError
        
    def exists(self, object_key: str) -> bool:
        """Check if an object exists in storage."""
        raise NotImplementedError
        
    def get_size(self, object_key: str) -> Optional[int]:
        """Get the size of an object in bytes."""
        raise NotImplementedError


class S3Storage(StorageInterface):
    """AWS S3 storage implementation."""
    
    def __init__(self, config: S3Config):
        self.config = config
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=config.access_key,
            aws_secret_access_key=config.secret_key,
            region_name=config.region,
            endpoint_url=config.endpoint_url
        )
        self.bucket_name = config.bucket_name
        
    def upload(self, file_path: Union[str, Path], object_key: str) -> bool:
        try:
            file_path = Path(file_path)
            self.s3_client.upload_file(
                str(file_path),
                self.bucket_name,
                object_key
            )
            logger.info(f"Uploaded {file_path} to S3 as {object_key}")
            return True
        except ClientError as e:
            logger.error(f"S3 upload error: {e}")
            return False
            
    def upload_fileobj(self, file_obj: BinaryIO, object_key: str) -> bool:
        try:
            self.s3_client.upload_fileobj(
                file_obj,
                self.bucket_name,
                object_key
            )
            logger.info(f"Uploaded file object to S3 as {object_key}")
            return True
        except ClientError as e:
            logger.error(f"S3 upload_fileobj error: {e}")
            return False
            
    def download(self, object_key: str, file_path: Union[str, Path]) -> bool:
        try:
            file_path = Path(file_path)
            os.makedirs(file_path.parent, exist_ok=True)
            self.s3_client.download_file(
                self.bucket_name,
                object_key,
                str(file_path)
            )
            logger.info(f"Downloaded {object_key} from S3 to {file_path}")
            return True
        except ClientError as e:
            logger.error(f"S3 download error: {e}")
            return False
            
    def download_fileobj(self, object_key: str) -> Optional[BinaryIO]:
        try:
            file_obj = io.BytesIO()
            self.s3_client.download_fileobj(
                self.bucket_name,
                object_key,
                file_obj
            )
            file_obj.seek(0)
            logger.info(f"Downloaded {object_key} from S3 to file object")
            return file_obj
        except ClientError as e:
            logger.error(f"S3 download_fileobj error: {e}")
            return None
            
    def get_url(self, object_key: str) -> str:
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self.bucket_name,
                    'Key': object_key
                },
                ExpiresIn=3600  # URL valid for 1 hour
            )
            return url
        except ClientError as e:
            logger.error(f"S3 get_url error: {e}")
            return ""
            
    def delete(self, object_key: str) -> bool:
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=object_key
            )
            logger.info(f"Deleted {object_key} from S3")
            return True
        except ClientError as e:
            logger.error(f"S3 delete error: {e}")
            return False
            
    def exists(self, object_key: str) -> bool:
        """Check if an object exists in S3."""
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=object_key)
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return False
            logger.error(f"S3 exists check error: {e}")
            return False
            
    def get_size(self, object_key: str) -> Optional[int]:
        """Get the size of an S3 object in bytes."""
        try:
            response = self.s3_client.head_object(Bucket=self.bucket_name, Key=object_key)
            return response.get('ContentLength')
        except ClientError as e:
            logger.error(f"S3 get_size error: {e}")
            return None


class LocalStorage(StorageInterface):
    """Local filesystem storage implementation."""
    
    def __init__(self, base_dir: Union[str, Path] = None):
        if base_dir is None:
            base_dir = os.environ.get('LOCAL_STORAGE_PATH', 'storage')
        self.base_dir = Path(base_dir)
        os.makedirs(self.base_dir, exist_ok=True)
        logger.info(f"Local storage initialized at {self.base_dir}")
        
    def _get_full_path(self, object_key: str) -> Path:
        """Convert object key to full filesystem path."""
        return self.base_dir / object_key
        
    def upload(self, file_path: Union[str, Path], object_key: str) -> bool:
        try:
            file_path = Path(file_path)
            destination = self._get_full_path(object_key)
            os.makedirs(destination.parent, exist_ok=True)
            
            with open(file_path, 'rb') as src, open(destination, 'wb') as dst:
                dst.write(src.read())
                
            logger.info(f"Copied {file_path} to local storage as {object_key}")
            return True
        except Exception as e:
            logger.error(f"Local upload error: {e}")
            return False
            
    def upload_fileobj(self, file_obj: BinaryIO, object_key: str) -> bool:
        try:
            destination = self._get_full_path(object_key)
            os.makedirs(destination.parent, exist_ok=True)
            
            with open(destination, 'wb') as dst:
                dst.write(file_obj.read())
                
            logger.info(f"Saved file object to local storage as {object_key}")
            return True
        except Exception as e:
            logger.error(f"Local upload_fileobj error: {e}")
            return False
            
    def download(self, object_key: str, file_path: Union[str, Path]) -> bool:
        try:
            source = self._get_full_path(object_key)
            file_path = Path(file_path)
            os.makedirs(file_path.parent, exist_ok=True)
            
            with open(source, 'rb') as src, open(file_path, 'wb') as dst:
                dst.write(src.read())
                
            logger.info(f"Copied {object_key} from local storage to {file_path}")
            return True
        except Exception as e:
            logger.error(f"Local download error: {e}")
            return False
            
    def download_fileobj(self, object_key: str) -> Optional[BinaryIO]:
        try:
            source = self._get_full_path(object_key)
            file_obj = io.BytesIO()
            
            with open(source, 'rb') as src:
                file_obj.write(src.read())
                
            file_obj.seek(0)
            logger.info(f"Read {object_key} from local storage to file object")
            return file_obj
        except Exception as e:
            logger.error(f"Local download_fileobj error: {e}")
            return None
            
    def get_url(self, object_key: str) -> str:
        # For local storage, return a file URI
        full_path = self._get_full_path(object_key)
        return f"file://{full_path.absolute()}"
            
    def delete(self, object_key: str) -> bool:
        try:
            full_path = self._get_full_path(object_key)
            if full_path.exists():
                os.remove(full_path)
                logger.info(f"Deleted {object_key} from local storage")
                return True
            logger.warning(f"File {object_key} not found in local storage")
            return False
        except Exception as e:
            logger.error(f"Local delete error: {e}")
            return False
            
    def exists(self, object_key: str) -> bool:
        """Check if an object exists in storage."""
        try:
            full_path = self._get_full_path(object_key)
            return full_path.exists()
        except Exception as e:
            logger.error(f"Local exists check error: {e}")
            return False
            
    def get_size(self, object_key: str) -> Optional[int]:
        """Get the size of an object in bytes."""
        try:
            full_path = self._get_full_path(object_key)
            if full_path.exists():
                return full_path.stat().st_size
            return None
        except Exception as e:
            logger.error(f"Local get_size error: {e}")
            return None


class StorageFactory:
    """Factory to create appropriate storage implementation."""
    
    @staticmethod
    def get_storage(s3_config: Optional[S3Config] = None, local_path: Optional[str] = None) -> StorageInterface:
        """
        Get storage implementation based on configuration.
        Falls back to local storage if S3 is not properly configured.
        """
        if s3_config is None:
            s3_config = S3Config()
            
        if s3_config.is_configured:
            logger.info("Using S3 storage")
            return S3Storage(s3_config)
        else:
            logger.info("S3 not configured, using local storage")
            return LocalStorage(local_path)

import zipfile
import mimetypes
from typing import List, Dict, Any
from ..models import UserAsset, User

def get_s3_client():
    """Get a configured S3 client"""
    return boto3.client(
        's3',
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_REGION
    )

def get_user_root_folder(user_id: int) -> str:
    """Get the root S3 folder path for a user"""
    return f"users/{user_id}/assets/"

def upload_file_to_s3(file_obj, key: str, content_type: str = None) -> bool:
    """
    Upload a file object to S3
    
    Args:
        file_obj: File-like object or bytes
        key: S3 key (path)
        content_type: MIME type, auto-detected if None
        
    Returns:
        True if successful, False otherwise
    """
    s3_client = get_s3_client()
    
    if not content_type:
        # Try to guess the content type
        content_type, _ = mimetypes.guess_type(key)
        
    try:
        extra_args = {}
        if content_type:
            extra_args['ContentType'] = content_type
        
        s3_client.upload_fileobj(
            file_obj,
            settings.AWS_STORAGE_BUCKET_NAME,
            key,
            ExtraArgs=extra_args
        )
        return True
    except ClientError:
        return False

def delete_from_s3(key: str) -> bool:
    """
    Delete a file from S3
    
    Args:
        key: S3 key (path)
        
    Returns:
        True if successful, False otherwise
    """
    s3_client = get_s3_client()
    
    try:
        logger.info(f"Attempting to delete file from S3: {key}")
        response = s3_client.delete_object(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            Key=key
        )
        logger.info(f"S3 delete response: {response}")
        return True
    except ClientError as e:
        logger.error(f"Error deleting file from S3: {key}, Error: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error deleting from S3: {key}, Error: {str(e)}")
        return False

def delete_folder_from_s3(folder_key: str) -> bool:
    """
    Delete a folder and all its contents from S3
    
    Args:
        folder_key: S3 folder key (path)
        
    Returns:
        True if successful, False otherwise
    """
    if not folder_key.endswith('/'):
        folder_key += '/'
        
    s3_client = get_s3_client()
    
    try:
        logger.info(f"Attempting to delete folder from S3: {folder_key}")
        
        # List all objects in this folder
        objects_to_delete = []
        paginator = s3_client.get_paginator('list_objects_v2')
        pages = paginator.paginate(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            Prefix=folder_key
        )
        
        for page in pages:
            if 'Contents' in page:
                for obj in page['Contents']:
                    objects_to_delete.append({'Key': obj['Key']})
                    logger.debug(f"Marked for deletion: {obj['Key']}")
        
        logger.info(f"Found {len(objects_to_delete)} objects to delete in folder {folder_key}")
        
        # Delete the objects in batches of 1000 (S3 limit)
        if objects_to_delete:
            for i in range(0, len(objects_to_delete), 1000):
                batch = objects_to_delete[i:i+1000]
                logger.info(f"Deleting batch of {len(batch)} objects")
                response = s3_client.delete_objects(
                    Bucket=settings.AWS_STORAGE_BUCKET_NAME,
                    Delete={'Objects': batch}
                )
                
                # Log success and errors
                if 'Deleted' in response:
                    logger.info(f"Successfully deleted {len(response['Deleted'])} objects")
                if 'Errors' in response and response['Errors']:
                    for error in response['Errors']:
                        logger.error(f"Error deleting {error['Key']}: {error['Code']} - {error['Message']}")
                
        return True
    except ClientError as e:
        logger.error(f"ClientError deleting folder from S3: {folder_key}, Error: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error deleting folder from S3: {folder_key}, Error: {str(e)}")
        return False

def rename_in_s3(old_key: str, new_key: str) -> bool:
    """
    Rename a file in S3 (copy then delete, as S3 doesn't have a native rename)
    
    Args:
        old_key: Current S3 key (path)
        new_key: New S3 key (path)
        
    Returns:
        True if successful, False otherwise
    """
    s3_client = get_s3_client()
    
    try:
        logger.info(f"Renaming object in S3 from {old_key} to {new_key}")
        
        # For folders, just return True as we'll handle the children separately
        if old_key.endswith('/') and new_key.endswith('/'):
            return True
            
        # Copy the object to the new key
        s3_client.copy_object(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            CopySource={'Bucket': settings.AWS_STORAGE_BUCKET_NAME, 'Key': old_key},
            Key=new_key
        )
        
        # Delete the old object
        s3_client.delete_object(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            Key=old_key
        )
        
        logger.info(f"Successfully renamed {old_key} to {new_key}")
        return True
        
    except ClientError as e:
        logger.error(f"Error renaming {old_key} to {new_key}: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error renaming in S3: {str(e)}")
        return False

def extract_and_upload_zip(user: User, zip_file, parent_folder: str = '') -> List[UserAsset]:
    """
    Extract ZIP file and upload its contents to S3 maintaining folder structure
    
    Args:
        user: User object
        zip_file: ZIP file object
        parent_folder: Parent folder to extract the ZIP into
        
    Returns:
        List of created UserAsset objects
    """
    user_root = get_user_root_folder(user.id)
    
    # Combine user root with optional parent folder
    if parent_folder:
        user_folder = f"{user_root}{parent_folder.strip('/')}/"
    else:
        user_folder = user_root
    
    created_assets = []
    folder_set = set()  # Track folders to avoid duplicates
    
    with zipfile.ZipFile(zip_file) as zip_ref:
        # Process directories first to ensure the structure exists
        for file_info in zip_ref.infolist():
            if file_info.is_dir():
                folder_path = file_info.filename
                s3_key = f"{user_folder}{folder_path}"
                
                # Create folder asset in database
                asset, created = UserAsset.objects.update_or_create(
                    user=user,
                    key=s3_key,
                    defaults={
                        'filename': os.path.basename(folder_path.rstrip('/')),
                        'is_folder': True,
                        'parent_folder': os.path.dirname(s3_key.rstrip('/'))
                    }
                )
                
                if created:
                    created_assets.append(asset)
                
                # Add to tracking set
                folder_set.add(s3_key)
                
                # Also add parent folders
                parts = folder_path.split('/')
                for i in range(1, len(parts)):
                    parent_path = '/'.join(parts[:i]) + '/'
                    parent_key = f"{user_folder}{parent_path}"
                    
                    if parent_key not in folder_set:
                        folder_set.add(parent_key)
                        parent_name = os.path.basename(parent_path.rstrip('/'))
                        parent_parent = os.path.dirname(parent_key.rstrip('/'))
                        
                        asset, created = UserAsset.objects.update_or_create(
                            user=user,
                            key=parent_key,
                            defaults={
                                'filename': parent_name,
                                'is_folder': True,
                                'parent_folder': parent_parent
                            }
                        )
                        
                        if created:
                            created_assets.append(asset)
        
        # Now process files
        for file_info in zip_ref.infolist():
            if not file_info.is_dir():
                file_path = file_info.filename
                file_name = os.path.basename(file_path)
                file_size = file_info.file_size
                
                # Determine the S3 key
                s3_key = f"{user_folder}{file_path}"
                parent_folder_key = os.path.dirname(s3_key)
                
                # Read file content
                with zip_ref.open(file_info) as file_obj:
                    content = io.BytesIO(file_obj.read())
                    
                    # Guess content type
                    content_type, _ = mimetypes.guess_type(file_path)
                    
                    # Upload to S3
                    upload_result = upload_file_to_s3(content, s3_key, content_type)
                    
                    if upload_result:
                        # Create asset record
                        asset = UserAsset.objects.create(
                            user=user,
                            key=s3_key,
                            filename=file_name,
                            file_size=file_size,
                            content_type=content_type or '',
                            is_folder=False,
                            parent_folder=parent_folder_key
                        )
                        
                        created_assets.append(asset)
    
    return created_assets

# def list_user_assets(user: User, folder: str = '') -> Dict[str, Any]:
#     """
#     List assets for a user in a specific folder
    
#     Args:
#         user: User object
#         folder: Folder path (relative to user root)
        
#     Returns:
#         Dict with folders and files
#     """
#     user_root = get_user_root_folder(user.id)
    
#     # Determine the full path to list
#     if folder:
#         list_path = f"{user_root}{folder.strip('/')}"
#         if not list_path.endswith('/'):
#             list_path += '/'
#     else:
#         list_path = user_root
    
#     # Query database for assets in this folder
#     assets = UserAsset.objects.filter(
#         user=user,
#         key__startswith=list_path
#     )
    
#     # Separate direct children from descendants
#     folders = []
#     files = []
    
#     for asset in assets:
#         # Skip the folder itself
#         if asset.key == list_path:
#             continue
            
#         # Skip assets not directly in this folder
#         relative_path = asset.key[len(list_path):]
#         if '/' in relative_path and not asset.key.endswith('/'):
#             continue
            
#         if asset.is_folder:
#             folders.append(UserAssetSerializer(asset).data)
#         else:
#             files.append(UserAssetSerializer(asset).data)
    
#     return {
#         'current_folder': list_path,
#         'folders': folders,
#         'files': files
#     }


    def bulk_delete_from_s3(keys: List[str]) -> Dict[str, bool]:
        """
        Bulk delete multiple objects from S3
        
        Args:
            keys: List of S3 keys to delete
            
        Returns:
            Dict mapping keys to success status
        """
        s3_client = get_s3_client()
        results = {}
        
        try:
            # Prepare objects for deletion
            objects_to_delete = [{'Key': key} for key in keys]
            
            # Delete in batches of 1000 (S3 limit)
            for i in range(0, len(objects_to_delete), 1000):
                batch = objects_to_delete[i:i+1000]
                
                response = s3_client.delete_objects(
                    Bucket=settings.AWS_STORAGE_BUCKET_NAME,
                    Delete={'Objects': batch}
                )
                
                # Process successful deletions
                if 'Deleted' in response:
                    for deleted in response['Deleted']:
                        results[deleted['Key']] = True
                
                # Process errors
                if 'Errors' in response:
                    for error in response['Errors']:
                        results[error['Key']] = False
                        logger.error(f"S3 delete error for {error['Key']}: {error['Code']} - {error['Message']}")
            
            # Mark any remaining keys as successful if not in results
            for key in keys:
                if key not in results:
                    results[key] = True
                    
        except ClientError as e:
            logger.error(f"S3 bulk delete error: {str(e)}")
            # Mark all as failed
            for key in keys:
                results[key] = False
        
        return results