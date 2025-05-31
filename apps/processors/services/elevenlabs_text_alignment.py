import json
import os
import tempfile
import requests
import io
from typing import Dict, Any, List, Optional

class ElevenLabsTextAlignment:
    """
    Drop-in replacement for Aeneas using ElevenLabs Forced Alignment API
    Outputs data in the exact same format as Aeneas for compatibility
    """
    
    def __init__(self, api_key: str, base_url: str = "https://api.elevenlabs.io/v1"):
        """
        Initialize the ElevenLabs Aeneas replacement
        
        Args:
            api_key (str): Your ElevenLabs API key
            base_url (str): ElevenLabs API base URL
        """
        self.api_key = api_key
        self.base_url = base_url
        self.headers = {"xi-api-key": api_key}
    
    def preprocess_text(self, text: str) -> str:
        """
        Preprocess text similar to original Aeneas function
        
        Args:
            text (str): Raw text to preprocess
            
        Returns:
            str: Preprocessed text
        """
        # Basic text preprocessing
        # Remove extra whitespace
        text = ' '.join(text.split())
        
        # Ensure text ends with punctuation for better alignment
        if text and text[-1] not in '.!?':
            text += '.'
        
        return text
    
    def _get_audio_duration(self, audio_path: str) -> Optional[float]:
        """
        Get audio duration using FFprobe (if available)
        
        Args:
            audio_path (str): Path to audio file
            
        Returns:
            Optional[float]: Duration in seconds or None if unable to determine
        """
        try:
            import subprocess
            cmd = [
                'ffprobe', '-v', 'quiet', '-print_format', 'json',
                '-show_format', audio_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                duration = float(data.get('format', {}).get('duration', 0))
                return duration if duration > 0 else None
        except Exception:
            pass
        
        return None
    
    def align_text_with_audio(self, 
                             script: str, 
                             audio_path: str, 
                             output_json_path: str) -> str:
        """
        Align script text with audio file using ElevenLabs Forced Alignment API
        Falls back to Aeneas if ElevenLabs fails
        Returns word-level timing information in Aeneas format
        
        Args:
            script (str): Text script to align
            audio_path (str): Path to audio file
            output_json_path (str): Path where to save the alignment JSON
            
        Returns:
            str: Path to the output JSON file (for compatibility)
        """
        try:
            print(f"🔄 Aligning text with audio using ElevenLabs API...")
            
            # Preprocess the script
            processed_script = self.preprocess_text(script)
            
            # Get audio duration for optimization
            duration = self._get_audio_duration(audio_path)
            if duration:
                print(f"📊 Audio duration: {duration:.2f} seconds")
            
            # Try ElevenLabs first
            alignment_data = self._perform_elevenlabs_alignment(audio_path, processed_script)
            
            if alignment_data:
                # ElevenLabs successful - convert to Aeneas format
                aeneas_format = self._convert_to_aeneas_format(alignment_data, processed_script)
                
                # Save to output file
                with open(output_json_path, 'w', encoding='utf-8') as f:
                    json.dump(aeneas_format, f, indent=1, ensure_ascii=False)
                
                print(f"✅ ElevenLabs alignment saved to: {output_json_path}")
                return output_json_path
            else:
                # ElevenLabs failed - fall back to Aeneas
                print("⚠️ ElevenLabs alignment failed, trying Aeneas fallback...")
                return self._create_fallback_alignment(script, audio_path, output_json_path)
            
        except Exception as e:
            print(f"❌ Error in ElevenLabs alignment: {e}")
            # Fall back to Aeneas
            return self._create_fallback_alignment(script, audio_path, output_json_path)
    
    def _perform_elevenlabs_alignment(self, audio_path: str, text: str) -> Optional[List[Dict]]:
        """
        Perform forced alignment using ElevenLabs API
        
        Args:
            audio_path (str): Path to audio file
            text (str): Text to align
            
        Returns:
            Optional[List[Dict]]: List of word timestamps or None if failed
        """
        try:
            url = f"{self.base_url}/forced-alignment"
            
            # Read audio file
            with open(audio_path, "rb") as f:
                audio_bytes = f.read()
            
            # Prepare multipart form data
            files = {
                'file': ('audio.mp3', io.BytesIO(audio_bytes), 'audio/mpeg')
            }
            
            data = {
                'text': text,
                'language': 'en'  # Default to English
            }
            
            headers = {"xi-api-key": self.api_key}
            
            print("🔄 Sending request to ElevenLabs Forced Alignment API...")
            response = requests.post(url, files=files, data=data, headers=headers, timeout=60)
            response.raise_for_status()
            
            result = response.json()
            
            # Extract word-level timestamps
            words = result.get("words", [])
            
            # Process and clean the words
            processed_words = []
            for word_data in words:
                word_text = word_data.get("text", "").strip()
                
                # Skip empty words or just spaces
                if not word_text:
                    continue
                
                processed_words.append({
                    "word": word_text,
                    "start_time_s": word_data.get("start", 0.0),
                    "end_time_s": word_data.get("end", 0.0)
                })
            
            print(f"✅ Received {len(processed_words)} word alignments from ElevenLabs")
            return processed_words
            
        except requests.exceptions.RequestException as e:
            print(f"❌ ElevenLabs API request failed: {e}")
            return None
        except Exception as e:
            print(f"❌ Error in ElevenLabs alignment: {e}")
            return None
    
    def _convert_to_aeneas_format(self, alignment_data: List[Dict], original_text: str) -> Dict[str, Any]:
        """
        Convert ElevenLabs alignment data to Aeneas format
        
        Args:
            alignment_data (List[Dict]): ElevenLabs word timestamps
            original_text (str): Original text for reference
            
        Returns:
            Dict[str, Any]: Data in Aeneas format
        """
        fragments = []
        
        for i, word_data in enumerate(alignment_data):
            # Generate fragment ID in Aeneas format
            fragment_id = f"f{i+1:06d}"  # f000001, f000002, etc.
            
            # Convert time to string format with 3 decimal places
            begin_time = f"{word_data['start_time_s']:.3f}"
            end_time = f"{word_data['end_time_s']:.3f}"
            
            # Create fragment in Aeneas format
            fragment = {
                "begin": begin_time,
                "children": [],
                "end": end_time,
                "id": fragment_id,
                "language": "eng",
                "lines": [word_data["word"]]
            }
            
            fragments.append(fragment)
        
        # Create the full Aeneas-compatible structure
        aeneas_data = {
            "fragments": fragments
        }
        
        return aeneas_data
    
    def _create_fallback_alignment(self, script: str, audio_path: str, output_json_path: str) -> str:
        """
        Create a fallback alignment using Aeneas if ElevenLabs fails
        
        Args:
            script (str): Text script
            audio_path (str): Audio file path
            output_json_path (str): Output JSON path
            
        Returns:
            str: Output path
        """
        try:
            print("⚠️ ElevenLabs failed, falling back to Aeneas...")
            
            # Try to import and use Aeneas
            try:
                from aeneas.executetask import ExecuteTask
                from aeneas.task import Task
                
                # Use the same enhanced Aeneas configuration logic from original
                return self._use_aeneas_alignment(script, audio_path, output_json_path)
                
            except ImportError:
                print("❌ Aeneas not available, using simple estimation...")
                return self._create_simple_estimation_alignment(script, audio_path, output_json_path)
                
        except Exception as e:
            print(f"❌ Error in fallback alignment: {e}")
            # Last resort: simple estimation
            return self._create_simple_estimation_alignment(script, audio_path, output_json_path)
    
    def _use_aeneas_alignment(self, script: str, audio_path: str, output_json_path: str) -> str:
        """
        Use Aeneas for alignment with the same enhanced configuration as original
        
        Args:
            script (str): Text script
            audio_path (str): Audio file path  
            output_json_path (str): Output JSON path
            
        Returns:
            str: Output path
        """
        try:
            from aeneas.executetask import ExecuteTask
            from aeneas.task import Task
            import tempfile
            
            print("🔄 Using Aeneas alignment as fallback...")
            
            # Preprocess the script (same as original)
            processed_script = self.preprocess_text(script)
            
            # Get audio duration to select optimal config (same logic as original)
            duration = self._get_audio_duration(audio_path)
            
            # Create temporary text file for script
            with tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False) as f:
                f.write(processed_script)
                text_file = f.name
            
            try:
                # Choose configuration based on audio length (same as original logic)
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
                
                # Create and execute Aeneas task
                task = Task(config_string=config_string)
                task.audio_file_path_absolute = os.path.abspath(audio_path)
                task.text_file_path_absolute = os.path.abspath(text_file)
                task.sync_map_file_path_absolute = os.path.abspath(output_json_path)

                ExecuteTask(task).execute()
                task.output_sync_map_file()
                
                print(f"✅ Aeneas fallback alignment completed: {output_json_path}")
                return output_json_path
                
            finally:
                # Clean up temporary file
                if os.path.exists(text_file):
                    os.unlink(text_file)
                    
        except Exception as e:
            print(f"❌ Aeneas alignment failed: {e}")
            # Fall back to simple estimation if Aeneas also fails
            return self._create_simple_estimation_alignment(script, audio_path, output_json_path)
    
    def _create_simple_estimation_alignment(self, script: str, audio_path: str, output_json_path: str) -> str:
        """
        Create a simple estimation alignment as last resort
        Uses simple word timing estimation
        
        Args:
            script (str): Text script
            audio_path (str): Audio file path
            output_json_path (str): Output JSON path
            
        Returns:
            str: Output path
        """
        try:
            print("⚠️ Creating simple estimation alignment as last resort...")
            
            # Get audio duration
            duration = self._get_audio_duration(audio_path)
            if not duration:
                duration = 10.0  # Default fallback duration
            
            # Preprocess text
            processed_script = self.preprocess_text(script)
            words = processed_script.split()
            
            # Estimate timing per word
            if len(words) > 0:
                avg_word_duration = duration / len(words)
            else:
                avg_word_duration = 0.5
            
            fragments = []
            current_time = 0.0
            
            for i, word in enumerate(words):
                fragment_id = f"f{i+1:06d}"
                begin_time = current_time
                end_time = current_time + avg_word_duration
                
                fragment = {
                    "begin": f"{begin_time:.3f}",
                    "children": [],
                    "end": f"{end_time:.3f}",
                    "id": fragment_id,
                    "language": "eng",
                    "lines": [word]
                }
                
                fragments.append(fragment)
                current_time = end_time
            
            # Create Aeneas format
            aeneas_data = {"fragments": fragments}
            
            # Save to file
            with open(output_json_path, 'w', encoding='utf-8') as f:
                json.dump(aeneas_data, f, indent=1, ensure_ascii=False)
            
            print(f"⚠️ Simple estimation alignment saved to: {output_json_path}")
            return output_json_path
            
        except Exception as e:
            print(f"❌ Error creating simple estimation alignment: {e}")
            raise
    
    def test_alignment(self, script: str, audio_path: str) -> None:
        """
        Test the alignment function and display results
        
        Args:
            script (str): Text to align
            audio_path (str): Audio file path
        """
        try:
            print("🧪 TESTING ELEVENLABS ALIGNMENT")
            print("=" * 50)
            print(f"Script: {script[:100]}...")
            print(f"Audio: {audio_path}")
            
            # Create temporary output file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                temp_output = f.name
            
            try:
                # Run alignment
                result_path = self.align_text_with_audio(script, audio_path, temp_output)
                
                # Display results
                if os.path.exists(result_path):
                    with open(result_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    fragments = data.get("fragments", [])
                    print(f"\n✅ Alignment successful! Found {len(fragments)} word fragments")
                    
                    # Show first few fragments
                    print("\nFirst 10 word alignments:")
                    for i, fragment in enumerate(fragments[:10]):
                        word = fragment["lines"][0] if fragment["lines"] else ""
                        begin = fragment["begin"]
                        end = fragment["end"]
                        print(f"  {i+1:2d}. '{word}': {begin}s - {end}s")
                    
                    if len(fragments) > 10:
                        print(f"  ... and {len(fragments) - 10} more")
                
            finally:
                # Clean up temp file
                if os.path.exists(temp_output):
                    os.unlink(temp_output)
                    
        except Exception as e:
            print(f"❌ Test failed: {e}")

