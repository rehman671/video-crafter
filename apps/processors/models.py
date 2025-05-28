from django.db import models
from django.contrib.auth.models import User
from .constants import RESOLUTIONS

class Video(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=225, null=True, blank=True)
    output = models.FileField(upload_to="output/", null=True, blank=True)
    text_file = models.FileField(upload_to="text_files/", null=True, blank=True)
    content = models.TextField(null=True, blank=True)
    audio_file = models.FileField(upload_to="audio_files/", null=True, blank=True)
    srt_file = models.FileField(upload_to="srt_files/", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    dimensions = models.CharField(max_length=255,choices=RESOLUTIONS, default="16:9")
    subtitle_font = models.ForeignKey("core.Font", on_delete=models.SET_NULL, null=True, blank=True)
    font_size = models.PositiveIntegerField(default=20)
    font_color = models.CharField(max_length=20, default="#FFFFFF")
    box_roundness = models.PositiveIntegerField(default=0)
    elevenlabs_api_key = models.CharField(max_length=100, blank=True, null=True)
    voice_id = models.CharField(max_length=50, blank=True, null=True)
    subtitle_box_color = models.CharField(max_length=20, default="#000000")
    output_with_bg = models.FileField(upload_to="output_bg/", null=True, blank=True)
    output_with_watermark = models.FileField(upload_to="output_watermark/", null=True, blank=True)
    output_with_bg_watermark = models.FileField(upload_to="output_bg_watermark/", null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

class Clips(models.Model):
    video = models.ForeignKey(Video, on_delete=models.CASCADE)
    video_end_time = models.FloatField(null=True, blank=True)
    start_time = models.FloatField(null=True, blank= True)  # Default to 0 so it's never null
    end_time = models.FloatField(null=True, blank=True)  # Allow null
    video_file = models.FileField(upload_to="clips/", null=True, blank=True)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    sequence = models.PositiveIntegerField(default=0)  # Sequence number for ordering clips
    is_changed = models.BooleanField(default=False)  # Flag to indicate if the clip has been changed

    class Meta:
        ordering = ["sequence", "start_time"]

    def __str__(self):
        return self.text[:50]  # Return the first 50 characters of the text for display

    def clean(self):
        # Always ensure start_time has a value
        if self.start_time is None:
            self.start_time = 0
        super().clean()

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        # Remove single quotes from text field if present
        if self.text:
            self.text = self.text.replace("'", "")
        
        # Ensure start_time has a default value if it's None - this is crucial
        if self.start_time is None:
            self.start_time = 0
        
        # Call the parent save method
        super().save(force_insert, force_update, using, update_fields)
    
class Subclip(models.Model):
    clip = models.ForeignKey(Clips, on_delete=models.CASCADE)
    start_time = models.FloatField(null=True, blank=True)
    end_time = models.FloatField(null=True, blank=True)
    text = models.TextField()
    video_file = models.FileField(upload_to="subclips/", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["start_time"]

class BackgroundMusic(models.Model):
    video = models.ForeignKey(Video, on_delete=models.CASCADE)
    audio_file = models.FileField(upload_to="bg_music/")
    start_time = models.FloatField()
    end_time = models.FloatField()
    volumn = models.FloatField(default=0.5)  # Volume level (0.0 to 1.0)

class ProcessingStatus(models.Model):
    """Tracks the status of video processing"""
    video = models.OneToOneField(Video, on_delete=models.CASCADE, related_name='processing_status')
    status = models.CharField(max_length=20, choices=[
        ('not_started', 'Not Started'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('error', 'Error'),
        ('cancelled', 'Cancelled')
    ], default='not_started')
    progress = models.IntegerField(default=0)  # Progress as a percentage (0-100)
    current_step = models.CharField(max_length=100, blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Processing status for Video #{self.video.id}: {self.status} ({self.progress}%)"