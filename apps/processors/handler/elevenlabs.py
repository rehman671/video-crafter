import os
import requests
import json
from typing import Dict, Any, Optional, Tuple
import time

class ElevenLabsHandler:
    def __init__(self, api_key: str, voice_id: str = "21m00Tcm4TlvDq8ikWAM"):
        self.api_key = api_key
        self.voice_id = voice_id
        self.base_url = "https://api.elevenlabs.io/v1"
        self._verify_api_key()
        
    def _verify_voice_id(self) -> bool:
        """Verify if the voice ID is valid by directly checking with the API"""
        headers = {
            "Accept": "application/json",
            "xi-api-key": self.api_key
        }
        
        url = f"{self.base_url}/voices/{self.voice_id}"
        
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            return True
        elif response.status_code == 404:
            raise ValueError(f"Invalid voice ID: {self.voice_id}. Voice not found.")
        else:
            raise Exception(f"Error verifying voice ID: {response.text}")
            
    def _verify_api_key(self) -> bool:
        """Verify if the API key is valid by checking user info and voice ID validity"""
        try:
            # Check if API key is valid
            user_info = self.get_user_info()
            
            # Check if voice ID is valid using direct API check
                
            return True
        except Exception as e:
            raise ValueError(f"Invalid Elevenlabs Api Key")
    
    def get_user_info(self) -> Dict:
        """Get user information including subscription and remaining credits"""
        headers = {
            "Accept": "application/json",
            "xi-api-key": self.api_key
        }
        
        url = f"{self.base_url}/user"
        
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"Error getting user info: {response.text}")
    
    def get_remaining_credits(self) -> Tuple[int, int]:
        """Get remaining character credits and total character quota"""
        user_info = self.get_user_info()
        subscription = user_info.get("subscription", {})
        character_count = subscription.get("character_count", 0)
        character_limit = subscription.get("character_limit", 0)
        return  character_limit, character_count
    
    def has_sufficient_credits(self, text_length: int) -> bool:
        """Check if there are sufficient credits for the given text length"""
        remaining, _ = self.get_remaining_credits()
        print(self.get_remaining_credits())
        print(f"Remaining credits: {remaining}")
        print(f"Text length: {text_length}")
        return remaining >= (text_length*2.5)
        
    def generate_voiceover(self, 
                          text: str, 
                          output_path: str, 
                          voice_settings: Optional[Dict[str, Any]] = None) -> str:
        """Generate voiceover using ElevenLabs API"""
        
        # Check for sufficient credits
        if not self.has_sufficient_credits(len(text)):
            raise Exception("Insufficient credits to generate voiceover")
        
        if voice_settings is None:
            voice_settings = {
                "stability": 0.84,
                "similarity_boost": 1,
                "style": 0.0,
                "use_speaker_boost": True,
                "speed": 1.1,
            }
            
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": self.api_key
        }
        
        data = {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": voice_settings
        }
        
        url = f"{self.base_url}/text-to-speech/{self.voice_id}/stream"
        
        response = requests.post(url, json=data, headers=headers)
        
        if response.status_code == 200:
            with open(output_path, "wb") as f:
                f.write(response.content)
            return output_path
        else:
            error_msg = response.text
            # Check for specific ElevenLabs error types
            if "payment_issue" in error_msg or "failed or incomplete payment" in error_msg:
                raise Exception("ElevenLabs payment issue: Your subscription has a failed or incomplete payment. Complete the latest invoice to continue usage.")
            elif response.status_code == 401:
                raise Exception("Invalid ElevenLabs API key")
            elif response.status_code == 404:
                raise Exception("Invalid Voice ID")
            else:
                raise Exception(f"Error generating voiceover: {response.text}")
                    
    def get_available_voices(self) -> Dict:
        """Get list of available voices from ElevenLabs"""
        headers = {
            "Accept": "application/json",
            "xi-api-key": self.api_key
        }
        
        url = f"{self.base_url}/voices"
        
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"Error getting voices: {response.text}")


    def get_history(self, voice_id: Optional[str] = None) -> Dict:
        """Get history of generated voiceovers"""
        headers = {
            "Accept": "application/json",
            "xi-api-key": self.api_key
        }
        url = f"{self.base_url}/history?voice_id={voice_id}"
        if voice_id is None:
            url = f"{self.base_url}/history?page_size=20&source=TTS"
        print(f"Requesting history for voice ID: {voice_id}")
        response = requests.get(url, headers=headers)
        print(f"Response status code: {response.status_code}")
        print(f"Response text: {response.text}")
        if response.status_code == 200:
            return response.json()
        else:
            error_msg = response.text
            if response.status_code == 401:
                raise Exception("Invalid ElevenLabs API key")
            elif response.status_code == 404:
                raise Exception(f"Voice ID {voice_id} not found in history")
            else:
                raise Exception(f"Error getting history: {error_msg}")

    def get_history_by_id(self, history_id) -> Dict:
        """Get history of generated voiceovers"""
        headers = {
            "Accept": "application/json",
            "xi-api-key": self.api_key
        }

        url = f"{self.base_url}/history/{history_id}"
        response = requests.get(url, headers=headers)
        print(f"Response status code: {response.status_code}")
        print(f"Response text: {response.text}")
        if response.status_code == 200:
            return response.json()
        else:
            error_msg = response.text
            if response.status_code == 401:
                raise Exception("Invalid ElevenLabs API key")
            else:
                raise Exception(f"Error getting history: {error_msg}")

    
    def get_history_audio(self, history_id: str, output_path: str) -> str:
        """Download audio from a specific history entry"""
        print(f"Downloading audio for history ID: {history_id}")
        headers = {
            "Accept": "audio/mpeg",
            "xi-api-key": self.api_key
        }
        
        url = f"{self.base_url}/history/{history_id}/audio"
        
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            with open(output_path, "wb") as f:
                f.write(response.content)
            return output_path
        else:
            error_msg = response.text
            if response.status_code == 401:
                raise Exception("Invalid ElevenLabs API key")
            elif response.status_code == 404:
                raise Exception(f"History ID {history_id} not found")
            else:
                raise Exception(f"Error downloading history audio: {error_msg}")