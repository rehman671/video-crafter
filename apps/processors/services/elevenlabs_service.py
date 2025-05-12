import requests
import json
from django.conf import settings

def validate_elevenlabs_api_key(api_key):
    """
    Validate an ElevenLabs API key
    
    Args:
        api_key: API key to validate
        
    Returns:
        Tuple (is_valid, message)
    """
    try:
        headers = {
            "xi-api-key": api_key,
            "Content-Type": "application/json"
        }
        
        # Make a request to the user info endpoint
        response = requests.get(
            f"{settings.ELEVENLABS_API_URL}/user", 
            headers=headers
        )
        
        # Check if the request was successful
        if response.status_code == 200:
            return True, "API key is valid"
        else:
            return False, f"API returned status code {response.status_code}"
            
    except Exception as e:
        return False, str(e)

def get_available_voices(api_key):
    """
    Get available voices from ElevenLabs
    
    Args:
        api_key: ElevenLabs API key
        
    Returns:
        List of voice objects or error dict
    """
    try:
        headers = {
            "xi-api-key": api_key,
            "Content-Type": "application/json"
        }
        
        # Make a request to the voices endpoint
        response = requests.get(
            f"{settings.ELEVENLABS_API_URL}/voices", 
            headers=headers
        )
        
        # Check if the request was successful
        if response.status_code == 200:
            data = response.json()
            voices = []
            
            # Format the response to just include relevant information
            for voice in data.get('voices', []):
                voices.append({
                    'voice_id': voice.get('voice_id'),
                    'name': voice.get('name'),
                    'preview_url': voice.get('preview_url'),
                    'category': voice.get('category')
                })
                
            return voices
        else:
            return {'error': f"API returned status code {response.status_code}"}
            
    except Exception as e:
        return {'error': str(e)}

def generate_speech(text, api_key, voice_id, model_id="eleven_monolingual_v1", stability=0.5, similarity_boost=0.75):
    """
    Generate speech from text using ElevenLabs API
    
    Args:
        text: Text to convert to speech
        api_key: ElevenLabs API key
        voice_id: Voice ID to use
        model_id: Model ID to use
        stability: Voice stability (0-1)
        similarity_boost: Voice similarity boost (0-1)
        
    Returns:
        Audio data or error dict
    """
    try:
        headers = {
            "xi-api-key": api_key,
            "Content-Type": "application/json"
        }
        
        data = {
            "text": text,
            "model_id": model_id,
            "voice_settings": {
                "stability": stability,
                "similarity_boost": similarity_boost
            }
        }
        
        # Make a request to the text-to-speech endpoint
        response = requests.post(
            f"{settings.ELEVENLABS_API_URL}/text-to-speech/{voice_id}", 
            json=data,
            headers=headers
        )
        
        # Check if the request was successful
        if response.status_code == 200:
            return response.content
        else:
            error_text = response.text
            try:
                error_json = response.json()
                if 'detail' in error_json:
                    error_text = error_json['detail']['message']
            except:
                pass
                
            return {'error': f"API returned status code {response.status_code}: {error_text}"}
            
    except Exception as e:
        return {'error': str(e)}
