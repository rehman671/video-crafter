from django.contrib import admin
from django import forms
from .models import Video, Clips, Subclip, BackgroundMusic, ProcessingStatus
from django.contrib import messages
from .utils import generate_final_video, generate_audio_file, generate_srt_file, generate_clips_from_srt, generate_signed_url
import json
from .models import VideoLogs
from django.utils.html import format_html
import requests


class SubclipInline(admin.TabularInline):
    model = Subclip
    extra = 0
    fields = ['start_time', 'end_time','text', 'video_file',]

class ClipsForm(forms.ModelForm):
    class Meta:
        model = Clips
        fields = '__all__'
    
    def clean(self):
        cleaned_data = super().clean()
        # Ensure start_time has a value
        if cleaned_data.get('start_time') is None:
            cleaned_data['start_time'] = 0
        return cleaned_data

class ClipsInline(admin.TabularInline):
    model = Clips
    form = ClipsForm
    extra = 0
    ordering = ['sequence']
    readonly_fields = ['sequence']
    fields = ['sequence','start_time', 'end_time', 'text', 'video_file',]

class BackgroundMusicInline(admin.TabularInline):
    model = BackgroundMusic
    extra = 0

@admin.register(Video)
class VideoAdmin(admin.ModelAdmin):
    list_display = ['id', 'output','output_with_watermark', 'dimensions', 'created_at', 'updated_at']
    search_fields = ['id']
    list_filter = ['user']
    inlines = [ClipsInline, BackgroundMusicInline]
    actions = ['generate_clips_from_srt', 'generate_srt_file', 'generate_audio_file', 'generate_final_video']
    
    def generate_final_video(self, request, queryset:list[Video]): 
        for video in queryset:
            try:
                generate_final_video(video)
                messages.success(request, f"Final video generated successfully for Video #{video.id}")
            except Exception as e:
                messages.error(request, f"Error generating final video for Video #{video.id}: {str(e)}")

    def generate_audio_file(self, request, queryset:list[Video]):
        for video in queryset:
            try:
                success = generate_audio_file(video, request.user.id)
                if success:
                    messages.success(request, f"Audio generated successfully for Video #{video.id}")
                else:
                    messages.error(request, f"Failed to generate audio for Video #{video.id}")
            except ValueError as e:
                messages.error(request, str(e))
            except Exception as e:
                messages.error(request, f"Error generating audio for Video #{video.id}: {str(e)}")

    def generate_srt_file(self, request, queryset:list[Video]):
        for video in queryset:
            try:
                success = generate_srt_file(video, request.user.id)
                if success:
                    messages.success(request, f"SRT file generated successfully for Video #{video.id}")
                else:
                    messages.error(request, f"Failed to generate SRT file for Video #{video.id}")
            except ValueError as e:
                messages.error(request, str(e))
            except Exception as e:
                messages.error(request, f"Error generating SRT file for Video #{video.id}: {str(e)}")

            
    def generate_clips_from_srt(self, request, queryset):
        for video in queryset:
            try:
                clips_created = generate_clips_from_srt(video)
                messages.success(
                    request, 
                    f"Successfully created {clips_created} clips based on sentences for Video #{video.id}."
                )
            except ValueError as e:
                messages.error(request, str(e))
            except json.JSONDecodeError:
                messages.error(
                    request, 
                    f"Invalid JSON format in the SRT file for Video #{video.id}."
                )
            except Exception as e:
                messages.error(
                    request, 
                    f"Error processing files for Video #{video.id}: {str(e)}"
                )
    
    generate_clips_from_srt.short_description = "Generate clips from SRT file"
    generate_srt_file.short_description = "Generate SRT from text file"
    generate_audio_file.short_description = "Generate AUDIO from text file"
    generate_final_video.short_description = "Generate Final Video"

@admin.register(Clips)
class ClipsAdmin(admin.ModelAdmin):
    form = ClipsForm
    list_display = ['id', 'video', "is_changed",'start_time', 'end_time', 'text', 'created_at']
    list_filter = ['video', 'created_at']
    search_fields = ['text']
    inlines = [SubclipInline]
    
    
@admin.register(Subclip)
class SubclipAdmin(admin.ModelAdmin):
    list_display = ['id', 'clip', 'video_id', 'start_time', 'end_time', 'text', 'video_file', 'created_at']
    list_filter = ['clip__video', 'created_at', 'clip__video__user']
    search_fields = ['text', 'video_file']
    
    def video_id(self, obj):
        return obj.clip.video.id if obj.clip and obj.clip.video else None
    
    video_id.short_description = 'Video ID'

@admin.register(BackgroundMusic)
class BackgroundMusicAdmin(admin.ModelAdmin):
    list_display = ['id', 'video', 'audio_file']
    list_filter = ['video']

@admin.register(ProcessingStatus)
class ProcessingStatusAdmin(admin.ModelAdmin):
    pass


@admin.register(VideoLogs)
class VideoLogsAdmin(admin.ModelAdmin):
    list_display = ('video', 'created_at', 'log_file')
    list_filter = ('created_at','video', 'video__user')
    search_fields = ('video__id',)
    readonly_fields = ('video', 'log_preview', 'created_at', 'updated_at')
    ordering = ('-created_at',)
    fields = ['video', 'log_file','log_preview', 'created_at', 'updated_at']
    def has_add_permission(self, request):
        return False  # Logs are created automatically

    @admin.display(description='Log Preview')
    def log_preview(self, obj):
        try:
            if obj.log_file:
                log_url = generate_signed_url(obj.log_file.name)
                if log_url:
                    # Get first 500 characters from remote log file
                    response = requests.get(log_url)
                    if response.status_code == 200:
                        content = response.text
                        # Format the content in a pre tag with styling 
                        formatted_content = format_html(
                            '<div style="max-height: 400px; overflow-y: auto;">'
                            '<pre style="background-color: #f5f5f5; padding: 10px; '
                            'border: 1px solid #ddd; border-radius: 4px; '
                            'font-family: monospace; white-space: pre-wrap;">{}</pre>',
                            content, 
                        )
                            # log_url
                            # '<a href="{}" target="_blank">View Full Log</a></div>',
                        return formatted_content
                    return "Could not fetch log file"
            return "No log file available"
        except Exception as e:
            return f"Error reading log file: {str(e)}"