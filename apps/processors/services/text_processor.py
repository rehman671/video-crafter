import re
import io
from django.conf import settings
from django.core.files.storage import default_storage
from ..models import Clips

def process_text_file(video):
    """Process text file and create clips from it"""
    try:
        # Read the text file using storage API
        with default_storage.open(video.text_file.name, 'r', encoding='utf-8') as file:
            text_content = file.read()
        
        # Split text by periods and new lines
        # First, split by periods
        sentences = re.split(r'(?<=[.!?])\s+', text_content)
        
        # Now process each sentence and further split if there are new lines
        clips_text = []
        for sentence in sentences:
            # Skip empty sentences
            if not sentence.strip():
                continue
                
            # Split by new lines
            lines = sentence.split('\n')
            for line in lines:
                line = line.strip()
                if line:  # Skip empty lines
                    clips_text.append(line)
        
        # Create clips from text segments
        created_clips = []
        for i, text in enumerate(clips_text):
            # Assume each clip is approximately 3 seconds
            start_time = 0
            end_time = 0
            
            clip = Clips.objects.create(
                video=video,
                text=text,
                start_time=start_time,
                end_time=end_time,
                # Video end time will be set when processing is complete
                video_end_time=None  
            )
            
            created_clips.append(clip)
        
        return created_clips
        
    except Exception as e:
        # Log the error
        print(f"Error processing text file: {e}")
        raise

def update_text_file(video, old_text, new_text):
    """
    Update the video's text file by replacing old_text with new_text
    
    Args:
        video: The Video object
        old_text: The text to be replaced
        new_text: The new text to replace with
        
    Returns:
        True if successful
    """
    try:
        # Read the current content of the file using storage API
        with default_storage.open(video.text_file.name, 'r', encoding='utf-8') as file:
            content = file.read()
        
        # Replace the old text with the new text
        # We use re.escape to ensure special regex characters are treated literally
        # We use a word boundary to ensure we're replacing the exact text
        updated_content = re.sub(
            r'\b' + re.escape(old_text) + r'\b', 
            new_text, 
            content
        )
        
        # If the content didn't change, try without word boundaries
        if updated_content == content:
            updated_content = content.replace(old_text, new_text)
        
        # Write the updated content back to the file using storage API
        # Create a ContentFile to save back to storage
        from django.core.files.base import ContentFile
        default_storage.delete(video.text_file.name)  # Delete existing file
        default_storage.save(video.text_file.name, ContentFile(updated_content.encode('utf-8')))
        
        return True
        
    except Exception as e:
        # Log the error
        print(f"Error updating text file: {e}")
        raise

def sync_text_file_from_clips(video):
    """
    Regenerate the entire text file based on current clips
    
    Args:
        video: The Video object
    
    Returns:
        True if successful
    """
    try:
        # Get all clips for the video ordered by start_time
        clips = Clips.objects.filter(video=video).order_by('start_time')
        
        # Create content from clips
        content = ""
        for clip in clips:
            # Add each clip's text followed by a period and new line
            content += clip.text
            if not clip.text.endswith(('.', '!', '?')):
                content += '.'
            content += '\n\n'
        
        # Write the updated content to the file using storage API
        from django.core.files.base import ContentFile
        default_storage.delete(video.text_file.name)  # Delete existing file
        default_storage.save(video.text_file.name, ContentFile(content.encode('utf-8')))
        
        return True
        
    except Exception as e:
        # Log the error
        print(f"Error syncing text file: {e}")
        raise