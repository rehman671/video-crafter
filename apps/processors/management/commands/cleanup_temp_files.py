import os
import datetime
import tempfile
import shutil
from django.core.management.base import BaseCommand
from apps.processors.utils import cleanup_temp_files

class Command(BaseCommand):
    help = 'Clean up temporary files older than their respective thresholds'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force cleanup all temporary files regardless of age',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show files that would be deleted without actually deleting them',
        )

    def handle(self, *args, **options):
        self.stdout.write('Starting cleanup of temporary files...')
        
        force = options['force']
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN: No files will actually be deleted'))
            
        if force:
            self.stdout.write(self.style.WARNING('FORCE mode enabled: All temp files will be cleaned'))
        
        try:
            # If we're in force or dry run mode, use our custom implementation
            if force or dry_run:
                self._custom_cleanup(force=force, dry_run=dry_run)
            else:
                # Use the standard cleanup function
                cleanup_temp_files()
                
            self.stdout.write(self.style.SUCCESS('Successfully cleaned up temporary files'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error during cleanup: {str(e)}'))
            
    def _custom_cleanup(self, force=False, dry_run=False):
        """Custom cleanup implementation for more control and reporting"""
        temp_dir = tempfile.gettempdir()
        current_time = datetime.datetime.now()
        cleaned_files = 0
        cleaned_dirs = 0
        cleaned_stream_files = 0
        total_bytes_cleaned = 0
        
        # Check for files/folders in temp directory
        for item in os.listdir(temp_dir):
            item_path = os.path.join(temp_dir, item)
            
            # Skip if it's not a file or directory
            if not os.path.isfile(item_path) and not os.path.isdir(item_path):
                continue
                
            # Check if the item is related to our app
            is_our_temp = False
            is_stream_file = False
            
            # Check for our video files
            if os.path.isfile(item_path):
                if item.startswith("video_") and "_stream_" in item and item.endswith(".mp4"):
                    is_stream_file = True
                elif any(item.endswith(ext) for ext in ('.mp4', '.mov', '.avi', '.srt')):
                    is_our_temp = True
                
            # Check for our temporary directories
            if os.path.isdir(item_path) and 'videocrafter_temp' in item:
                is_our_temp = True
                
            # Process each type
            if is_our_temp or is_stream_file:
                # Get last modification time
                modified_time = datetime.datetime.fromtimestamp(os.path.getmtime(item_path))
                file_age = (current_time - modified_time).total_seconds()
                
                # For stream files, use a longer threshold (4 hours)
                threshold = 14400 if is_stream_file else 3600  # 4 hours or 1 hour
                
                # Delete if older than threshold or force is True
                if force or file_age > threshold:
                    try:
                        file_size = os.path.getsize(item_path) if os.path.isfile(item_path) else 0
                        
                        if not dry_run:
                            if os.path.isfile(item_path):
                                os.remove(item_path)
                                if is_stream_file:
                                    cleaned_stream_files += 1
                                else:
                                    cleaned_files += 1
                            else:
                                # Use shutil to remove directory and all its contents
                                import shutil
                                shutil.rmtree(item_path)
                                cleaned_dirs += 1
                                
                        total_bytes_cleaned += file_size
                        
                        age_str = f"{file_age/60:.1f} minutes old"
                        self.stdout.write(f"{'Would clean' if dry_run else 'Cleaned'}: {item_path} ({age_str}, {file_size/1024:.1f} KB)")
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f"Error cleaning {item_path}: {str(e)}"))
        
        # Report stats
        self.stdout.write(self.style.SUCCESS(
            f"{'' if not dry_run else '[DRY RUN] Would have '}"
            f"Cleaned: {cleaned_files} files, {cleaned_dirs} directories, {cleaned_stream_files} stream files. "
            f"Total: {total_bytes_cleaned/1048576:.2f} MB freed"
        ))
