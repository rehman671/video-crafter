from rest_framework import serializers
from .models import BackgroundMusic, Video

class BackgroundMusicSerializer(serializers.ModelSerializer):
    """
    Serializer for BackgroundMusic model
    """
    filename = serializers.SerializerMethodField()
    duration = serializers.SerializerMethodField()
    
    class Meta:
        model = BackgroundMusic
        fields = ['id', 'video', 'audio_file', 'start_time', 'end_time', 'filename', 'duration']
        read_only_fields = ['id', 'filename', 'duration']
    
    def get_filename(self, obj):
        """Get the filename of the audio file"""
        if obj.audio_file:
            return obj.audio_file.name.split('/')[-1]
        return None
    
    def get_duration(self, obj):
        """Get the duration of the audio segment"""
        if obj.start_time is not None and obj.end_time is not None:
            return obj.end_time - obj.start_time
        return None
    
    def validate(self, data):
        """Validate start and end times"""
        start_time = data.get('start_time', 0)
        end_time = data.get('end_time')
        
        if end_time is not None and end_time <= start_time:
            raise serializers.ValidationError("End time must be greater than start time")
        
        return data
