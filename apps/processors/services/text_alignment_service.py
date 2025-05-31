import os
import json
import tempfile
import subprocess
from typing import List, Dict, Any, Optional
import aeneas
from aeneas.executetask import ExecuteTask
from aeneas.task import Task
from aeneas.textfile import TextFileFormat

class TextAudioAligner:
    def __init__(self):
        # Check if aeneas is installed
        try:
            self.use_direct_api = True
            self._debug = False  # Internal debug flag
        except ImportError:
            self.use_direct_api = False
            raise ImportError("Aeneas is not installed. Install it with: pip install aeneas")
            
    def preprocess_text(self, script: str) -> str:
        """
        Preprocess text to make it more suitable for alignment
        - Enhanced to better handle longer texts while maintaining original structure
        """
        # First, normalize line breaks
        script = script.replace('\r\n', '\n').replace('\r', '\n')
        
        # Split into paragraphs or lines
        lines = script.strip().split('\n')
        
        if len(lines) <= 1:
            # For single line text, ensure words are properly separated
            return ' '.join(word for word in script.split() if word)
        else:
            # For multi-line text, preserve structure but clean each line
            # This is better for longer texts with natural breaks
            cleaned_lines = []
            for line in lines:
                if not line.strip():
                    continue
                # Normalize spaces within each line
                cleaned_line = ' '.join(word for word in line.split() if word)
                cleaned_lines.append(cleaned_line)
            
            # Join with newlines to maintain structure
            return '\n'.join(cleaned_lines)
            
    def align_text_with_audio(self, 
                             script: str, 
                             audio_path: str, 
                             output_json_path: str) -> Dict[str, Any]:
        """
        Align script text with audio file using Aeneas
        Returns word-level timing information
        
        - Enhanced to handle longer audio files better
        - Same interface as original for compatibility
        """
        # Preprocess the script
        processed_script = self.preprocess_text(script)
        
        # Get audio duration if possible (to select optimal config)
        duration = self._get_audio_duration(audio_path)
        
        # Create temporary text file for script
        with tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False) as f:
            f.write(processed_script)
            text_file = f.name
            
        try:
            # Choose configuration based on audio length
            if duration and duration > 30.0:
                # Enhanced configuration for longer audio (>30 seconds)
                config_string = (
                    "task_language=eng|"
                    "is_text_type=plain|"
                    "os_task_file_format=json|"
                    "is_text_file_format=plain|"
                    # Use rate algorithm for longer content
                    "task_adjust_boundary_algorithm=rate|"
                    "task_adjust_boundary_rate_value=22.000|"
                    # Less aggressive boundary settings for longer content
                    "task_adjust_boundary_nonspeech_min=0.150|"
                    "task_adjust_boundary_nonspeech_string=REMOVE|"
                    # Better head/tail detection for longer audio
                    "is_audio_file_detect_head_max=0.750|"
                    "is_audio_file_detect_head_min=0.150|"
                    "is_audio_file_detect_tail_max=0.750|"
                    "is_audio_file_detect_tail_min=0.150|"
                    # Additional optimizations
                    "task_max_audio_length=0|"
                    "os_task_file_head_tail_format=true|"
                    "task_adjust_boundary_no_zero=true|"
                    "is_audio_file_detect_head=true|"
                    "is_audio_file_detect_tail=true|"
                    # Break text into smaller chunks for better alignment
                    "task_max_text_chunk_length=12.000|"
                    # Word level mapping
                    "is_text_mapping=word"
                )
            else:
                # Original configuration works well for shorter audio
                config_string = (
                    "task_language=eng|"
                    "is_text_type=plain|"
                    "os_task_file_format=json|"
                    "is_text_file_format=plain|"
                    # Set word-level granularity for more precise alignment
                    "is_text_unparsed_id_sort=true|"
                    "is_text_unparsed_id_regex=\\w+|"
                    # Adjust boundary parameters for more precise detection
                    "task_adjust_boundary_algorithm=percent|"  # use percent algorithm
                    "task_adjust_boundary_percent_value=50|"   # center point
                    "task_adjust_boundary_nonspeech_min=0.100|"
                    "task_adjust_boundary_nonspeech_string=REMOVE|"
                    # Better head/tail detection
                    "is_audio_file_detect_head_max=1.000|"
                    "is_audio_file_detect_head_min=0.100|"
                    "is_audio_file_detect_tail_max=1.000|"
                    "is_audio_file_detect_tail_min=0.100|"
                    # Additional optimizations
                    "task_max_audio_length=0|"
                    "os_task_file_head_tail_format=true|"
                    "task_adjust_boundary_no_zero=true|"
                    "is_audio_file_detect_head=true|"
                    "is_audio_file_detect_tail=true|"
                    "task_adjust_boundary_rate_value=12.000|"
                    # Word level mapping
                    "is_text_mapping=word"
                    
                )
            
            task = Task(config_string=config_string)
            task.audio_file_path_absolute = os.path.abspath(audio_path)
            task.text_file_path_absolute = os.path.abspath(text_file)
            task.sync_map_file_path_absolute = os.path.abspath(output_json_path)

            ExecuteTask(task).execute()
            task.output_sync_map_file()
            
            return output_json_path
            
        finally:
            # Clean up temporary file
            os.unlink(text_file)
    
    def _get_audio_duration(self, audio_path: str) -> Optional[float]:
        """Get the duration of an audio file using aeneas"""
        try:
            from aeneas.tools.execute_task import AudioFileProfiler
            profiler = AudioFileProfiler()
            info = profiler.profile(audio_path)
            return info["duration"]
        except Exception:
            return None
            
    def _extract_word_timings(self, aeneas_json_path: str, original_script: str) -> Dict[str, Any]:
        """Extract word-level timings from Aeneas output with improved accuracy"""
        # Load Aeneas JSON output
        with open(aeneas_json_path, 'r') as f:
            aeneas_data = json.load(f)
            
        # Extract fragment-level timings
        fragments = aeneas_data.get('fragments', [])
        
        # Check if we have word-level information already (will be present with the improved config)
        if len(fragments) > 0 and len(fragments[0].get('children', [])) > 0:
            # We have word-level data directly from aeneas
            words = []
            word_index = 0
            
            for fragment in fragments:
                for child in fragment.get('children', []):
                    word = child.get('text', '').strip()
                    if not word:
                        continue
                        
                    words.append({
                        'word': word,
                        'start': float(child.get('begin', 0)),
                        'end': float(child.get('end', 0)),
                        'index': word_index
                    })
                    word_index += 1
            
        else:
            # Improved fallback method for creating word timing
            words = []
            word_index = 0
            
            for fragment in fragments:
                text = fragment.get('text', '')
                begin = float(fragment.get('begin', 0))
                end = float(fragment.get('end', 0))
                
                # Split fragment into words
                fragment_words = [w for w in text.split() if w]
                if not fragment_words:
                    continue
                    
                # Improved timing distribution based on word lengths
                # Allocate some time for natural pauses between words
                total_chars = sum(len(w) for w in fragment_words)
                fragment_duration = end - begin
                
                # Calculate time for words vs spaces between words
                if len(fragment_words) > 1:
                    # Allocate 85% for words, 15% for spaces between words
                    word_time_portion = 0.85
                    space_time = (fragment_duration * (1 - word_time_portion)) / (len(fragment_words) - 1)
                else:
                    word_time_portion = 1.0
                    space_time = 0
                
                # Time available for actual words
                word_time_available = fragment_duration * word_time_portion
                
                current_time = begin
                for i, word in enumerate(fragment_words):
                    # Calculate word duration proportional to its length
                    word_duration = (len(word) / total_chars) * word_time_available if total_chars > 0 else 0
                    
                    # Ensure minimum word duration (80ms)
                    word_duration = max(word_duration, 0.08)
                    
                    # Make sure we don't exceed fragment end time
                    word_end = min(current_time + word_duration, end)
                    
                    words.append({
                        'word': word,
                        'start': round(current_time, 3),
                        'end': round(word_end, 3),
                        'index': word_index
                    })
                    
                    # Update current time for next word
                    current_time = word_end
                    if i < len(fragment_words) - 1:
                        current_time += space_time
                        
                    word_index += 1
                
        # Save the detailed word timings to a new file
        word_timings_path = os.path.splitext(aeneas_json_path)[0] + "_words.json"
        with open(word_timings_path, 'w') as f:
            json.dump(words, f, indent=2)
            
        return {
            'words': words,
            'word_timings_path': word_timings_path
        }
        
    def align_text_to_audio(self, audio_path: str, text_path: str, output_path: str) -> str:
        """Align each phrase separately with audio - enhanced for longer files"""
        try:
            # Get file content and duration
            with open(text_path, 'r') as f:
                text_content = f.read()
                
            duration = self._get_audio_duration(audio_path)
            
            # Choose configuration based on audio length
            if duration and duration > 30.0:
                # Enhanced configuration for longer audio
                config_string = (
                    "task_language=eng|"
                    "is_text_type=plain|"
                    "os_task_file_format=json|"
                    "is_text_file_format=plain|"
                    # Use rate algorithm for longer content
                    "task_adjust_boundary_algorithm=rate|"
                    "task_adjust_boundary_rate_value=22.000|"
                    # Boundary detection parameters for longer audio
                    "task_adjust_boundary_nonspeech_min=0.150|"
                    "task_adjust_boundary_nonspeech_string=REMOVE|"
                    # More moderate head/tail detection
                    "is_audio_file_detect_head_max=0.700|"
                    "is_audio_file_detect_head_min=0.150|"
                    "is_audio_file_detect_tail_max=0.700|"
                    "is_audio_file_detect_tail_min=0.150|"
                    # Break text into smaller chunks for better alignment
                    "task_max_text_chunk_length=12.000|"
                    # Additional optimizations
                    "task_max_audio_length=0|"
                    "task_adjust_boundary_no_zero=true|"
                    "is_audio_file_detect_head=true|"
                    "is_audio_file_detect_tail=true|"
                    "is_text_mapping=word"  # Force word-level mapping
                )
            else:
                # Original configuration for shorter audio
                config_string = (
                    "task_language=eng|"
                    "is_text_type=plain|"
                    "os_task_file_format=json|"
                    "is_text_file_format=plain|"
                    # Boundary detection parameters
                    "task_adjust_boundary_algorithm=percent|"
                    "task_adjust_boundary_percent_value=50|"
                    # "task_adjust_boundary_nonspeech_min=0.050|"

                    "task_adjust_boundary_nonspeech_string=REMOVE|"
                    # Improved head/tail detection for start time precision
                    # "is_audio_file_detect_head_max=0.500|"
                    # "is_audio_file_detect_head_min=0.050|"
                    # "is_audio_file_detect_tail_max=0.500|"
                    # "is_audio_file_detect_tail_min=0.050|"
                    "is_audio_file_detect_head_max=1.500|"
                    "is_audio_file_detect_head_min=0.300|"
                    "is_audio_file_detect_tail_max=1.500|"
                    "is_audio_file_detect_tail_min=0.300|"
                    # Additional optimizations
                    "task_max_audio_length=0|"
                    "task_adjust_boundary_no_zero=true|"
                    "is_audio_file_detect_head=true|"
                    "is_audio_file_detect_tail=true|"
                    "is_text_mapping=word"  # Force word-level mapping
                )

            task = Task(config_string=config_string)
            task.audio_file_path_absolute = os.path.abspath(audio_path)
            task.text_file_path_absolute = os.path.abspath(text_path)
            task.sync_map_file_path_absolute = os.path.abspath(output_path)

            ExecuteTask(task).execute()
            task.output_sync_map_file()
            print("Successfully aligned text with audio")
            return output_path
        except Exception as e:
            # logger.error(f"Alignment failed: {str(e)}")
            raise
    
    def get_highlighted_word_clips(self, 
                                  word_timings: List[Dict], 
                                  highlighted_words: List[Dict]) -> List[Dict]:
        """
        Match highlighted words/phrases with their timing information
        - Improved matching for multi-word phrases
        
        highlighted_words format: [{'text': 'word or phrase', 'clip_path': 'path/to/clip.mp4'}, ...]
        """
        result = []
        
        for highlight in highlighted_words:
            text = highlight['text'].lower()
            clip_path = highlight['clip_path']
            
            # Split into words for better matching
            highlight_words = text.split()
            
            # For single words
            if len(highlight_words) == 1:
                for i, word_data in enumerate(word_timings):
                    if word_data['word'].lower() == text:
                        result.append({
                            'clip_path': clip_path,
                            'word_data': word_data
                        })
            else:
                # For multi-word phrases - improved matching
                for i in range(len(word_timings) - len(highlight_words) + 1):
                    # Check if this could be the start of our phrase
                    if word_timings[i]['word'].lower() == highlight_words[0]:
                        # Check if subsequent words match
                        match_found = True
                        for j in range(1, len(highlight_words)):
                            if (i+j >= len(word_timings) or 
                                word_timings[i+j]['word'].lower() != highlight_words[j]):
                                match_found = False
                                break
                        
                        if match_found:
                            # We found a phrase match
                            start_time = word_timings[i]['start']
                            end_time = word_timings[i+len(highlight_words)-1]['end']
                            
                            result.append({
                                'clip_path': clip_path,
                                'word_data': {
                                    'word': text,
                                    'start': start_time,
                                    'end': end_time,
                                    'index': word_timings[i]['index']
                                }
                            })
        
        return result