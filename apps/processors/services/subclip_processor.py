import os
import re
from django.conf import settings
from ..models import Subclip

def create_subclip_from_text(clip, text_to_match):
    """
    Create a subclip from a specific text segment in the clip
    
    Args:
        clip: The Clip object
        text_to_match: The text to search for within the clip's text
        
    Returns:
        The created Subclip object
    """
    # Find the text in the clip content (case insensitive)
    clip_text = clip.text
    match = re.search(re.escape(text_to_match), clip_text, re.IGNORECASE)
    
    if not match:
        raise ValueError(f"Text '{text_to_match}' not found in clip content")
    
    # Get the start and end position of the matched text
    start_pos, end_pos = match.span()
    
    # Calculate timing based on position of the text
    # For simplicity, assume uniform timing across text
    # In a real implementation, this would use NLP or speech recognition for accurate timing
    duration = clip.end_time - clip.start_time
    text_length = len(clip_text)
    
    # Calculate timing proportionally based on text position
    subclip_start = clip.start_time + (start_pos / text_length) * duration
    subclip_end = clip.start_time + (end_pos / text_length) * duration
    
    # Create a subclip record
    subclip = Subclip.objects.create(
        clip=clip,
        start_time=subclip_start,
        end_time=subclip_end,
        text=text_to_match
        sequence=Subclip.objects.filter(clip=clip).count() + 1,  # Increment sequence number
    )
    
    # In a real implementation, we would generate the actual video file here
    # For now, we'll just store the timing information
    
    return subclip
