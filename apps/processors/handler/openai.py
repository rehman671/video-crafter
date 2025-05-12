import os
import json
import urllib.parse
from typing import List, Dict, Any, Tuple
from openai import OpenAI


class OpenAIHandler:
    """
    Handler class for OpenAI API interactions.
    Provides methods to generate video scene suggestions based on input prompts.
    """
    
    def __init__(self, api_key=None):
        """
        Initialize the OpenAI handler with API key.
        
        Args:
            api_key (str, optional): OpenAI API key. If not provided, will try to get from environment.
        """
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
            
        if not self.api_key:
            raise ValueError("OpenAI API key is required. Provide it directly or set OPENAI_API_KEY environment variable.")
            
        self.client = OpenAI(api_key=self.api_key)

    def generate_scene_suggestions(self, words: str) -> Dict[str, Any]:
        """
        Generate video scene suggestions based on input words.
        
        Args:
            words (str): The words to generate scene suggestions for.
            
        Returns:
            Dict: Contains scene suggestions and search URLs.
        """
        try:
            # Create a chat completion using the new OpenAI client format
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a professional video producer who specializes in creating compelling video advertisements."},
                    {"role": "user", "content": self._build_prompt(words)}
                ],
                temperature=0.7,
                max_tokens=1000
            )
            
            # Extract suggestions from the response
            response_content = response.choices[0].message.content
            scene_suggestions = self._parse_scene_suggestions(response_content)
            
            # Generate search URLs for each suggestion
            for suggestion in scene_suggestions["suggestions"]:
                search_term = suggestion["search_term"]
                encoded_term = urllib.parse.quote(search_term)
                
                suggestion["pexels_url"] = f"https://www.pexels.com/search/videos/{encoded_term}/"
                suggestion["storyblocks_url"] = f"https://www.storyblocks.com/all-video/search/{encoded_term}?search-origin=search_bar"
            
            return scene_suggestions
            
        except Exception as e:
            return {
                "error": str(e),
                "status": "failed",
                "suggestions": []
            }
    
    def _build_prompt(self, words: str) -> str:
        """
        Build the prompt for OpenAI.
        
        Args:
            words (str): The words to build the prompt for.
            
        Returns:
            str: The complete prompt.
        """
        return f"""
I want you to think like a top movie producer and think of the best video scene that will fit the following words. It will go on a video advert that will be posted on Facebook:

"{words}"

Please provide 3 straight-to-the-point video scene suggestions in 3 bullet points.

Then, think about what I can search for each bullet point on Pexels and Storyblocks. Provide a clear search term for each scene.

Format your response like this:
1. [Scene description]
   Search term: [term]

2. [Scene description]
   Search term: [term]

3. [Scene description]
   Search term: [term]
"""

    def _parse_scene_suggestions(self, content: str) -> Dict[str, Any]:
        """
        Parse the scene suggestions from the OpenAI response.
        
        Args:
            content (str): The raw response content.
            
        Returns:
            Dict: Structured scene suggestions.
        """
        lines = content.strip().split('\n')
        suggestions = []
        
        current_suggestion = None
        for line in lines:
            line = line.strip()
            
            # Check for new suggestion (starts with number and period)
            if line and line[0].isdigit() and line[1:].startswith('. '):
                if current_suggestion:
                    suggestions.append(current_suggestion)
                
                current_suggestion = {
                    "description": line[2:].strip(),
                    "search_term": ""
                }
            
            # Check for search term
            elif line.lower().startswith('search term:') and current_suggestion:
                current_suggestion["search_term"] = line[12:].strip()
        
        # Add the last suggestion if it exists
        if current_suggestion:
            suggestions.append(current_suggestion)
        
        return {
            "status": "success",
            "count": len(suggestions),
            "suggestions": suggestions
        }