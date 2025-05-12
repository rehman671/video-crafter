import subprocess
import os
from pathlib import Path
import tempfile
import logging
import time
from apps.processors.models import Video, Clips, Subclip, BackgroundMusic
import concurrent.futures
from functools import partial
from django.core.files import File
from django.core.files.storage import default_storage
from django.conf import settings

# Set up logging
logger = logging.getLogger(__name__)


class VideoProcessorService:

    def __init__(self, video: Video, status_callback=None):
        self.video = video
        self.status_callback = status_callback
        # Configuration for clip duration management
        self.min_clip_duration = 3.0  # Minimum clip duration in seconds
        self.max_clip_duration = 15.0  # Maximum clip duration in seconds

        # Font configuration - S3 compatible approach
        self.font_path = None
        if self.video.subtitle_font:
            try:
                # Try to create a local copy of the font file

                
                font_path_rel = self.video.subtitle_font.font_path
                if default_storage.exists(font_path_rel):
                    # Create a temp file for the font
                    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(font_path_rel)[1]) as tmp_font:
                        with default_storage.open(font_path_rel, 'rb') as s3_file:
                            tmp_font.write(s3_file.read())
                        self.font_path = tmp_font.name
                    print(f"Using specified font from storage: {self.video.subtitle_font.name} at {self.font_path}")
                else:
                    self.font_path = self._find_available_font()
                    print(f"Font not found in storage, using fallback font: {self.font_path}")
            except Exception as e:
                print(f"Error loading font: {str(e)}")
                self.font_path = self._find_available_font()
                print(f"Error loading font, using fallback: {self.font_path}")
        else:
            # Fallback to system fonts if no font specified
            self.font_path = self._find_available_font()
            print(f"Using fallback font: {self.font_path}")

        # Font size processing to match with standard document applications
        # Standard conversion: 1pt ≈ 1.333px (96dpi / 72ppi)
        # Apply a scaling factor to make font size match with document apps
        raw_font_size = self.video.font_size if self.video.font_size > 0 else 25
        
        # Reduce the scaling factor to make text smaller and more appropriate
        scaling_factor = 1.2  # Reduced from 2.0 to make font smaller
        self.font_size = int(raw_font_size * scaling_factor)
        
        print(f"Font size set to {self.font_size}px (from {raw_font_size}pt with scaling factor {scaling_factor})")
        
        self.font_size_ratio = 40  # Only used if calculating font size based on video height
        
        # Get font color from video model
        self.font_color = self.video.font_color
        
        # Get subtitle box color and padding from video model
        self.subtitle_box_color = self.video.subtitle_box_color
        self.subtitle_box_padding = 0.4
        
        # Get box roundness from video model
        self.box_roundness = self.video.box_roundness
        
        # Set global framerate for consistency
        self.framerate = 24  # Changed from 30 to 24 FPS for all video processing

        # Maximum words per line for subtitle wrapping
        self.max_words_per_line = 5
    def _find_available_font(self):
        """Find an available font from common locations"""
        # Look for fonts in project folders first
        potential_font_paths = [
            # Project fonts
            os.path.join(settings.BASE_DIR, "fonts", "Arial.ttf"),
            os.path.join(settings.BASE_DIR, "fonts", "Montserrat.ttf"),
            os.path.join(settings.BASE_DIR, "fonts", "Roboto-Medium.ttf"),
            # Common Windows font locations
            "C:/Windows/Fonts/Arial.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/times.ttf",
            # Common Linux font locations
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]

        for path in potential_font_paths:
            if os.path.exists(path):
                return path
        
        # If no font found, return None and rely on ffmpeg's default font
        logger.warning("No font file found, using ffmpeg default font")
        return None

    def _update_progress(self, progress, step=None, error=None):
        """Update processing progress if callback is available"""
        if self.status_callback:
            self.status_callback(self.video.id, progress, step, error)

    def _wrap_text(self, text, max_width=None):
        """
        Smart text wrapping for subtitles to ensure they stay within video boundaries.
        - Keeps current calculation until it exceeds 2 lines
        - If text would create more than 2 lines, restricts to exactly 2 lines
        - First line will always be longer than the second line (around 35 chars)
        - Ensures text fits within screen constraints
        
        Args:
            text: The text to wrap
            max_width: Maximum width in pixels (if known)
        """
        words = text.split()
        total_words = len(words)
        total_chars = len(text)
        
        # Very short text - keep as single line
        if total_words <= 4 or total_chars <= 29:
            return [text]
        if self.video.dimensions == "16:9" and  (total_words <= 10 or total_chars <= 40):
            return [text]
        # Calculate target line lengths based on font size
        font_size = self.video.font_size if self.video.font_size > 0 else 25
        
        # Calculate character limits using linear relationship that gives 30 chars at font size 22
        # Formula: chars = base_chars * (reference_font_size / current_font_size)
        reference_font_size = 22  # Font size reference point that gives 30 characters
        base_chars = 20  # Number of characters at reference font size
        if self.video.dimensions == "16:9":
            base_chars = 40
        # Calculate the scaling factor relative to reference font size
        font_size_factor = reference_font_size / max(font_size, 10)  # Prevent division by very small font sizes
        
        # First line should have more characters than second line
        first_line_max_chars = int(base_chars * font_size_factor * 1.2)  # Make first line 20% longer
        second_line_max_chars = int(base_chars * font_size_factor)
        
        # Ensure reasonable limits regardless of font size
        first_line_max_chars = max(25, min(50, first_line_max_chars))
        second_line_max_chars = max(20, min(40, second_line_max_chars))
        
        # Always ensure first line is longer than potential second line
        if first_line_max_chars <= second_line_max_chars:
            first_line_max_chars = second_line_max_chars + 5
        
        # Process text with current algorithm
        # Initialize variables
        lines = []
        current_line = []
        current_chars = 0
        
        # Process each word
        for word in words:
            # Account for space before word
            space_needed = 1 if current_line else 0
            word_length = len(word)
            
            # Check if adding this word would exceed first line length
            if current_chars + space_needed + word_length > first_line_max_chars and current_line:
                # Complete first line
                lines.append(" ".join(current_line))
                current_line = [word]
                current_chars = word_length
            else:
                # Add word to current line
                if current_line:  # Add space
                    current_chars += 1
                current_line.append(word)
                current_chars += word_length
        
        # Add remaining words
        if current_line:
            lines.append(" ".join(current_line))
        
        # Check if we have more than 2 lines - if so, redistribute to exactly 2 lines
        if len(lines) > 2:
            # For text that would create more than 2 lines, force exactly 2 lines
            # Target first line to have around 35 characters or 60% of total text
            target_first_line_chars = min(35, int(total_chars * 0.6))
            
            # Reconstruct from words to achieve target character count
            first_line = ""
            second_line = ""
            char_count = 0
            
            for i, word in enumerate(words):
                # Add space if not first word
                space = " " if char_count > 0 else ""
                
                # If adding this word would exceed target for first line, start second line
                if char_count + len(space + word) > target_first_line_chars and not second_line:
                    second_line = word
                # Otherwise add to whichever line we're building
                elif not second_line:
                    first_line += space + word
                    char_count += len(space + word)
                else:
                    second_line += " " + word
            
            # If second line is longer than first line, rebalance
            while second_line and len(second_line) > len(first_line):
                # Find last space in second line
                space_idx = second_line.find(" ")
                if space_idx == -1:
                    break  # No space found, can't rebalance
                
                # Move first word from second line to first line
                word_to_move = second_line[:space_idx]
                second_line = second_line[space_idx+1:]  # +1 to remove the space
                first_line += " " + word_to_move
            
            # Return exactly 2 lines
            return [first_line, second_line]
            
        # If second line is longer than first, redistribute to make first line longer
        elif len(lines) == 2 and len(lines[0]) < len(lines[1]):
            words_first = lines[0].split()
            words_second = lines[1].split()
            
            # Keep moving words from second line to first until first is longer
            while len(lines[0]) < len(lines[1]) and len(words_second) > 1:
                words_first.append(words_second.pop(0))
                lines[0] = " ".join(words_first)
                lines[1] = " ".join(words_second)
        
        return lines

    def _process_clip_segment(self, segment_files, clip, subclips):
        """Process a clip and its subclips with exact placement at specified times"""
        temp_dir = tempfile.mkdtemp()
        try:
            # Create a segment file for each clip and subclip
            for j, subclip in enumerate(subclips):
                if subclip.video_file and os.path.exists(subclip.video_file.path):
                    # Extract subclip with exact timing
                    subclip_path = os.path.join(temp_dir, f"subclip_{j}.mp4")
                    
                    # Get exact timing from subclip object
                    subclip_start = subclip.start_time
                    subclip_end = subclip.end_time
                    
                    # Add to segment files with exact timing
                    segment_files.append({
                        "file": subclip_path,
                        "text": subclip.text,
                        "start_time": subclip_start,
                        "end_time": subclip_end,
                        "is_subclip": True
                    })
                    
                    print(f"Added subclip with EXACT timing: {subclip_start} to {subclip_end}")
            
            return segment_files
        except Exception as e:
            print(f"Error processing clip segments: {str(e)}")
            return segment_files


    def generate_video(self, add_watermark=False):
        start_time = time.time()
        print(f"Starting video generation for video {self.video.id}")
        self._update_progress(1, "Checking system capabilities")

        # Check if NVIDIA GPU is available and determine supported presets
        try:
            nvidia_info = subprocess.run(
                ["nvidia-smi"], capture_output=True, check=False, text=True
            )
            use_gpu = nvidia_info.returncode == 0

            if use_gpu:
                # Test if h264_nvenc is available and check supported presets
                preset_test = subprocess.run(
                    ["ffmpeg", "-h", "encoder=h264_nvenc"],
                    capture_output=True,
                    check=False,
                    text=True,
                )

                if "p4" in preset_test.stdout:
                    nvenc_preset = "p4"
                elif "p7" in preset_test.stdout:
                    nvenc_preset = "p7"
                elif "fast" in preset_test.stdout:
                    nvenc_preset = "fast"
                else:
                    nvenc_preset = "default"

                print(
                    f"NVIDIA GPU detected, using hardware acceleration with preset: {nvenc_preset}"
                )
            else:
                print("No NVIDIA GPU detected, using CPU encoding")
        except Exception as e:
            use_gpu = False
            print(f"Error checking GPU, falling back to CPU encoding: {str(e)}")
            self._update_progress(2, "Falling back to CPU encoding")

        clips = Clips.objects.filter(video=self.video).order_by("start_time")

        if not clips.exists():
            error_msg = f"No clips found for video {self.video.id}"
            logger.error(error_msg)
            self._update_progress(0, error=error_msg)
            raise ValueError(error_msg)

        self._update_progress(5, "Determining video dimensions")
        
        # Determine video dimensions based on the video's dimension setting
        dimensions = self.video.dimensions
        if (dimensions == "16:9"):
            width, height = 1920, 1080
        elif (dimensions == "9:16"):
            width, height = 1080, 1920
        elif (dimensions == "1:1"):
            width, height = 1080, 1080
        elif (dimensions == "4:5"):
            width, height = 1080, 1350
        else:
            width, height = 1920, 1080  # Default to 16:9

        # Calculate font size based on video height or use model setting
        if self.video.font_size > 0:
            if self.video.dimensions == "9:16":
                # For vertical video, use a smaller font size
                font_size = 52
            elif self.video.dimensions == "16:9":
                font_size = self.video.font_size * 2
            else:
                font_size = self.video.font_size * 2
        else:
            font_size = int(height / self.font_size_ratio)

        # Calculate safe area for text (positioned in lower third)
        text_y_position = int(height * 0.8)  # Lower third of the screen

        # Create temp directory for intermediate files - make it easy to identify
        temp_dir_suffix = f"videocrafter_temp_{self.video.id}_{int(time.time())}"
        import tempfile
        
        with tempfile.TemporaryDirectory(suffix=temp_dir_suffix) as temp_dir:
            # Create a file listing all segments for ffmpeg concat
            concat_file_path = os.path.join(temp_dir, "concat.txt")
            segment_files = []

            # Track the expected start time of the next clip
            expected_time = 0.0
            process_tasks = []

            clip_start_time = time.time()

            # First, create an exact mapping of where subtitles should appear
            subtitle_timings = []
            
            # Pre-process all clips to ensure exact timing
            clips_list = list(clips)
            
            # Debug log the total number of clips we're processing
            print(f"Total clips to process: {len(clips_list)}")
            
            # Process each clip and its subclips
            for i, clip in enumerate(clips_list):
                print(f"Processing clip {i+1}/{len(clips_list)} - Starting at {expected_time:.3f}s")
                
                # Check if there's a gap before this clip
                if clip.start_time > expected_time:
                    # Create black video for the gap
                    gap_duration = clip.start_time - expected_time
                    black_path = os.path.join(temp_dir, f"black_{i}.mp4")

                    # Generate black video with the correct duration
                    self._create_black_video(
                        black_path,
                        gap_duration,
                        width,
                        height,
                        use_gpu,
                        nvenc_preset if use_gpu else None,
                    )

                    # Add to segment files - ensure precise timing
                    segment_files.append(
                        {
                            "file": black_path,
                            "text": "",
                            "start_time": expected_time,
                            "end_time": clip.start_time,
                            "is_black": True,
                            "clip_index": None,
                        }
                    )

                    print(
                        f"Added black screen for gap: {expected_time:.3f} to {clip.start_time:.3f} (duration: {gap_duration:.3f}s)"
                    )

                # Get all subclips for this clip
                subclips = Subclip.objects.filter(clip=clip).order_by("start_time")
                
                # If no subclips, process the clip normally
                if not subclips.exists():
                    # Generate clip file path
                    clip_path = os.path.join(temp_dir, f"clip_{i}.mp4")

                    # Original clip duration
                    original_duration = clip.end_time - clip.start_time

                    # Apply minimum duration constraint but don't extend beyond original duration
                    if original_duration < self.min_clip_duration:
                        # Use slow-motion effect by applying speed_factor < 1.0
                        target_duration = self.min_clip_duration
                        speed_factor = original_duration / target_duration
                    else:
                        # Keep the original duration as is, no extension
                        target_duration = original_duration
                        speed_factor = 1.0
                        
                    # Set the adjusted end time based on original duration
                    adjusted_end_time = clip.start_time + target_duration

                    # Process the full clip
                    process_tasks.append(
                        (
                            clip,
                            clip_path,
                            i,
                            width,
                            height,
                            use_gpu,
                            nvenc_preset if use_gpu else None,
                            speed_factor,
                            clip.start_time,
                            clip.end_time,
                        )
                    )

                    # Add to segment files
                    segment_files.append(
                        {
                            "file": clip_path,
                            "text": clip.text,
                            "start_time": clip.start_time,
                            "end_time": adjusted_end_time,
                            "speed_factor": speed_factor,
                            "is_black": False,
                            "clip_index": i,
                        }
                    )
                    
                    # Add subtitle timing - main clip
                    subtitle_timings.append({"text": clip.text, "start": clip.start_time, "end": clip.end_time, "is_main_clip": True})
                    
                    # Debug log for the last two clips
                    if i >= len(clips_list) - 2:
                        print(f"Critical clip {i}: start={clip.start_time:.3f}, end={clip.end_time:.3f}")
                        print(f"Critical clip {i} adjusted: start={clip.start_time:.3f}, end={adjusted_end_time:.3f}")
                    
                    expected_time = adjusted_end_time
                
                else:
                    # We have subclips to insert within this clip
                    # Sort subclips by start_time to ensure proper ordering
                    subclips = sorted(subclips, key=lambda sc: sc.start_time if sc.start_time is not None else clip.start_time)
                    
                    # Track the current position within the clip
                    current_pos = clip.start_time

                    # Add the main clip's subtitle timing for the entire clip duration
                    # This ensures we only show the main clip's text during the entire sequence
                    if clip.text:
                        # Check for identical timestamps between clip and subclips
                        has_matching_timestamps = any(sc.start_time == clip.start_time for sc in subclips if sc.start_time is not None)
                        
                        # If there's a timestamp match, add a small offset to prevent conflicts
                        subtitle_start = clip.start_time
                        if has_matching_timestamps:
                            print(f"Found matching timestamps for clip {i} and its subclips - adjusting subtitle timing")
                            # Create a small offset for subtitle timing to ensure proper display
                            subtitle_start = clip.start_time + 0.01
                        
                        subtitle_timings.append(
                            {"text": clip.text, "start": subtitle_start, "end": clip.end_time, "is_main_clip": True}
                        )
                    
                    # Process each subclip and the clip segments before/between/after them
                    for j, subclip in enumerate(subclips):
                        # Determine subclip timing
                        subclip_start = subclip.start_time if subclip.start_time is not None else current_pos
                        subclip_end = subclip.end_time if subclip.end_time is not None else (
                            subclip_start + min(3.0, (clip.end_time - subclip_start) / 2)  # Default 3 seconds or half remaining
                        )
                        
                        # Ensure subclip is within the clip boundaries
                        subclip_start = max(clip.start_time, min(clip.end_time, subclip_start))
                        subclip_end = max(subclip_start, min(clip.end_time, subclip_end))
                        
                        # When subclip starts at the same time as the main clip, ensure proper subtitle handling
                        if subclip_start == clip.start_time and subclip.text:
                            # Log for debugging
                            print(f"Subclip {j} starts at same time as clip {i} - ensuring proper subtitle display")
                            
                            # Add the subclip text with a slight delay to ensure it doesn't conflict
                            subtitle_timings.append({
                                "text": subclip.text, 
                                "start": subclip_start + 0.02,  # Small offset to ensure proper sequencing
                                "end": subclip_end,
                                "is_subclip": True
                            })
                        
                        # Process the subclip itself
                        subclip_path = os.path.join(temp_dir, f"clip_{i}_subclip_{j}.mp4")
                        subclip_duration = subclip_end - subclip_start
                        
                        # Apply minimum duration constraints to subclip
                        if subclip_duration < self.min_clip_duration:
                            target_subclip_duration = min(self.min_clip_duration, subclip_duration * 1.5)
                            subclip_speed_factor = subclip_duration / target_subclip_duration
                            adjusted_subclip_end = subclip_start + target_subclip_duration
                        else:
                            target_subclip_duration = min(subclip_duration, self.max_clip_duration)
                            subclip_speed_factor = 1.0
                            adjusted_subclip_end = subclip_start + target_subclip_duration
                        
                        process_tasks.append(
                            (
                                subclip,
                                subclip_path,
                                f"{i}_subclip_{j}",
                                width,
                                height,
                                use_gpu,
                                nvenc_preset if use_gpu else None,
                                subclip_speed_factor,
                                subclip_start,
                                subclip_end,
                            )
                        )
                        
                        segment_files.append(
                            {
                                "file": subclip_path,
                                "text": subclip.text,
                                "start_time": subclip_start,
                                "end_time": adjusted_subclip_end,
                                "speed_factor": subclip_speed_factor,
                                "is_black": False,
                                "clip_index": f"{i}_subclip_{j}",
                                "is_subclip": True,
                            }
                        )
                        
                        print(f"Added subclip within clip {i}: {subclip_start:.3f} to {subclip_end:.3f}")
                        
                        # Update current position to the end of the subclip
                        current_pos = subclip_end
                    
                    # If there's a portion of the main clip after the last subclip, process it
                    if current_pos < clip.end_time:
                        final_segment_path = os.path.join(temp_dir, f"clip_{i}_final_segment.mp4")
                        final_segment_duration = clip.end_time - current_pos
                        
                        process_tasks.append(
                            (
                                {
                                    "type": "segment",
                                    "clip": clip,
                                    "start_offset": current_pos - clip.start_time,  # Offset from clip start
                                    "duration": final_segment_duration,
                                    "text": clip.text
                                },
                                final_segment_path,
                                f"{i}_final_segment",
                                width,
                                height,
                                use_gpu,
                                nvenc_preset if use_gpu else None,
                                1.0,  # No speed adjustment
                                current_pos,
                                clip.end_time,
                            )
                        )
                        
                        # Apply duration constraints
                        if final_segment_duration < self.min_clip_duration:
                            # Reduce min duration for final segments to avoid timing mismatches
                            # This prevents excessive stretching that can cause subclip desync
                            target_duration = min(self.min_clip_duration, final_segment_duration * 1.2)
                            speed_factor = final_segment_duration / target_duration
                            # Ensure adjusted time doesn't exceed clip end to maintain sync
                            adjusted_end_time = min(current_pos + target_duration, clip.end_time)
                        else:
                            # Use exact duration for longer segments to maintain synchronization
                            target_duration = final_segment_duration
                            adjusted_end_time = clip.end_time
                            speed_factor = 1.0
                        
                        segment_files.append(
                            {
                                "file": final_segment_path,
                                "text": clip.text,
                                "start_time": current_pos,
                                "end_time": adjusted_end_time,
                                "speed_factor": speed_factor,
                                "is_black": False,
                                "clip_index": f"{i}_final_segment",
                                "is_segment": True,
                            }
                        )
                        
                        print(f"Added final clip segment: {current_pos:.3f} to {clip.end_time:.3f}")
                        
                        expected_time = adjusted_end_time
                    else:
                        expected_time = current_pos
                
                # Debug at the end of subclip processing for the last two clips
                if i >= len(clips_list) - 2:
                    print(f"Critical clip {i} with subclips, final expected_time: {expected_time:.3f}")
                    # Debug subtitle information for the last clips
                    print(f"Critical clip {i} text: \"{clip.text}\"")
                    if any(subtitle_timings):
                        for st in subtitle_timings[-2:]:
                            print(f"Subtitle entry: start={st['start']:.3f}, end={st['end']:.3f}, text=\"{st['text']}\"")
            
            # Sort segment files by start_time to ensure proper sequence
            segment_files.sort(key=lambda x: x["start_time"])
            
            # Update subtitle timings to match sorted segment files for accurate text display
            subtitle_timings.sort(key=lambda x: x["start"])
            
            # Ensure no overlapping subtitles - prioritize main clips over subclips
            adjusted_subtitle_timings = []
            for i, st in enumerate(subtitle_timings):
                # Check for overlaps with previous subtitle
                if i > 0 and st["start"] < adjusted_subtitle_timings[-1]["end"]:
                    prev_subtitle = adjusted_subtitle_timings[-1]
                    
                    # If current is main clip and previous is subclip, prioritize main clip
                    if st.get("is_main_clip", False) and prev_subtitle.get("is_subclip", False):
                        # Truncate the previous subclip subtitle
                        prev_subtitle["end"] = st["start"] - 0.01
                        print(f"Adjusted subclip subtitle to end at {prev_subtitle['end']:.3f} to avoid overlap with main clip")
                        adjusted_subtitle_timings.append(st)
                    # If current is subclip and previous is main clip, prioritize main clip
                    elif st.get("is_subclip", False) and prev_subtitle.get("is_main_clip", False):
                        # Adjust start time of current subclip subtitle to prevent overlap
                        st["start"] = prev_subtitle["end"] + 0.01
                        print(f"Adjusted subclip subtitle to start at {st['start']:.3f} to avoid overlap with main clip")
                        # Only add if the adjusted timing still makes sense
                        if st["start"] < st["end"]:
                            adjusted_subtitle_timings.append(st)
                        else:
                            print(f"Skipping subclip subtitle due to timing conflict")
                    else:
                        # Default overlap handling - use the later subtitle
                        adjusted_subtitle_timings.append(st)
                else:
                    # No overlap, add normally
                    adjusted_subtitle_timings.append(st)
            
            # Replace original subtitle timings with adjusted ones
            subtitle_timings = adjusted_subtitle_timings
            print(f"Using {len(subtitle_timings)} adjusted subtitles for accurate timing")
            
            # Ensure no text is being cut off by checking all subtitle entries
            for i, segment in enumerate(segment_files):
                if segment.get("text") and not any(st.get("text") == segment["text"] for st in subtitle_timings):
                    # Add missing subtitle
                    subtitle_timings.append({
                        "text": segment["text"],
                        "start": segment["start_time"],
                        "end": segment["end_time"],
                        "is_main_clip": True
                    })
                    print(f"Added missing subtitle for segment {i}: \"{segment['text']}\"")
            
            print(f"Created sequence with {len(segment_files)} segments and {len(subtitle_timings)} subtitle entries")
            
            # Simplify subtitle timing - use exact clip and subclip times without offsets
            updated_subtitles = []
            
            # Add main clip subtitles with exact timing from clip objects
            for clip in clips_list:
                if clip.text:
                    updated_subtitles.append({
                        "text": clip.text,
                        "start": clip.start_time,
                        "end": clip.end_time,
                        "is_main_clip": True
                    })
                    print(f"Added main clip subtitle at exact time: {clip.start_time:.3f} to {clip.end_time:.3f}")
                    
                # We no longer add subclip subtitles at all
                # This ensures only main clip text is shown
            
            # Replace with our updated subtitles with exact timing
            subtitle_timings = updated_subtitles
            print(f"Using {len(subtitle_timings)} subtitles with exact timing from clip objects only (subclip text removed)")

            # If we have an audio file, get its EXACT duration
            precise_audio_duration = 0
            if self.video.audio_file:
                try:
                    # Download audio file to temporary location for processing

                    
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_audio:
                        # Download the audio file
                        with default_storage.open(self.video.audio_file.name, 'rb') as s3_file:
                            temp_audio.write(s3_file.read())
                        audio_temp_path = temp_audio.name
                    # Get PRECISE audio duration using ffprobe
                    probe_cmd = [
                        "ffprobe",
                        "-v",
                        "error",
                        "-show_entries",
                        "format=duration",
                        "-of",
                        "default=noprint_wrappers=1:nokey=1",
                       audio_temp_path ,
                    ]
                    precise_audio_duration = float(
                        subprocess.check_output(probe_cmd).decode("utf-8").strip()
                    )
                    print(
                        f"PRECISE Audio duration: {precise_audio_duration:.6f}s, Current video end: {expected_time:.6f}s"
                    )

                    # EXACTLY match total duration to audio duration
                    if (
                        abs(precise_audio_duration - expected_time) > 0.01
                    ):  # More than 10ms difference
                        if precise_audio_duration > expected_time:
                            # Add black screen if audio is longer
                            final_gap_duration = precise_audio_duration - expected_time
                            final_black_path = os.path.join(temp_dir, "final_black.mp4")

                            self._create_black_video(
                                final_black_path,
                                final_gap_duration,
                                width,
                                height,
                                use_gpu,
                                nvenc_preset if use_gpu else None,
                            )

                            segment_files.append(
                                {
                                    "file": final_black_path,
                                    "text": "",
                                    "start_time": expected_time,
                                    "end_time": precise_audio_duration,
                                    "is_black": True,
                                }
                            )

                            print(
                                f"Added final black screen for EXACT match: {expected_time:.6f} to {precise_audio_duration:.6f}"
                            )
                        else:
                            # Trim video if audio is shorter
                            print(
                                f"Need to trim video from {expected_time:.6f} to match audio duration {precise_audio_duration:.6f}"
                            )

                        # Set expected_time to EXACT audio duration
                        expected_time = precise_audio_duration
                except Exception as e:
                    logger.error(f"Error determining precise audio duration: {str(e)}")

            # Process clips in parallel
            parallel_start_time = time.time()
            print(
                f"Starting parallel clip processing with strict subtitle alignment (clips prep took {parallel_start_time - clip_start_time:.2f} seconds)"
            )
            self._update_progress(20, "Processing clips in parallel")

            with concurrent.futures.ThreadPoolExecutor(
                max_workers=min(os.cpu_count(), 4)
            ) as executor:
                process_clip_fn = partial(
                    self._process_clip,
                    width=width,
                    height=height,
                    use_gpu=use_gpu,
                    nvenc_preset=nvenc_preset if use_gpu else None,
                )
                list(
                    executor.map(process_clip_fn, process_tasks)
                )  # Force wait for completion

            parallel_end_time = time.time()
            self._update_progress(50, "Finished parallel processing, preparing for concatenation")

            print(
                f"Finished parallel clip processing in {parallel_end_time - parallel_start_time:.2f} seconds"
            )

            # Create a concat file for ffmpeg with PRECISE timing
            with open(concat_file_path, "w") as f:
                total_duration = 0
                expected_total_duration = 0
                for idx, segment in enumerate(segment_files):
                    segment_duration = segment["end_time"] - segment["start_time"]
                    expected_total_duration += segment_duration
                    
                    # Debug the last few segments being written to the concat file
                    if idx >= len(segment_files) - 3:
                        print(f"DEBUG: Writing to concat file [{idx}]: {os.path.basename(segment['file'])}, duration={segment_duration:.3f}s")
                    
                    # Include ALL segments regardless of current total duration
                    # This ensures we capture all content, and will fix duration later
                    f.write(f"file '{segment['file']}'\n")
                    total_duration += segment_duration

                print(f"DEBUG: Expected total video duration from all segments: {expected_total_duration:.3f}s")
                if precise_audio_duration > 0:
                    print(f"DEBUG: Audio duration: {precise_audio_duration:.3f}s, Difference: {abs(expected_total_duration - precise_audio_duration):.3f}s")

            # Concatenate all segments
            concat_start_time = time.time()
            print("Starting clip concatenation with EXACT timing")
            self._update_progress(60, "Concatenating video segments")
            
            intermediate_output = os.path.join(temp_dir, "intermediate.mp4")

            # Run concatenation with improved output validation
            concat_cmd = [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                concat_file_path,
                "-c:v",
                "copy",
                "-r",
                str(self.framerate),  # Force consistent framerate output
                intermediate_output,
            ]
            
            print(f"DEBUG: Running concat command: {' '.join(concat_cmd)}")
            subprocess.run(concat_cmd, check=True)

            # Verify intermediate output duration
            try:
                probe_cmd = [
                    "ffprobe",
                    "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    intermediate_output
                ]
                intermediate_duration = float(subprocess.check_output(probe_cmd).decode("utf-8").strip())
                print(f"CRITICAL: Concatenated video duration: {intermediate_duration:.3f}s vs expected {expected_total_duration:.3f}s")
                
                # Alert if we lost significant content
                if intermediate_duration < expected_total_duration - 0.5:  # If missing more than 0.5 seconds
                    print(f"WARNING: Concat output duration {intermediate_duration:.3f}s is shorter than expected {expected_total_duration:.3f}s")
            except Exception as e:
                print(f"WARNING: Could not verify concatenated video duration: {str(e)}")

            concat_end_time = time.time()
            self._update_progress(70, "Adding subtitles and audio")
            
            print(f"Finished clip concatenation in {concat_end_time - concat_start_time:.2f} seconds")

            # Initialize PNG overlays list
            self._png_overlays = []

            # Add text overlays to the final video - ensure strict subtitle alignment
            final_output_path = os.path.join(temp_dir, "final_output.mp4")
            temp_output_path = os.path.join(temp_dir, "temp_output.mp4")
            filter_complex = []

            # Start with the base video
            filter_complex.append("[0:v]")

            # Calculate maximum text width as percentage of video width (80% of width to leave margins)
            max_text_width = int(width * 0.8)

            # Determine if we're working with vertical video (9:16 aspect ratio)
            is_vertical_video = self.video.dimensions == "9:16"
            
            # Adjust text position based on aspect ratio
            if is_vertical_video:
                # For vertical videos (9:16), position text lower
                text_y_position = int(height * 0.78)  # Position at 75% of height
            else:
                # For horizontal videos, keep existing lower third positioning
                text_y_position = int(height * 0.85)  # Lower third of the screen

            for i, subtitle in enumerate(subtitle_timings):
                if subtitle["text"]:  # Only add text if it exists
                    has_text = True
                    # Use EXACT subtitle timestamps
                    start_time_sec = subtitle["start"]
                    end_time_sec = subtitle["end"]

                    # Calculate approx max width in pixels based on video width
                    max_subtitle_width = int(width * (0.85 if is_vertical_video else 0.8))
                    
                    # Use the improved text wrapping function with width constraints
                    text_lines = self._wrap_text(subtitle["text"], max_subtitle_width)
                    
                    # Calculate vertical spacing between lines (1.2x font size)
                    line_spacing = int(font_size * 1.2)
                    # Calculate number of lines
                    num_lines = len(text_lines)

                    # Adjust starting y-position based on aspect ratio and number of lines
                    if is_vertical_video:
                        # For vertical videos, adjust position to be more visible and higher up
                        start_y = text_y_position - (line_spacing * num_lines) + 60  # Added offset to move it up
                    else:
                        # For horizontal videos, use standard positioning logic
                        if num_lines > 3:
                            start_y = text_y_position - (line_spacing * (num_lines - 2))
                        else:
                            start_y = text_y_position - (line_spacing * (num_lines - 1) // 2)
                    
                    # Calculate proper box padding based on font size and video dimensions
                    padding_factor = self.subtitle_box_padding
                    # For vertical videos, use larger horizontal padding
                    horizontal_padding = font_size * (padding_factor * 0.3 if is_vertical_video else padding_factor * 0.7)  # Reduced horizontal padding
                    vertical_padding = font_size * padding_factor
                    
                    # Check if we're working with vertical video to determine box creation approach
                    if is_vertical_video:
                        # For vertical videos, create individual boxes for each line
                        for line_idx, line_text in enumerate(text_lines):
                            if not line_text.strip():
                                continue  # Skip empty lines
                                
                            # Calculate y position for this specific line
                            line_y = start_y + (line_idx * line_spacing) - (vertical_padding * 0.2)  # Adjusted for vertical padding
                            
                            # Calculate individual box dimensions for this line
                            avg_char_width = font_size * 0.54
                            line_text_width = len(line_text) * avg_char_width
                            line_box_width = int(line_text_width + (horizontal_padding*1.3))
                            line_box_height = int(line_spacing + (vertical_padding * 0.9))
                            
                            # Ensure minimum width for short texts
                            min_width = int(width * 0.15)
                            line_box_width = max(line_box_width, min_width)
                            
                            # Cap maximum width
                            max_width = int(width * 0.9)
                            line_box_width = min(line_box_width, max_width)
                            
                            # Calculate box position for this line (centered)
                            line_box_x = int((width - line_box_width) / 2)
                            line_box_y = line_y - (vertical_padding * 0.8)  # Position box slightly above text
                            
                            # If we have a box_roundness value, create a rounded box as PNG
                            if self.box_roundness > 0:
                                # Use larger radius for vertical videos (more rounded corners)
                                radius_percentage = min(15 * 1.2, 100) / 100
                                radius = int(min(line_box_width, line_box_height) * radius_percentage)
                                
                                # Create a temp PNG file for this line's rounded box
                                rounded_box_path = os.path.join(temp_dir, f"rounded_box_{i}_line_{line_idx}.png")
                                
                                try:
                                    from PIL import Image, ImageDraw
                                    
                                    # Create a new RGBA image with transparent background
                                    img = Image.new('RGBA', (int(line_box_width), int(line_box_height)), (0, 0, 0, 0))
                                    draw = ImageDraw.Draw(img)
                                    
                                    # Convert hex color to RGBA
                                    color = self.subtitle_box_color
                                    if color.startswith('#'):
                                        color = color[1:]
                                    r = int(color[0:2], 16)
                                    g = int(color[2:4], 16)
                                    b = int(color[4:6], 16)
                                    a = 255  # Fully opaque
                                    
                                    # Ensure radius is not too large - max 50% of smaller dimension
                                    radius = min(radius, min(line_box_width, line_box_height) // 2)
                                    
                                    # Draw rounded rectangle with anti-aliasing
                                    draw.rounded_rectangle(
                                        [(0, 0), (int(line_box_width) - 1, int(line_box_height) - 1)],
                                        radius=int(radius),
                                        fill=(r, g, b, a)
                                    )
                                    
                                    # Save the image with maximum quality
                                    img.save(rounded_box_path, 'PNG')
                                    
                                    # Verify the PNG was created successfully
                                    if os.path.exists(rounded_box_path) and os.path.getsize(rounded_box_path) > 0:
                                        # Store the overlay info for later use in the FFmpeg command
                                        if not hasattr(self, '_png_overlays'):
                                            self._png_overlays = []
                                        
                                        self._png_overlays.append({
                                            'path': rounded_box_path,
                                            'x': line_box_x,
                                            'y': line_box_y,
                                            'start': start_time_sec,
                                            'end': end_time_sec,
                                            'input_idx': i + 1
                                        })
                                        
                                        print(f"Created rounded box for line {line_idx} with radius {radius}px")
                                    else:
                                        raise Exception(f"Failed to create PNG file at {rounded_box_path}")
                                    
                                except Exception as e:
                                    # Fallback to standard box if PIL has any issues
                                    print(f"Error creating rounded box for line {line_idx}, falling back to standard box: {str(e)}")
                                    filter_complex.append(
                                        f"drawbox=x={line_box_x}:y={line_box_y}:"
                                        f"w={line_box_width}:h={line_box_height}:"
                                        f"color={self.subtitle_box_color}@1.0:t=fill:"
                                        f"enable='between(t,{start_time_sec},{end_time_sec})'"
                                    )
                                    filter_complex.append(",")
                            else:
                                # Use standard box if no roundness requested
                                filter_complex.append(
                                    f"drawbox=x={line_box_x}:y={line_box_y}:"
                                    f"w={line_box_width}:h={line_box_height}:"
                                    f"color={self.subtitle_box_color}@1.0:t=fill:"
                                    f"enable='between(t,{start_time_sec},{end_time_sec})'"
                                )
                                filter_complex.append(",")
                    else:
                        # For non-vertical videos, keep the original single box for all lines
                        # Get the longest line for width calculation
                        longest_line = max(text_lines, key=len) if text_lines else ""
                        
                        if num_lines > 0:
                            # Calculate box height based on number of lines and padding
                            box_height = (num_lines * line_spacing) + (vertical_padding * 1.1)
                            
                            # Calculate width with reduced side space
                            avg_char_width = font_size * 0.5  # Reduced from 0.6 to make box narrower
                            if self.video.dimensions == "16:9":
                                avg_char_width = font_size * 0.44
                            estimated_text_width = len(longest_line) * avg_char_width
                            box_width = int(estimated_text_width + (horizontal_padding))  # Reduced multiplier for padding
                            
                            # Ensure minimum width for short texts
                            min_width = int(width * 0.15)  # Reduced from 0.2
                            box_width = max(box_width, min_width)
                            
                            # Cap maximum width
                            max_width = int(width * 0.8)  # Reduced from 0.85
                            box_width = min(box_width, max_width)
                        
                            # Calculate box position for proper centering
                            box_x_fixed = int((width - box_width) / 2)
                            
                            # Calculate y-position for the box
                            box_y = start_y - (vertical_padding - (vertical_padding*0.1))
                            
                            # If we have a box_roundness value, create a rounded box as PNG
                            if self.box_roundness > 0:
                                # Calculate appropriate radius based on aspect ratio
                                radius_percentage = self.box_roundness / 100
                                radius = int(min(box_width, box_height) * radius_percentage)
                                
                                # Create a temp PNG file for the rounded box
                                rounded_box_path = os.path.join(temp_dir, f"rounded_box_{i}.png")
                                
                                # Generate the rounded box image using PIL
                                try:
                                    from PIL import Image, ImageDraw
                                    
                                    # Create a new RGBA image with transparent background
                                    img = Image.new('RGBA', (int(box_width), int(box_height)), (0, 0, 0, 0))
                                    draw = ImageDraw.Draw(img)
                                    
                                    # Convert hex color to RGBA
                                    color = self.subtitle_box_color
                                    if color.startswith('#'):
                                        color = color[1:]
                                    r = int(color[0:2], 16)
                                    g = int(color[2:4], 16)
                                    b = int(color[4:6], 16)
                                    a = 255  # Fully opaque
                                    
                                    # Ensure radius is not too large - max 50% of smaller dimension
                                    radius = min(radius, min(box_width, box_height) // 2)
                                    
                                    # Draw rounded rectangle with anti-aliasing
                                    draw.rounded_rectangle(
                                        [(0, 0), (int(box_width) - 1, int(box_height) - 1)],
                                        radius=int(radius),
                                        fill=(r, g, b, a)
                                    )
                                    
                                    # Save the image with maximum quality
                                    img.save(rounded_box_path, 'PNG')
                                    
                                    # Verify the PNG was created successfully
                                    if os.path.exists(rounded_box_path) and os.path.getsize(rounded_box_path) > 0:
                                        # Store the overlay info for later use in the FFmpeg command
                                        if not hasattr(self, '_png_overlays'):
                                            self._png_overlays = []
                                        
                                        self._png_overlays.append({
                                            'path': rounded_box_path,
                                            'x': box_x_fixed,
                                            'y': box_y,
                                            'start': start_time_sec,
                                            'end': end_time_sec,
                                            'input_idx': i + 1
                                        })
                                        
                                        print(f"Successfully created rounded box {i} with radius {radius}px")
                                    else:
                                        raise Exception(f"Failed to create PNG file at {rounded_box_path}")
                                    
                                except Exception as e:
                                    # Fallback to standard box if PIL has any issues
                                    print(f"Error creating rounded box {i}, falling back to standard box: {str(e)}")
                                    filter_complex.append(
                                        f"drawbox=x={box_x_fixed}:y={box_y}:"
                                        f"w={box_width}:h={box_height}:"
                                        f"color={self.subtitle_box_color}@1.0:t=fill:"
                                        f"enable='between(t,{start_time_sec},{end_time_sec})'"
                                    )
                                    filter_complex.append(",")
                            else:
                                # Use standard box if no roundness requested
                                filter_complex.append(
                                    f"drawbox=x={box_x_fixed}:y={box_y}:"
                                    f"w={box_width}:h={box_height}:"
                                    f"color={self.subtitle_box_color}@1.0:t=fill:"
                                    f"enable='between(t,{start_time_sec},{end_time_sec})'"
                                )
                                filter_complex.append(",")
                    # Now add each line of text WITHOUT individual boxes
                    for line_idx, line_text in enumerate(text_lines):
                        # Calculate y position for this line, with adjustments for vertical video
                        if is_vertical_video:
                            # Slightly tighter line spacing for vertical videos
                            line_y = start_y + (line_idx * (line_spacing * 0.95))
                        else:
                            line_y = start_y + (line_idx * line_spacing)

                        # Prepare text (escape special characters)
                        escaped_text = (
                            line_text.replace("'", "\\'")
                            .replace(":", "\\:")
                            .replace(",", "\\,")
                        )

                        # Add drawtext filter with font size proportional to video dimensions
                        if is_vertical_video:
                            # Slightly larger font for vertical videos for better readability
                            adjusted_font_size = int(font_size * 1.1)
                            font_config = f"fontsize={adjusted_font_size}:fontcolor={self.font_color}"
                        else:
                            font_config = f"fontsize={font_size}:fontcolor={self.font_color}"

                        # Add font file if available
                        if self.font_path and os.path.exists(self.font_path):
                            font_path_escaped = self.font_path.replace(
                                "\\", "\\\\"
                            ).replace(":", "\\:")
                            font_config += f":fontfile='{font_path_escaped}'"
                        
                        # Create drawtext filter for this line WITHOUT box
                        filter_complex.append(
                            f"drawtext=text='{escaped_text}':{font_config}:"
                            f"x=(w-tw)/2:y={line_y}:"  # Center horizontally at calculated y position
                            f"enable='between(t,{start_time_sec},{end_time_sec})'"
                        )

                        # Add comma for next filter
                        filter_complex.append(",")

            # Check if we have rounded box overlays to include
            png_overlay_inputs = []
            if hasattr(self, '_png_overlays') and self._png_overlays:
                print(f"Including {len(self._png_overlays)} rounded box overlays")
                
                # Build overlay filters for rounded boxes
                overlay_filters = []
                current_stream = "[0:v]"  # Start with the base video
                
                # Add PNG overlay inputs
                for i, overlay in enumerate(self._png_overlays):
                    png_overlay_inputs.extend(["-i", overlay['path']])
                    
                    # Create overlay filter
                    next_stream = f"[v{i}]" if i < len(self._png_overlays) - 1 else "[vbase]"
                    overlay_filter = (
                        f"{current_stream}[{i+1}:v]overlay="
                        f"x={overlay['x']}:y={overlay['y']}:"
                        f"enable='between(t,{overlay['start']},{overlay['end']})'"
                    )
                    overlay_filter += next_stream
                    
                    overlay_filters.append(overlay_filter)
                    current_stream = next_stream
                
                # Finalize the filter complex string from filter_complex list
                filter_complex_str = "".join(filter_complex)
                
                # Reconstruct the filter complex with overlays BEFORE text
                # This ensures the text appears on top of the rounded boxes
                if overlay_filters:
                    # Start with overlay filters creating a base with rounded boxes
                    overlay_complex = ",".join(overlay_filters)
                    
                    if has_text and filter_complex != ["null"]:
                        # Modify the text filters to use the [vbase] input from overlay filters
                        # and output to [v] for the final mapping
                        text_filters = filter_complex_str.replace("[0:v]", "[vbase]").replace("null", "[vbase]")
                        
                        # If the text filters don't end with output mapping, add one
                        if not text_filters.endswith("[v]"):
                            text_filters += "[v]"
                            
                        filter_complex_str = overlay_complex + "," + text_filters
                    else:
                        # Only overlay filters, but ensure they output to [v] for mapping
                        if overlay_complex.endswith("[vbase]"):
                            filter_complex_str = overlay_complex.replace("[vbase]", "[v]")
                        else:
                            filter_complex_str = overlay_complex
                
                print(f"Updated filter complex with {len(self._png_overlays)} rounded box overlays")

            # Check if we have any text overlays
            if not has_text:
                # If no text overlays, use a null filter to avoid empty filter error
                filter_complex = ["null"]
            else:
                # Ensure we don't have a trailing comma
                if filter_complex[-1] == ",":
                    filter_complex.pop()

            # Finalize the filter complex
            filter_complex_str = "".join(filter_complex)
            print(
                f"Using filter complex with subtitle-aligned timing and manual text wrapping"
            )

            # Start final video processing
            final_start_time = time.time()
            self._update_progress(80, "Processing final video")
            
            print("Starting final video processing with text overlays and audio")

            # GPU-accelerated encoder for the final video
            video_codec = "h264_nvenc" if use_gpu else "libx264"

            if use_gpu:
                video_options = ["-preset", nvenc_preset]
            else:
                video_options = ["-preset", "medium"]

            # Debug overlay status
            print(f"PNG Overlays available: {hasattr(self, '_png_overlays')} with {len(self._png_overlays) if hasattr(self, '_png_overlays') else 0} items")

            # Check if we have an audio file to include
            if self.video.audio_file:

                
                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_audio:
                    # Download the audio file
                    with default_storage.open(self.video.audio_file.name, 'rb') as s3_file:
                        temp_audio.write(s3_file.read())
                    audio_temp_path = temp_audio.name                # Apply text overlays and add audio
                if hasattr(self, '_png_overlays') and self._png_overlays:
                    # We have PNG overlays to include
                    print(f"Including {len(self._png_overlays)} rounded box overlays in final video")
                    
                    # Build the overlay filter chain
                    overlay_chain = []
                    current_stream = "[0:v]"
                    
                    for i, overlay in enumerate(self._png_overlays):
                        next_stream = f"[v{i}]"
                        overlay_filter = (
                            f"{current_stream}[{i+1}:v]overlay="
                            f"x={overlay['x']}:y={overlay['y']}:"
                            f"enable='between(t,{overlay['start']},{overlay['end']})'"
                        )
                        overlay_filter += next_stream
                        overlay_chain.append(overlay_filter)
                        current_stream = next_stream
                    
                    # Add text filters if needed
                    filter_complex_str = ",".join(overlay_chain)
                    
                    # If we have text filters, append them to the overlay chain
                    if has_text:
                        # Get the text filters without the initial input label and remove any trailing commas
                        text_filters = "".join(filter_complex).replace("[0:v]", current_stream)
                        if text_filters.endswith(","):
                            text_filters = text_filters[:-1]
                        
                        # Combine overlay and text filters
                        filter_complex_str = filter_complex_str + "," + text_filters
                    
                    # Ensure final output is labeled as [v]
                    if not filter_complex_str.endswith("[v]"):
                        filter_complex_str = filter_complex_str + "[v]"
                    
                    # Build the ffmpeg command with all overlay inputs
                    cmd = ["ffmpeg", "-y", "-i", intermediate_output]
                    
                    # Add all PNG overlay inputs
                    for overlay in self._png_overlays:
                        cmd.extend(["-i", overlay['path']])
                    
                    # Add audio and complete command
                    cmd.extend([
                        "-i", audio_temp_path,
                        "-filter_complex", filter_complex_str,
                        "-map", "[v]",
                        "-map", f"{len(self._png_overlays) + 1}:a",  # Audio is after all the overlays
                        "-c:v", video_codec,
                    ])
                    cmd.extend(video_options)
                    cmd.extend([
                        "-c:a", "aac",
                        "-strict", "experimental",
                        "-r", str(self.framerate),
                        final_output_path,
                    ])
                    
                    # Print the command for debugging
                    print(f"FFmpeg command: {' '.join(cmd)}")
                    
                elif has_text:
                    # Only text overlays, no PNG boxes
                    cmd = [
                        "ffmpeg",
                        "-y",
                        "-i", intermediate_output,
                        "-i", audio_temp_path,
                        "-filter_complex", "".join(filter_complex),
                        "-map", "[0:v]" if filter_complex == ["null"] else "[v]",
                        "-map", "1:a",
                        "-c:v", video_codec,
                    ]
                    cmd.extend(video_options)
                    cmd.extend([
                        "-c:a", "aac",
                        "-strict", "experimental",
                        "-r", str(self.framerate),
                        final_output_path,
                    ])
                else:
                    # No text or overlays, just copy video and add audio
                    cmd = [
                        "ffmpeg",
                        "-y",
                        "-i", intermediate_output,
                        "-i", audio_temp_path,
                        "-c:v", video_codec,
                    ]
                    cmd.extend(video_options)
                    cmd.extend([
                        "-c:a", "aac",
                        "-strict", "experimental",
                        "-r", str(self.framerate),
                        final_output_path,
                    ])
                
                try:
                    print(f"Executing FFmpeg command...")
                    subprocess.run(cmd, check=True)
                    print(f"FFmpeg command completed successfully")
                    os.unlink(audio_temp_path)
                except subprocess.CalledProcessError as e:
                    print(f"Error generating final video: {str(e)}")
                    raise Exception(f"Error generating final video: {str(e)}")
                    
            else:
                # No audio, only apply text overlays
                if hasattr(self, '_png_overlays') and self._png_overlays:
                    # We have PNG overlays to include
                    print(f"Including {len(self._png_overlays)} rounded box overlays in final video (no audio)")
                    
                    # Build the overlay filter chain
                    overlay_chain = []
                    current_stream = "[0:v]"
                    
                    for i, overlay in enumerate(self._png_overlays):
                        next_stream = f"[v{i}]"
                        overlay_filter = (
                            f"{current_stream}[{i+1}:v]overlay="
                            f"x={overlay['x']}:y={overlay['y']}:"
                            f"enable='between(t,{overlay['start']},{overlay['end']})'"
                        )
                        overlay_filter += next_stream
                        overlay_chain.append(overlay_filter)
                        current_stream = next_stream
                    
                    # Add text filters if needed
                    filter_complex_str = ",".join(overlay_chain)
                    
                    # If we have text filters, append them to the overlay chain
                    if has_text:
                        # Get the text filters without the initial input label and remove any trailing commas
                        text_filters = "".join(filter_complex).replace("[0:v]", current_stream)
                        if text_filters.endswith(","):
                            text_filters = text_filters[:-1]
                        
                        # Combine overlay and text filters
                        filter_complex_str = filter_complex_str + "," + text_filters
                    
                    # Ensure final output is labeled as [v]
                    if not filter_complex_str.endswith("[v]"):
                        filter_complex_str = filter_complex_str + "[v]"
                    
                    # Build the ffmpeg command with all overlay inputs
                    cmd = ["ffmpeg", "-y", "-i", intermediate_output]
                    
                    # Add all PNG overlay inputs
                    for overlay in self._png_overlays:
                        cmd.extend(["-i", overlay['path']])
                    
                    # Complete command without audio
                    cmd.extend([
                        "-filter_complex", filter_complex_str,
                        "-map", "[v]",
                        "-c:v", video_codec,
                    ])
                    cmd.extend(video_options)
                    cmd.extend([
                        "-pix_fmt", "yuv420p",
                        "-r", str(self.framerate),
                        final_output_path,
                    ])
                    
                elif has_text:
                    # Only text overlays, no boxes
                    cmd = [
                        "ffmpeg",
                        "-y",
                        "-i", intermediate_output,
                        "-filter_complex", "".join(filter_complex),
                        "-map", "[0:v]" if filter_complex == ["null"] else "[v]",
                        "-c:v", video_codec,
                    ]
                    cmd.extend(video_options)
                    cmd.extend([
                        "-pix_fmt", "yuv420p",
                        "-r", str(self.framerate),
                        final_output_path,
                    ])
                else:
                    # No text or overlays, just copy video
                    cmd = [
                        "ffmpeg",
                        "-y",
                        "-i", intermediate_output,
                        "-c:v", video_codec,
                    ]
                    cmd.extend(video_options)
                    cmd.extend([
                        "-pix_fmt", "yuv420p",
                        "-r", str(self.framerate),
                        final_output_path,
                    ])
                
                try:
                    print(f"Executing FFmpeg command...")
                    subprocess.run(cmd, check=True)
                    print(f"FFmpeg command completed successfully")
                except subprocess.CalledProcessError as e:
                    print(f"Error generating final video: {str(e)}")
                    raise Exception(f"Error generating final video: {str(e)}")

            final_end_time = time.time()
            self._update_progress(90, "Saving final video")
            
            print(
                f"Finished final video processing in {final_end_time - final_start_time:.2f} seconds"
            )

            # Save to the model
            save_start_time = time.time()
            
            # Create a copy of the file in a location that won't be deleted when the temp dir is closed
            permanent_output_path = os.path.join(tempfile.gettempdir(), f"video_{self.video.id}_output_{int(time.time())}.mp4")
            with open(final_output_path, "rb") as src, open(permanent_output_path, "wb") as dst:
                dst.write(src.read())

            # Apply watermark if requested
            if add_watermark:
                self._update_progress(95, "Adding watermark")
                watermark_start_time = time.time()
                
                # Create path for watermarked output
                watermarked_output_path = os.path.join(tempfile.gettempdir(), f"video_{self.video.id}_watermarked_{int(time.time())}.mp4")
                
                # Set watermark scale based on video dimensions
                # Use smaller scale for portrait videos, larger for landscape
                if height > width:  # Portrait video
                    self.watermark_scale = 0.15  # 15% of width for portrait videos
                else:  # Landscape or square video
                    self.watermark_scale = 0.25  # 25% of width for landscape videos
                
                # Define watermark path - check standard locations
                self.watermark_path = None
                potential_watermark_paths = [
                    os.path.join(settings.BASE_DIR, "static", "watermark.png"),
                    os.path.join(settings.BASE_DIR, "media", "watermark.png"),
                    os.path.join(settings.BASE_DIR, "assets", "watermark.png"),
                ]
                
                for path in potential_watermark_paths:
                    if os.path.exists(path):
                        self.watermark_path = path
                        break
                
                if self.watermark_path:
                    # Apply watermark to the video
                    watermark_success = self.apply_watermark(
                        permanent_output_path, 
                        watermarked_output_path,
                        use_gpu,
                        nvenc_preset if use_gpu else None
                    )
                    
                    if watermark_success:
                        print(f"Successfully applied watermark, output saved to {watermarked_output_path}")
                        # Replace the output path with the watermarked version
                        permanent_output_path = watermarked_output_path
                    else:
                        print("Failed to apply watermark, using non-watermarked output")
                    
                    watermark_end_time = time.time()
                    print(f"Watermark processing took {watermark_end_time - watermark_start_time:.2f} seconds")
                else:
                    print("Watermark image not found in standard locations, skipping watermark")

            # Save the final output file to the video model using Django's File API
            with open(permanent_output_path, 'rb') as output_file:
                output_filename = f"video_{self.video.id}_output.mp4"
                self.video.output.save(output_filename, File(output_file), save=True)

            save_end_time = time.time()
            self._update_progress(100, "Video generation complete")
            
            print(f"Saved final video in {save_end_time - save_start_time:.2f} seconds")

            # Calculate total processing time
            end_time = time.time()
            total_time = end_time - start_time

            # Log performance statistics
            print(f"Video generation completed in {total_time:.2f} seconds")
            print(f"Performance breakdown:")
            print(
                f"- Clip preparation: {parallel_start_time - clip_start_time:.2f} seconds"
            )
            print(
                f"- Parallel processing: {parallel_end_time - parallel_start_time:.2f} seconds"
            )
            print(f"- Concatenation: {concat_end_time - concat_start_time:.2f} seconds")
            print(
                f"- Final processing: {final_end_time - final_start_time:.2f} seconds"
            )
            print(f"- Saving: {save_end_time - save_start_time:.2f} seconds")
            print(subtitle_timings)

            # Print to console for immediate feedback
            print(
                f"\nVideo #{self.video.id} generation completed in {total_time:.2f} seconds"
            )
            print(f"GPU acceleration: {'Enabled' if use_gpu else 'Disabled'}")
            if use_gpu:
                print(f"Using NVENC preset: {nvenc_preset}")

        return permanent_output_path


    def _process_clip(self, task_data, width, height, use_gpu=False, nvenc_preset=None):
        """Process an individual clip, segment, or subclip to standardized dimensions with blurred background without stretching"""
        # Unpack task data with precise timing information
        (
            clip_data,
            output_path,
            index,
            width,
            height,
            use_gpu,
            nvenc_preset,
            speed_factor,
            start_time,
            end_time,
        ) = task_data

        # Calculate target duration
        target_duration = end_time - start_time
        print(f"Processing clip/subclip {index}: exact timing {start_time:.3f} to {end_time:.3f}, duration={target_duration:.3f}s")

        # Set codec based on GPU availability
        video_codec = "h264_nvenc" if use_gpu else "libx264"
        video_options = ["-preset", nvenc_preset if use_gpu else "medium"]

        try:
            # Determine what type of item we're processing
            if isinstance(clip_data, dict) and clip_data.get("type") == "segment":
                # We're processing a segment of a clip
                main_clip = clip_data["clip"]
                
                # S3-compatible file handling

                
                # Check if there's a valid video file available
                if main_clip.video_file:
                    try:
                        # Create a temporary file for processing
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_file:
                            # Download the file from storage
                            with default_storage.open(main_clip.video_file.name, 'rb') as s3_file:
                                temp_file.write(s3_file.read())
                            temp_file_path = temp_file.name
                        
                        # Build filter for segment extraction and standardization
                        start_offset = clip_data["start_offset"]  # Time from the start of the original clip
                        segment_duration = clip_data["duration"]  # Duration of this segment
                        
                        # Enhanced normalization filters with blurred background approach - IMPROVED VERSION
                        # This version ensures NO stretching of the input video
                        normalize_filters = [
                            # Split the video into two streams
                            f"split=2[original][blurred];",
                            
                            # Scale and blur one stream to fill the frame
                            # Use crop to ensure the blurred background fills the entire frame
                            f"[blurred]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},boxblur=luma_radius=min(h\\,w)/20:luma_power=1[blurred];",
                            
                            # Precisely calculate dimensions for the original to avoid ANY stretching
                            # This uses an iw/ih (input width/height) approach to preserve exact aspect ratio
                            f"[original]scale=iw*min({width}/iw\\,{height}/ih):ih*min({width}/iw\\,{height}/ih)[original];",
                            
                            # Overlay original on blurred background with precise centering
                            f"[blurred][original]overlay=(W-w)/2:(H-h)/2",
                            
                            # Ensure proper color format
                            ",format=yuv420p",
                            
                            # Apply framerate correction for consistent motion
                            f",fps={self.framerate}"
                        ]
                        
                        # Join all filters - special handling for this complex string
                        filter_string = "".join(normalize_filters)
                        
                        # Process the segment with proper seeking, trimming and normalization
                        cmd = [
                            "ffmpeg",
                            "-y",
                            "-i",
                            temp_file_path,
                            "-ss",
                            str(start_offset),
                            "-t",
                            str(segment_duration),
                            "-vf",
                            filter_string,
                            "-c:v",
                            video_codec,
                        ]
                        cmd.extend(video_options)
                        cmd.extend([
                            "-pix_fmt",
                            "yuv420p",
                            "-r",
                            str(self.framerate),  # Apply consistent framerate
                            "-vsync",
                            "cfr",  # Constant framerate for smooth playback
                            "-sws_flags",
                            "bicubic",  # High-quality scaling
                            output_path,
                        ])
                        
                        subprocess.run(cmd, check=True)
                        print(f"Processed clip segment {index}: from offset {start_offset:.3f}s, duration {segment_duration:.3f}s")
                        
                        # Clean up temp file
                        os.unlink(temp_file_path)
                    except Exception as e:
                        print(f"Error processing clip segment file: {str(e)}")
                        # Create black video as fallback
                        self._create_black_video(output_path, target_duration, width, height, use_gpu, nvenc_preset)
                        print(f"Created black screen for failed clip segment {index}, duration: {target_duration:.3f}s")
                else:
                    # Create black video if no video file exists or file is missing
                    self._create_black_video(output_path, target_duration, width, height, use_gpu, nvenc_preset)
                    print(f"Created black screen for missing clip segment {index}, duration: {target_duration:.3f}s")
                    
            elif isinstance(clip_data, Subclip):
                # We're processing a subclip

                
                if clip_data.video_file:
                    try:
                        # Create a temporary file for processing
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_file:
                            # Download the file from storage
                            with default_storage.open(clip_data.video_file.name, 'rb') as s3_file:
                                temp_file.write(s3_file.read())
                            temp_file_path = temp_file.name
                        
                        # Determine the actual duration of the subclip video file
                        try:
                            probe_cmd = [
                                "ffprobe",
                                "-v", "error",
                                "-show_entries", "format=duration",
                                "-of", "default=noprint_wrappers=1:nokey=1",
                                temp_file_path
                            ]
                            actual_duration = float(subprocess.check_output(probe_cmd).decode("utf-8").strip())
                        except Exception as e:
                            logger.warning(f"Could not determine actual duration of subclip: {str(e)}")
                            actual_duration = target_duration  # Fallback to target duration
                        
                        # Check if we need to stretch the video or if it can be used as-is
                        if actual_duration < target_duration - 0.1:  # Add small tolerance of 0.1s
                            # Calculate required slowdown factor
                            required_slowdown = target_duration / actual_duration
                            print(f"Stretching subclip {index} from {actual_duration:.2f}s to {target_duration:.2f}s (factor: {required_slowdown:.2f}x)")
                            
                            # For extreme slowdowns, use frame interpolation for smoother slow motion
                            if required_slowdown > 3.0:
                                # Update to use blurred background approach with improved aspect ratio handling
                                normalize_filters = [
                                    # Split the video into two streams
                                    f"split=2[original][blurred];",
                                    
                                    # Scale and blur one stream to fill the frame
                                    f"[blurred]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},boxblur=luma_radius=min(h\\,w)/20:luma_power=1[blurred];",
                                    
                                    # Scale original with precise aspect ratio preservation
                                    f"[original]scale=iw*min({width}/iw\\,{height}/ih):ih*min({width}/iw\\,{height}/ih)[original];",
                                    
                                    # Apply frame interpolation for smoother slow motion
                                    f"[original]minterpolate=fps={self.framerate}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1[original];",
                                    
                                    # Apply the slowdown
                                    f"[original]setpts={required_slowdown}*PTS[original];",
                                    
                                    # Overlay original on blurred background with precise centering
                                    f"[blurred][original]overlay=(W-w)/2:(H-h)/2",
                                    
                                    # Ensure proper format
                                    ",format=yuv420p"
                                ]
                            else:
                                # Standard slowdown for moderate stretching with blurred background
                                normalize_filters = [
                                    # Split the video into two streams
                                    f"split=2[original][blurred];",
                                    
                                    # Scale and blur one stream to fill the frame
                                    f"[blurred]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},boxblur=luma_radius=min(h\\,w)/20:luma_power=1[blurred];",
                                    
                                    # Scale original with precise aspect ratio preservation
                                    f"[original]scale=iw*min({width}/iw\\,{height}/ih):ih*min({width}/iw\\,{height}/ih)[original];",
                                    
                                    # Apply slowdown
                                    f"[original]setpts={required_slowdown}*PTS[original];",
                                    
                                    # Overlay original on blurred background with precise centering
                                    f"[blurred][original]overlay=(W-w)/2:(H-h)/2",
                                    
                                    # Ensure proper format
                                    ",format=yuv420p",
                                    
                                    # Apply framerate correction
                                    f",fps={self.framerate}"
                                ]
                        else:
                            # The video is already long enough, use standard processing with blurred background
                            print(f"Subclip {index} already has sufficient duration: {actual_duration:.2f}s, target: {target_duration:.2f}s")
                            normalize_filters = [
                                # Split the video into two streams
                                f"split=2[original][blurred];",
                                
                                # Scale and blur one stream to fill the frame
                                f"[blurred]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},boxblur=luma_radius=min(h\\,w)/20:luma_power=1[blurred];",
                                
                                # Scale original with precise aspect ratio preservation
                                f"[original]scale=iw*min({width}/iw\\,{height}/ih):ih*min({width}/iw\\,{height}/ih)[original];",
                                
                                # Overlay original on blurred background with precise centering
                                f"[blurred][original]overlay=(W-w)/2:(H-h)/2",
                                
                                # Ensure proper format
                                ",format=yuv420p",
                                
                                # Apply framerate correction
                                f",fps={self.framerate}"
                            ]
                        
                        # Join all filters - special handling for this complex filter string
                        filter_string = "".join(normalize_filters)
                        
                        # Determine if we need to trim the input
                        input_duration = min(actual_duration, target_duration) if actual_duration > target_duration else actual_duration
                        
                        # For subclips, prioritize exact timing over aesthetic slowdown
                        # This ensures better synchronization with subtitles
                        if isinstance(clip_data, Subclip) and actual_duration < target_duration:
                            # Reduce slowdown factor to minimize timing issues
                            # Only slow down by at most 20% to maintain natural motion
                            max_slowdown = 1.2
                            if required_slowdown > max_slowdown:
                                print(f"Limiting subclip slowdown from {required_slowdown:.2f}x to {max_slowdown:.2f}x for better timing")
                                required_slowdown = max_slowdown
                            normalize_filters = [
                                # Split the video into two streams
                                f"split=2[original][blurred];",
                                
                                # Scale and blur one stream to fill the frame
                                f"[blurred]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},boxblur=luma_radius=min(h\\,w)/20:luma_power=1[blurred];",
                                
                                # Scale original with precise aspect ratio preservation
                                f"[original]scale=iw*min({width}/iw\\,{height}/ih):ih*min({width}/iw\\,{height}/ih)[original];",
                                
                                # Apply slowdown
                                f"[original]setpts={required_slowdown}*PTS[original];",
                                
                                # Overlay original on blurred background with precise centering
                                f"[blurred][original]overlay=(W-w)/2:(H-h)/2",
                                
                                # Ensure proper format
                                ",format=yuv420p",
                                
                                # Apply framerate correction
                                f",fps={self.framerate}"
                            ]
                        
                        cmd = [
                            "ffmpeg",
                            "-y",
                            "-i",
                            temp_file_path,
                        ]
                        
                        # Only add trim input if needed
                        if actual_duration > target_duration:
                            cmd.extend(["-t", str(input_duration)])
                        
                        cmd.extend([
                            "-vf",
                            filter_string,
                            "-c:v",
                            video_codec,
                        ])
                        cmd.extend(video_options)
                        cmd.extend([
                            "-pix_fmt",
                            "yuv420p",
                            "-r",
                            str(self.framerate),  # Apply consistent framerate
                            "-vsync",
                            "cfr",  # Constant framerate for smooth playback
                            "-sws_flags",
                            "bicubic",  # High-quality scaling
                        ])
                        
                        # Always set exact output duration to ensure perfect timing
                        cmd.extend(["-t", str(target_duration), output_path])
                        
                        subprocess.run(cmd, check=True)
                        print(f"Processed subclip {index}: duration {target_duration:.3f}s at position {start_time:.3f}s to {end_time:.3f}s")
                        
                        # Clean up temp file
                        os.unlink(temp_file_path)
                    except Exception as e:
                        print(f"Error processing subclip file: {str(e)}")
                        # Create black video as fallback
                        self._create_black_video(output_path, target_duration, width, height, use_gpu, nvenc_preset)
                        print(f"Created black screen for failed subclip {index}, duration: {target_duration:.3f}s")
                else:
                    # Create black video if no video file exists or file is missing
                    self._create_black_video(output_path, target_duration, width, height, use_gpu, nvenc_preset)
                    print(f"Created black screen for missing subclip {index}, duration: {target_duration:.3f}s")
            
            else:
                # Regular clip processing

                
                if clip_data.video_file:
                    try:
                        # Create a temporary file for processing
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_file:
                            # Download the file from storage
                            with default_storage.open(clip_data.video_file.name, 'rb') as s3_file:
                                temp_file.write(s3_file.read())
                            temp_file_path = temp_file.name
                        
                        # Enhanced normalization filters with blurred background approach - NO stretching
                        normalize_filters = [
                            # Split the video into two streams
                            f"split=2[original][blurred];",
                            
                            # Scale and blur one stream to fill the frame
                            f"[blurred]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},boxblur=luma_radius=min(h\\,w)/20:luma_power=1[blurred];",
                            
                            # Scale original with precise aspect ratio preservation
                            f"[original]scale=iw*min({width}/iw\\,{height}/ih):ih*min({width}/iw\\,{height}/ih)[original];",
                            
                            # Overlay original on blurred background with precise centering
                            f"[blurred][original]overlay=(W-w)/2:(H-h)/2",
                            
                            # Ensure proper color space and sampling
                            ",format=yuv420p",
                            
                            # Apply framerate correction for consistent motion
                            f",fps={self.framerate}"
                        ]
                        
                        # Add speed adjustment if needed
                        if speed_factor != 1.0:
                            # We need to modify the filter string to apply speed adjustment to the original stream before overlay
                            normalize_filters = [
                                # Split the video into two streams
                                f"split=2[original][blurred];",
                                
                                # Scale and blur one stream to fill the frame
                                f"[blurred]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},boxblur=luma_radius=min(h\\,w)/20:luma_power=1[blurred];",
                                
                                # Scale original with precise aspect ratio preservation
                                f"[original]scale=iw*min({width}/iw\\,{height}/ih):ih*min({width}/iw\\,{height}/ih)[original];",
                                
                                # Apply speed adjustment to original
                                f"[original]setpts={speed_factor}*PTS[original];",
                                
                                # Overlay original on blurred background with precise centering
                                f"[blurred][original]overlay=(W-w)/2:(H-h)/2",
                                
                                # Ensure proper color space and sampling
                                ",format=yuv420p",
                                
                                # Apply framerate correction for consistent motion
                                f",fps={self.framerate}"
                            ]
                        
                        # Join all filters - special handling for complex filter string
                        filter_string = "".join(normalize_filters)
                        
                        # Extract duration from clip or use target duration
                        clip_duration = clip_data.end_time - clip_data.start_time
                        
                        # Process the clip with proper seeking and trimming
                        cmd = [
                            "ffmpeg",
                            "-y",
                            "-i",
                            temp_file_path,
                            "-t",
                            str(clip_duration),
                            "-vf",
                            filter_string,
                            "-c:v",
                            video_codec,
                        ]
                        cmd.extend(video_options)
                        cmd.extend([
                            "-pix_fmt",
                            "yuv420p",
                            "-r",
                            str(self.framerate),  # Apply consistent framerate
                            "-vsync",
                            "cfr",  # Constant framerate for smooth playback
                            "-sws_flags",
                            "bicubic",  # High-quality scaling
                            output_path,
                        ])
                        
                        subprocess.run(cmd, check=True)
                        print(f"Processed clip {index}: duration {clip_duration:.3f}s with speed factor {speed_factor}")
                        
                        # Clean up temp file
                        os.unlink(temp_file_path)
                    except Exception as e:
                        print(f"Error processing clip file: {str(e)}")
                        # Create black video as fallback
                        self._create_black_video(output_path, target_duration, width, height, use_gpu, nvenc_preset)
                        print(f"Created black screen for failed clip {index}, duration: {target_duration:.3f}s")
                else:
                    # Create black video if no video file exists or file is missing
                    self._create_black_video(output_path, target_duration, width, height, use_gpu, nvenc_preset)
                    print(f"Created black screen for missing clip {index}, duration: {target_duration:.3f}s")

        except Exception as e:
            logger.error(f"Error processing item {index}: {str(e)}")
            # Fallback to black screen
            try:
                self._create_black_video(output_path, target_duration, width, height, False, None)
                print(f"Fallback to black screen for {index} after error")
            except Exception as e2:
                logger.error(f"Failed to create fallback black screen for {index}: {str(e2)}")



    def _create_black_video(
        self, output_path, duration, width, height, use_gpu=False, nvenc_preset=None
    ):
        """Create a black video clip with specified duration and dimensions"""
        print("*"*8)
        print("-=- Creating black video --")    
        print("*"*8)
        video_codec = "h264_nvenc" if use_gpu else "libx264"

        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=black:s={width}x{height}:r={self.framerate}",  # Include framerate in source
            "-t",
            str(duration),
            "-c:v",
            video_codec,
        ]

        if use_gpu:
            cmd.extend(["-preset", nvenc_preset])
        else:
            # For CPU encoding
            cmd.extend(["-preset", "medium"])
            # Only use tune for libx264, not for NVENC
            cmd.extend(["-tune", "stillimage"])

        cmd.extend(
            [
                "-pix_fmt",
                "yuv420p",
                "-r",
                str(self.framerate),  # Explicitly set framerate
                output_path,
            ]
        )

        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"Error creating black video: {str(e)}")
            if use_gpu:
                # Fallback to CPU encoding if GPU encoding fails
                print("Falling back to CPU encoding for black video")
                self._create_black_video(
                    output_path, duration, width, height, False, None
                )
            else:
                # Re-raise if we're already using CPU encoding
                raise
            
    def apply_background_music(self, bg_music: BackgroundMusic):
        """
        Applies background music to the video output.
        If music duration exceeds video duration, music is trimmed to match.
        Background music plays alongside the original video audio (not replacing it).
        
        Args:
            bg_music: BackgroundMusic object containing audio file and timing information
        
        Returns:
            bool: True if successful, False otherwise
        """
        video = self.video
        
        # Check if the video has an output file
        if not video.output:
            logger.error(f"No output file found for video {video.id}")
            return False
        
        # Check if background music has a valid audio file
        if not bg_music.audio_file:
            logger.error(f"No audio file associated with background music for video {video.id}")
            return False
            
        try:

            
            logger.info(f"Applying background music to video {video.id}")
            
            # Create temporary files for processing
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp_video:
                # Download the video file to temp location
                with default_storage.open(video.output_with_bg.name, 'rb') as s3_video:
                    tmp_video.write(s3_video.read())
                video_temp_path = tmp_video.name
                
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp_audio:
                # Download the audio file to temp location
                with default_storage.open(bg_music.audio_file.name, 'rb') as s3_audio:
                    tmp_audio.write(s3_audio.read())
                audio_temp_path = tmp_audio.name
            
            # Create output temp file
            temp_output_path = tempfile.mktemp(suffix='.mp4')
            
            # Get video duration using ffprobe
            video_duration_cmd = [
                "ffprobe", 
                "-v", "error", 
                "-show_entries", "format=duration", 
                "-of", "default=noprint_wrappers=1:nokey=1", 
                video_temp_path
            ]
            video_duration = float(subprocess.check_output(video_duration_cmd).decode("utf-8").strip())
            
            # Check if the video has an audio track
            has_audio_cmd = [
                "ffprobe",
                "-v", "error",
                "-select_streams", "a",
                "-show_entries", "stream=codec_type",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_temp_path
            ]
            
            has_audio_result = subprocess.run(has_audio_cmd, capture_output=True, text=True)
            has_audio = has_audio_result.stdout.strip() == "audio"
            
            # Get audio duration
            audio_duration_cmd = [
                "ffprobe", 
                "-v", "error", 
                "-show_entries", "format=duration", 
                "-of", "default=noprint_wrappers=1:nokey=1", 
                audio_temp_path
            ]
            try:
                audio_duration = float(subprocess.check_output(audio_duration_cmd).decode("utf-8").strip())
            except:
                audio_duration = 0
                
            # Check if audio needs to be trimmed
            start_time = min(bg_music.start_time, video_duration)
            
            # Handle case where start_time equals end_time or end_time is not specified correctly
            if bg_music.end_time <= bg_music.start_time or bg_music.end_time > video_duration:
                # Use the minimum of video duration or audio duration from the start point
                end_time = min(video_duration, start_time + audio_duration)
            else:
                end_time = min(bg_music.end_time, video_duration)
                
            # Ensure we have a positive duration
            if end_time <= start_time:
                # Default to playing until the end of the video
                end_time = video_duration
                
            duration = end_time - start_time
            
            # Ensure we have a positive duration
            if duration <= 0:
                # If duration is still not positive, use a minimum duration or the entire audio
                duration = min(audio_duration, video_duration - start_time)
                end_time = start_time + duration
                
                # If we still have zero duration, start from the beginning
                if duration <= 0:
                    start_time = 0
                    duration = min(audio_duration, video_duration)
                    end_time = start_time + duration
                    
                print(f"Adjusted timing to ensure positive duration: start={start_time:.2f}, end={end_time:.2f}, duration={duration:.2f}")
            
            # Use volume from bg_music (range 0 to 1)
            volume_level = bg_music.volumn if hasattr(bg_music, 'volumn') and 0 <= bg_music.volumn <= 1 else 0.3
            
            # Print report of the background music processing
            print(f"\nBackground Music Processing Report:")
            print(f"- Video ID: {video.id}")
            print(f"- Video Duration: {video_duration:.2f} seconds")
            print(f"- Audio Duration: {audio_duration:.2f} seconds")
            print(f"- Music File: {os.path.basename(bg_music.audio_file.name)}")
            print(f"- Start Time: {start_time:.2f} seconds")
            print(f"- End Time: {end_time:.2f} seconds")
            print(f"- Volume Level: {volume_level:.2f}")
            print(f"- Duration: {duration:.2f} seconds")
            print(f"- Output: {temp_output_path}")
            print(f"- Video has existing audio track: {has_audio}")
            
            # Check if our duration is too small
            if duration < 0.1:
                print(f"Warning: Duration is too small ({duration:.2f}s), defaulting to full audio length")
                start_time = 0
                duration = min(audio_duration, video_duration)
                end_time = start_time + duration
            
            # First, prepare a trimmed version of the background music
            trimmed_audio_path = tempfile.mktemp(suffix='.mp3')
            audio_trim_cmd = [
                "ffmpeg",
                "-y",
                "-i", audio_temp_path,
                "-ss", "0",  # Start from beginning of audio file
                "-t", str(duration),  # Duration to extract
                "-af", f"volume={volume_level}",  # Apply volume adjustment
                "-c:a", "mp3",  # Codec
                trimmed_audio_path
            ]
            
            print(f"Preparing trimmed audio: {' '.join(audio_trim_cmd)}")
            try:
                subprocess.run(audio_trim_cmd, capture_output=True, check=True)
            except subprocess.CalledProcessError as e:
                print(f"Error trimming audio: {str(e)}")
                # Use the original audio if trimming fails
                trimmed_audio_path = audio_temp_path
            
            # Method selection based on whether the video has audio
            if has_audio:
                # APPROACH 1: Extract original audio from video
                original_audio_path = tempfile.mktemp(suffix='.mp3')
                extract_cmd = [
                    "ffmpeg",
                    "-y",
                    "-i", video_temp_path,
                    "-vn",  # No video
                    "-c:a", "mp3",  # Codec
                    original_audio_path
                ]
                
                print(f"Extracting original audio: {' '.join(extract_cmd)}")
                try:
                    subprocess.run(extract_cmd, capture_output=True, check=True)
                except subprocess.CalledProcessError as e:
                    print(f"Error extracting original audio: {str(e)}")
                    # Continue with other approaches if extraction fails
                    has_audio = False
            
            if has_audio:
                # KEY CHANGE: Instead of silencing the original audio, reduce its volume during the background music
                # This allows both audio tracks to be heard
                reduced_vol_path = tempfile.mktemp(suffix='.mp3')
                original_audio_volume = 2  # Adjust this value to balance with bg music
                
                volume_filter = (
                    f"volume={original_audio_volume}:enable='between(t,{start_time},{end_time})',"
                    f"volume=1:enable='not(between(t,{start_time},{end_time}))'")
                
                reduce_vol_cmd = [
                    "ffmpeg",
                    "-y",
                    "-i", original_audio_path,
                    "-af", volume_filter,
                    "-c:a", "mp3",
                    reduced_vol_path
                ]
                
                print(f"Creating audio with reduced volume during bg music: {' '.join(reduce_vol_cmd)}")
                try:
                    subprocess.run(reduce_vol_cmd, capture_output=True, check=True)
                except subprocess.CalledProcessError as e:
                    print(f"Error creating reduced volume audio: {str(e)}")
                    # Just use the original audio
                    reduced_vol_path = original_audio_path
                
                # Create a version of the trimmed background music with silence everywhere except where it should play
                music_timing_path = tempfile.mktemp(suffix='.mp3')
                # We need to create an audio file that's the full length of the video
                padding_cmd = [
                    "ffmpeg",
                    "-y",
                    "-i", trimmed_audio_path,
                    "-af", f"apad=whole_dur={video_duration}",
                    "-c:a", "mp3",
                    music_timing_path
                ]
                
                print(f"Creating padded background music: {' '.join(padding_cmd)}")
                try:
                    subprocess.run(padding_cmd, capture_output=True, check=True)
                    music_positioned = True
                except subprocess.CalledProcessError as e:
                    print(f"Error padding music: {str(e)}")
                    music_positioned = False
                    
                if music_positioned:
                    # Create a temporary file with the positioned music
                    positioned_music_path = tempfile.mktemp(suffix='.mp3')
                    position_cmd = [
                        "ffmpeg",
                        "-y",
                        "-i", music_timing_path,
                        "-af", f"adelay={int(start_time*1000)}|{int(start_time*1000)}",
                        "-c:a", "mp3",
                        positioned_music_path
                    ]
                    
                    print(f"Positioning music at {start_time}s: {' '.join(position_cmd)}")
                    try:
                        subprocess.run(position_cmd, capture_output=True, check=True)
                    except subprocess.CalledProcessError as e:
                        print(f"Error positioning music: {str(e)}")
                        # Use the padded version
                        positioned_music_path = music_timing_path
                        
                    # Mix the original audio (with reduced volume during bg music) and the positioned background music
                    mixed_audio_path = tempfile.mktemp(suffix='.mp3')
                    mix_cmd = [
                        "ffmpeg",
                        "-y",
                        "-i", reduced_vol_path,
                        "-i", positioned_music_path,
                        "-filter_complex", "amix=inputs=2:duration=first:weights=1 1",
                        "-c:a", "mp3",
                        mixed_audio_path
                    ]
                    
                    print(f"Mixing audio: {' '.join(mix_cmd)}")
                    try:
                        subprocess.run(mix_cmd, capture_output=True, check=True)
                        # The mix worked, now combine with video
                        final_cmd = [
                            "ffmpeg",
                            "-y",
                            "-i", video_temp_path,
                            "-i", mixed_audio_path,
                            "-c:v", "copy",
                            "-c:a", "aac",
                            "-map", "0:v",
                            "-map", "1:a",
                            "-shortest",
                            temp_output_path
                        ]
                        
                        print(f"Final combine: {' '.join(final_cmd)}")
                        subprocess.run(final_cmd, capture_output=True, check=True)
                        success = True
                    except subprocess.CalledProcessError as e:
                        print(f"Error in audio mixing or final combine: {str(e)}")
                        success = False
                else:
                    success = False
                
                # Clean up intermediate audio files
                for temp_file in [original_audio_path, reduced_vol_path, music_timing_path, 
                                positioned_music_path if 'positioned_music_path' in locals() else None, 
                                mixed_audio_path if 'mixed_audio_path' in locals() else None]:
                    if temp_file and os.path.exists(temp_file):
                        try:
                            os.unlink(temp_file)
                        except:
                            pass
            else:
                # No existing audio, simpler approach
                success = False
            
            # If the complex approach failed or there's no audio, try a simpler approach
            if not success or not has_audio:
                # APPROACH 2: For videos without audio or if the complex approach failed
                print("Using direct overlay approach for video without audio")
                
                # Create silent base for the full video duration
                silent_base_path = tempfile.mktemp(suffix='.mp3')
                try:
                    # First try with anullsrc
                    silence_cmd = [
                        "ffmpeg",
                        "-y",
                        "-f", "lavfi",
                        "-i", f"anullsrc=r=44100:cl=stereo:d={video_duration}",
                        "-c:a", "mp3",
                        silent_base_path
                    ]
                    
                    print(f"Creating silent base with anullsrc: {' '.join(silence_cmd)}")
                    subprocess.run(silence_cmd, capture_output=True, check=True)
                    silence_created = True
                except:
                    # If anullsrc fails, create a very short silence and extend it
                    try:
                        # Generate 0.1s of silence
                        silence_gen_cmd = [
                            "ffmpeg",
                            "-y",
                            "-f", "lavfi",
                            "-i", "anullsrc=r=44100:cl=stereo:d=0.1",
                            "-c:a", "mp3",
                            silent_base_path
                        ]
                        
                        print(f"Creating short silence: {' '.join(silence_gen_cmd)}")
                        subprocess.run(silence_gen_cmd, capture_output=True, check=True)
                        
                        # Now extend it to full duration
                        extended_silence_path = tempfile.mktemp(suffix='.mp3')
                        extend_cmd = [
                            "ffmpeg",
                            "-y",
                            "-i", silent_base_path,
                            "-af", f"apad=whole_dur={video_duration}",
                            "-c:a", "mp3",
                            extended_silence_path
                        ]
                        
                        print(f"Extending silence: {' '.join(extend_cmd)}")
                        subprocess.run(extend_cmd, capture_output=True, check=True)
                        
                        # Replace the original silence with the extended one
                        os.unlink(silent_base_path)
                        silent_base_path = extended_silence_path
                        silence_created = True
                    except:
                        print("Could not create silent base, using direct approach")
                        silence_created = False
                
                if silence_created:
                    # Now overlay the trimmed background music at the specified position
                    overlay_cmd = [
                        "ffmpeg",
                        "-y",
                        "-i", silent_base_path,
                        "-i", trimmed_audio_path,
                        "-filter_complex", f"[1:a]adelay={int(start_time*1000)}|{int(start_time*1000)}[delayed];[0:a][delayed]amix=inputs=2:duration=first[a]",
                        "-map", "[a]",
                        "-c:a", "mp3",
                        "-b:a", "192k",
                        tempfile.mktemp(suffix='.mp3')
                    ]
                    
                    print(f"Creating overlay audio: {' '.join(overlay_cmd)}")
                    try:
                        result = subprocess.run(overlay_cmd, capture_output=True, check=True)
                        final_audio_path = result.stdout.decode().strip()
                        
                        # Combine with video
                        final_cmd = [
                            "ffmpeg",
                            "-y",
                            "-i", video_temp_path,
                            "-i", final_audio_path,
                            "-c:v", "copy",
                            "-c:a", "aac",
                            "-map", "0:v",
                            "-map", "1:a",
                            "-shortest",
                            temp_output_path
                        ]
                        
                        print(f"Final combine: {' '.join(final_cmd)}")
                        subprocess.run(final_cmd, capture_output=True, check=True)
                        success = True
                    except subprocess.CalledProcessError as e:
                        print(f"Overlay or combine failed: {str(e)}")
                        success = False
                
                # Last resort if previous methods failed
                if not success:
                    print("Using fallback direct approach")
                    # Create a trimmed version of the input video
                    silent_video_path = tempfile.mktemp(suffix='.mp4')
                    silent_cmd = [
                        "ffmpeg",
                        "-y",
                        "-i", video_temp_path,
                        "-an",  # Remove audio
                        "-c:v", "copy",
                        silent_video_path
                    ]
                    
                    print(f"Creating silent video: {' '.join(silent_cmd)}")
                    try:
                        subprocess.run(silent_cmd, capture_output=True, check=True)
                    except subprocess.CalledProcessError as e:
                        print(f"Error creating silent video: {str(e)}")
                        # Use the original video
                        silent_video_path = video_temp_path
                        
                    # Create a precisely timed audio segment
                    precise_audio_path = tempfile.mktemp(suffix='.mp3')
                    
                    # Create an audio track with specific timing
                    ffmpeg_complex_filter = (
                        # Create a silent audio track for the entire video duration
                        f"-f lavfi -t {video_duration} -i anullsrc=r=44100:cl=stereo " +
                        # Add the trimmed music starting at the specified time
                        f"-i {trimmed_audio_path} " +
                        # Mix them together
                        f"-filter_complex \"[1:a]adelay={int(start_time*1000)}|{int(start_time*1000)}[delayed];" +
                        f"[0:a][delayed]amix=inputs=2:duration=first[a]\" " +
                        # Output the mixed audio
                        f"-map \"[a]\" -c:a aac -b:a 192k {precise_audio_path}"
                    )
                    
                    print(f"Attempting complex filter: {ffmpeg_complex_filter}")
                    try:
                        os.system(f"ffmpeg -y {ffmpeg_complex_filter}")
                        
                        # If that worked, combine with the video
                        final_cmd = [
                            "ffmpeg",
                            "-y",
                            "-i", silent_video_path,
                            "-i", precise_audio_path,
                            "-c:v", "copy",
                            "-c:a", "aac",
                            "-map", "0:v",
                            "-map", "1:a",
                            "-shortest",
                            temp_output_path
                        ]
                        
                        print(f"Final combine: {' '.join(final_cmd)}")
                        subprocess.run(final_cmd, capture_output=True, check=True)
                    except:
                        print("Complex filter failed, using direct audio overlay")
                        
                        # Absolutely simplest approach - use direct concatenation
                        concat_list_path = tempfile.mktemp(suffix='.txt')
                        with open(concat_list_path, 'w') as f:
                            if start_time > 0:
                                # Create a silent MP3 for the pre-music segment
                                pre_silence_path = tempfile.mktemp(suffix='.mp3')
                                pre_silence_cmd = [
                                    "ffmpeg",
                                    "-y",
                                    "-f", "lavfi",
                                    "-i", f"anullsrc=r=44100:cl=stereo:d={start_time}",
                                    "-c:a", "mp3",
                                    pre_silence_path
                                ]
                                
                                try:
                                    subprocess.run(pre_silence_cmd, capture_output=True)
                                    f.write(f"file '{pre_silence_path}'\n")
                                except:
                                    print("Could not create pre-silence")
                            
                            # Add the background music segment
                            f.write(f"file '{trimmed_audio_path}'\n")
                            
                            # If there's time after the music, add silence
                            if end_time < video_duration:
                                post_silence_duration = video_duration - end_time
                                post_silence_path = tempfile.mktemp(suffix='.mp3')
                                post_silence_cmd = [
                                    "ffmpeg",
                                    "-y",
                                    "-f", "lavfi",
                                    "-i", f"anullsrc=r=44100:cl=stereo:d={post_silence_duration}",
                                    "-c:a", "mp3",
                                    post_silence_path
                                ]
                                
                                try:
                                    subprocess.run(post_silence_cmd, capture_output=True)
                                    f.write(f"file '{post_silence_path}'\n")
                                except:
                                    print("Could not create post-silence")
                        
                        # Concatenate the audio segments
                        concat_audio_path = tempfile.mktemp(suffix='.mp3')
                        concat_cmd = [
                            "ffmpeg",
                            "-y",
                            "-f", "concat",
                            "-safe", "0",
                            "-i", concat_list_path,
                            "-c:a", "mp3",
                            concat_audio_path
                        ]
                        
                        print(f"Concatenating audio segments: {' '.join(concat_cmd)}")
                        try:
                            subprocess.run(concat_cmd, capture_output=True, check=True)
                            
                            # Finally, combine with the video
                            last_cmd = [
                                "ffmpeg",
                                "-y",
                                "-i", silent_video_path,
                                "-i", concat_audio_path,
                                "-c:v", "copy",
                                "-c:a", "aac",
                                "-map", "0:v",
                                "-map", "1:a",
                                "-shortest",
                                temp_output_path
                            ]
                            
                            print(f"Final combine: {' '.join(last_cmd)}")
                            subprocess.run(last_cmd, capture_output=True, check=True)
                        except subprocess.CalledProcessError as e:
                            print(f"Error in final concatenation: {str(e)}")
                            
                            # As an absolute last resort, just use the simple approach
                            print("Using absolute simplest approach - direct overlay without timing")
                            last_resort_cmd = [
                                "ffmpeg",
                                "-y",
                                "-i", video_temp_path,
                                "-i", trimmed_audio_path,  # Use the trimmed music directly
                                "-c:v", "copy",
                                "-c:a", "aac",
                                "-map", "0:v",
                                "-map", "1:a",  # Use audio directly
                                "-shortest",
                                temp_output_path
                            ]
                            
                            print(f"Last resort command: {' '.join(last_resort_cmd)}")
                            subprocess.run(last_resort_cmd, capture_output=True, check=True)
            
            # Verify the output has audio
            verify_cmd = [
                "ffprobe",
                "-v", "error",
                "-select_streams", "a",
                "-show_entries", "stream=codec_type",
                "-of", "default=noprint_wrappers=1:nokey=1",
                temp_output_path
            ]
            
            verify_result = subprocess.run(verify_cmd, capture_output=True, text=True)
            has_output_audio = verify_result.stdout.strip() == "audio"
            
            print(f"- Output video has audio track: {has_output_audio}")
            
            # Update the video output_with_bg file instead of the original output
            filename = f"{os.path.splitext(os.path.basename(video.output.name))[0]}_with_bg.mp4"
            with open(temp_output_path, 'rb') as f:
                # Save to output_with_bg instead of output
                video.output_with_bg.save(filename, File(f), save=True)


            # Clean up temporary files
            for temp_file in [video_temp_path, audio_temp_path, temp_output_path, trimmed_audio_path]:
                if os.path.exists(temp_file):
                    try:
                        os.unlink(temp_file)
                    except:
                        pass
            
            logger.info(f"Successfully applied background music to video {video.id}, saved as output_with_bg")
            return True
            
        except Exception as e:
            logger.error(f"Error applying background music to video {video.id}: {str(e)}")
            print(f"Error applying background music: {str(e)}")
            # Clean up temporary files if they exist
            for var_name in ['video_temp_path', 'audio_temp_path', 'temp_output_path', 'trimmed_audio_path']:
                if var_name in locals() and locals()[var_name] and os.path.exists(locals()[var_name]):
                    try:
                        os.unlink(locals()[var_name])
                    except:
                        pass
            return False


         
    def apply_background_music_watermark(self, bg_music: BackgroundMusic):
        """
        Applies background music to the video output.
        If music duration exceeds video duration, music is trimmed to match.
        Background music plays alongside the original video audio (not replacing it).
        
        Args:
            bg_music: BackgroundMusic object containing audio file and timing information
        
        Returns:
            bool: True if successful, False otherwise
        """
        video = self.video
        
        # Check if the video has an output file
        if not video.output:
            logger.error(f"No output file found for video {video.id}")
            return False
        
        # Check if background music has a valid audio file
        if not bg_music.audio_file:
            logger.error(f"No audio file associated with background music for video {video.id}")
            return False
            
        try:

            
            logger.info(f"Applying background music to video {video.id}")
            
            # Create temporary files for processing
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp_video:
                # Download the video file to temp location
                with default_storage.open(video.output_with_bg_watermark.name, 'rb') as s3_video:
                    tmp_video.write(s3_video.read())
                video_temp_path = tmp_video.name
                
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp_audio:
                # Download the audio file to temp location
                with default_storage.open(bg_music.audio_file.name, 'rb') as s3_audio:
                    tmp_audio.write(s3_audio.read())
                audio_temp_path = tmp_audio.name
            
            # Create output temp file
            temp_output_path = tempfile.mktemp(suffix='.mp4')
            
            # Get video duration using ffprobe
            video_duration_cmd = [
                "ffprobe", 
                "-v", "error", 
                "-show_entries", "format=duration", 
                "-of", "default=noprint_wrappers=1:nokey=1", 
                video_temp_path
            ]
            video_duration = float(subprocess.check_output(video_duration_cmd).decode("utf-8").strip())
            
            # Check if the video has an audio track
            has_audio_cmd = [
                "ffprobe",
                "-v", "error",
                "-select_streams", "a",
                "-show_entries", "stream=codec_type",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_temp_path
            ]
            
            has_audio_result = subprocess.run(has_audio_cmd, capture_output=True, text=True)
            has_audio = has_audio_result.stdout.strip() == "audio"
            
            # Get audio duration
            audio_duration_cmd = [
                "ffprobe", 
                "-v", "error", 
                "-show_entries", "format=duration", 
                "-of", "default=noprint_wrappers=1:nokey=1", 
                audio_temp_path
            ]
            try:
                audio_duration = float(subprocess.check_output(audio_duration_cmd).decode("utf-8").strip())
            except:
                audio_duration = 0
                
            # Check if audio needs to be trimmed
            start_time = min(bg_music.start_time, video_duration)
            
            # Handle case where start_time equals end_time or end_time is not specified correctly
            if bg_music.end_time <= bg_music.start_time or bg_music.end_time > video_duration:
                # Use the minimum of video duration or audio duration from the start point
                end_time = min(video_duration, start_time + audio_duration)
            else:
                end_time = min(bg_music.end_time, video_duration)
                
            # Ensure we have a positive duration
            if end_time <= start_time:
                # Default to playing until the end of the video
                end_time = video_duration
                
            duration = end_time - start_time
            
            # Ensure we have a positive duration
            if duration <= 0:
                # If duration is still not positive, use a minimum duration or the entire audio
                duration = min(audio_duration, video_duration - start_time)
                end_time = start_time + duration
                
                # If we still have zero duration, start from the beginning
                if duration <= 0:
                    start_time = 0
                    duration = min(audio_duration, video_duration)
                    end_time = start_time + duration
                    
                print(f"Adjusted timing to ensure positive duration: start={start_time:.2f}, end={end_time:.2f}, duration={duration:.2f}")
            
            # Use volume from bg_music (range 0 to 1)
            volume_level = bg_music.volumn if hasattr(bg_music, 'volumn') and 0 <= bg_music.volumn <= 1 else 0.3
            
            # Print report of the background music processing
            print(f"\nBackground Music Processing Report:")
            print(f"- Video ID: {video.id}")
            print(f"- Video Duration: {video_duration:.2f} seconds")
            print(f"- Audio Duration: {audio_duration:.2f} seconds")
            print(f"- Music File: {os.path.basename(bg_music.audio_file.name)}")
            print(f"- Start Time: {start_time:.2f} seconds")
            print(f"- End Time: {end_time:.2f} seconds")
            print(f"- Volume Level: {volume_level:.2f}")
            print(f"- Duration: {duration:.2f} seconds")
            print(f"- Output: {temp_output_path}")
            print(f"- Video has existing audio track: {has_audio}")
            
            # Check if our duration is too small
            if duration < 0.1:
                print(f"Warning: Duration is too small ({duration:.2f}s), defaulting to full audio length")
                start_time = 0
                duration = min(audio_duration, video_duration)
                end_time = start_time + duration
            
            # First, prepare a trimmed version of the background music
            trimmed_audio_path = tempfile.mktemp(suffix='.mp3')
            audio_trim_cmd = [
                "ffmpeg",
                "-y",
                "-i", audio_temp_path,
                "-ss", "0",  # Start from beginning of audio file
                "-t", str(duration),  # Duration to extract
                "-af", f"volume={volume_level}",  # Apply volume adjustment
                "-c:a", "mp3",  # Codec
                trimmed_audio_path
            ]
            
            print(f"Preparing trimmed audio: {' '.join(audio_trim_cmd)}")
            try:
                subprocess.run(audio_trim_cmd, capture_output=True, check=True)
            except subprocess.CalledProcessError as e:
                print(f"Error trimming audio: {str(e)}")
                # Use the original audio if trimming fails
                trimmed_audio_path = audio_temp_path
            
            # Method selection based on whether the video has audio
            if has_audio:
                # APPROACH 1: Extract original audio from video
                original_audio_path = tempfile.mktemp(suffix='.mp3')
                extract_cmd = [
                    "ffmpeg",
                    "-y",
                    "-i", video_temp_path,
                    "-vn",  # No video
                    "-c:a", "mp3",  # Codec
                    original_audio_path
                ]
                
                print(f"Extracting original audio: {' '.join(extract_cmd)}")
                try:
                    subprocess.run(extract_cmd, capture_output=True, check=True)
                except subprocess.CalledProcessError as e:
                    print(f"Error extracting original audio: {str(e)}")
                    # Continue with other approaches if extraction fails
                    has_audio = False
            
            if has_audio:
                # KEY CHANGE: Instead of silencing the original audio, reduce its volume during the background music
                # This allows both audio tracks to be heard
                reduced_vol_path = tempfile.mktemp(suffix='.mp3')
                original_audio_volume = 2  # Adjust this value to balance with bg music
                
                volume_filter = (
                    f"volume={original_audio_volume}:enable='between(t,{start_time},{end_time})',"
                    f"volume=1:enable='not(between(t,{start_time},{end_time}))'")
                
                reduce_vol_cmd = [
                    "ffmpeg",
                    "-y",
                    "-i", original_audio_path,
                    "-af", volume_filter,
                    "-c:a", "mp3",
                    reduced_vol_path
                ]
                
                print(f"Creating audio with reduced volume during bg music: {' '.join(reduce_vol_cmd)}")
                try:
                    subprocess.run(reduce_vol_cmd, capture_output=True, check=True)
                except subprocess.CalledProcessError as e:
                    print(f"Error creating reduced volume audio: {str(e)}")
                    # Just use the original audio
                    reduced_vol_path = original_audio_path
                
                # Create a version of the trimmed background music with silence everywhere except where it should play
                music_timing_path = tempfile.mktemp(suffix='.mp3')
                # We need to create an audio file that's the full length of the video
                padding_cmd = [
                    "ffmpeg",
                    "-y",
                    "-i", trimmed_audio_path,
                    "-af", f"apad=whole_dur={video_duration}",
                    "-c:a", "mp3",
                    music_timing_path
                ]
                
                print(f"Creating padded background music: {' '.join(padding_cmd)}")
                try:
                    subprocess.run(padding_cmd, capture_output=True, check=True)
                    music_positioned = True
                except subprocess.CalledProcessError as e:
                    print(f"Error padding music: {str(e)}")
                    music_positioned = False
                    
                if music_positioned:
                    # Create a temporary file with the positioned music
                    positioned_music_path = tempfile.mktemp(suffix='.mp3')
                    position_cmd = [
                        "ffmpeg",
                        "-y",
                        "-i", music_timing_path,
                        "-af", f"adelay={int(start_time*1000)}|{int(start_time*1000)}",
                        "-c:a", "mp3",
                        positioned_music_path
                    ]
                    
                    print(f"Positioning music at {start_time}s: {' '.join(position_cmd)}")
                    try:
                        subprocess.run(position_cmd, capture_output=True, check=True)
                    except subprocess.CalledProcessError as e:
                        print(f"Error positioning music: {str(e)}")
                        # Use the padded version
                        positioned_music_path = music_timing_path
                        
                    # Mix the original audio (with reduced volume during bg music) and the positioned background music
                    mixed_audio_path = tempfile.mktemp(suffix='.mp3')
                    mix_cmd = [
                        "ffmpeg",
                        "-y",
                        "-i", reduced_vol_path,
                        "-i", positioned_music_path,
                        "-filter_complex", "amix=inputs=2:duration=first:weights=1 1",
                        "-c:a", "mp3",
                        mixed_audio_path
                    ]
                    
                    print(f"Mixing audio: {' '.join(mix_cmd)}")
                    try:
                        subprocess.run(mix_cmd, capture_output=True, check=True)
                        # The mix worked, now combine with video
                        final_cmd = [
                            "ffmpeg",
                            "-y",
                            "-i", video_temp_path,
                            "-i", mixed_audio_path,
                            "-c:v", "copy",
                            "-c:a", "aac",
                            "-map", "0:v",
                            "-map", "1:a",
                            "-shortest",
                            temp_output_path
                        ]
                        
                        print(f"Final combine: {' '.join(final_cmd)}")
                        subprocess.run(final_cmd, capture_output=True, check=True)
                        success = True
                    except subprocess.CalledProcessError as e:
                        print(f"Error in audio mixing or final combine: {str(e)}")
                        success = False
                else:
                    success = False
                
                # Clean up intermediate audio files
                for temp_file in [original_audio_path, reduced_vol_path, music_timing_path, 
                                positioned_music_path if 'positioned_music_path' in locals() else None, 
                                mixed_audio_path if 'mixed_audio_path' in locals() else None]:
                    if temp_file and os.path.exists(temp_file):
                        try:
                            os.unlink(temp_file)
                        except:
                            pass
            else:
                # No existing audio, simpler approach
                success = False
            
            # If the complex approach failed or there's no audio, try a simpler approach
            if not success or not has_audio:
                # APPROACH 2: For videos without audio or if the complex approach failed
                print("Using direct overlay approach for video without audio")
                
                # Create silent base for the full video duration
                silent_base_path = tempfile.mktemp(suffix='.mp3')
                try:
                    # First try with anullsrc
                    silence_cmd = [
                        "ffmpeg",
                        "-y",
                        "-f", "lavfi",
                        "-i", f"anullsrc=r=44100:cl=stereo:d={video_duration}",
                        "-c:a", "mp3",
                        silent_base_path
                    ]
                    
                    print(f"Creating silent base with anullsrc: {' '.join(silence_cmd)}")
                    subprocess.run(silence_cmd, capture_output=True, check=True)
                    silence_created = True
                except:
                    # If anullsrc fails, create a very short silence and extend it
                    try:
                        # Generate 0.1s of silence
                        silence_gen_cmd = [
                            "ffmpeg",
                            "-y",
                            "-f", "lavfi",
                            "-i", "anullsrc=r=44100:cl=stereo:d=0.1",
                            "-c:a", "mp3",
                            silent_base_path
                        ]
                        
                        print(f"Creating short silence: {' '.join(silence_gen_cmd)}")
                        subprocess.run(silence_gen_cmd, capture_output=True, check=True)
                        
                        # Now extend it to full duration
                        extended_silence_path = tempfile.mktemp(suffix='.mp3')
                        extend_cmd = [
                            "ffmpeg",
                            "-y",
                            "-i", silent_base_path,
                            "-af", f"apad=whole_dur={video_duration}",
                            "-c:a", "mp3",
                            extended_silence_path
                        ]
                        
                        print(f"Extending silence: {' '.join(extend_cmd)}")
                        subprocess.run(extend_cmd, capture_output=True, check=True)
                        
                        # Replace the original silence with the extended one
                        os.unlink(silent_base_path)
                        silent_base_path = extended_silence_path
                        silence_created = True
                    except:
                        print("Could not create silent base, using direct approach")
                        silence_created = False
                
                if silence_created:
                    # Now overlay the trimmed background music at the specified position
                    overlay_cmd = [
                        "ffmpeg",
                        "-y",
                        "-i", silent_base_path,
                        "-i", trimmed_audio_path,
                        "-filter_complex", f"[1:a]adelay={int(start_time*1000)}|{int(start_time*1000)}[delayed];[0:a][delayed]amix=inputs=2:duration=first[a]",
                        "-map", "[a]",
                        "-c:a", "mp3",
                        "-b:a", "192k",
                        tempfile.mktemp(suffix='.mp3')
                    ]
                    
                    print(f"Creating overlay audio: {' '.join(overlay_cmd)}")
                    try:
                        result = subprocess.run(overlay_cmd, capture_output=True, check=True)
                        final_audio_path = result.stdout.decode().strip()
                        
                        # Combine with video
                        final_cmd = [
                            "ffmpeg",
                            "-y",
                            "-i", video_temp_path,
                            "-i", final_audio_path,
                            "-c:v", "copy",
                            "-c:a", "aac",
                            "-map", "0:v",
                            "-map", "1:a",
                            "-shortest",
                            temp_output_path
                        ]
                        
                        print(f"Final combine: {' '.join(final_cmd)}")
                        subprocess.run(final_cmd, capture_output=True, check=True)
                        success = True
                    except subprocess.CalledProcessError as e:
                        print(f"Overlay or combine failed: {str(e)}")
                        success = False
                
                # Last resort if previous methods failed
                if not success:
                    print("Using fallback direct approach")
                    # Create a trimmed version of the input video
                    silent_video_path = tempfile.mktemp(suffix='.mp4')
                    silent_cmd = [
                        "ffmpeg",
                        "-y",
                        "-i", video_temp_path,
                        "-an",  # Remove audio
                        "-c:v", "copy",
                        silent_video_path
                    ]
                    
                    print(f"Creating silent video: {' '.join(silent_cmd)}")
                    try:
                        subprocess.run(silent_cmd, capture_output=True, check=True)
                    except subprocess.CalledProcessError as e:
                        print(f"Error creating silent video: {str(e)}")
                        # Use the original video
                        silent_video_path = video_temp_path
                        
                    # Create a precisely timed audio segment
                    precise_audio_path = tempfile.mktemp(suffix='.mp3')
                    
                    # Create an audio track with specific timing
                    ffmpeg_complex_filter = (
                        # Create a silent audio track for the entire video duration
                        f"-f lavfi -t {video_duration} -i anullsrc=r=44100:cl=stereo " +
                        # Add the trimmed music starting at the specified time
                        f"-i {trimmed_audio_path} " +
                        # Mix them together
                        f"-filter_complex \"[1:a]adelay={int(start_time*1000)}|{int(start_time*1000)}[delayed];" +
                        f"[0:a][delayed]amix=inputs=2:duration=first[a]\" " +
                        # Output the mixed audio
                        f"-map \"[a]\" -c:a aac -b:a 192k {precise_audio_path}"
                    )
                    
                    print(f"Attempting complex filter: {ffmpeg_complex_filter}")
                    try:
                        os.system(f"ffmpeg -y {ffmpeg_complex_filter}")
                        
                        # If that worked, combine with the video
                        final_cmd = [
                            "ffmpeg",
                            "-y",
                            "-i", silent_video_path,
                            "-i", precise_audio_path,
                            "-c:v", "copy",
                            "-c:a", "aac",
                            "-map", "0:v",
                            "-map", "1:a",
                            "-shortest",
                            temp_output_path
                        ]
                        
                        print(f"Final combine: {' '.join(final_cmd)}")
                        subprocess.run(final_cmd, capture_output=True, check=True)
                    except:
                        print("Complex filter failed, using direct audio overlay")
                        
                        # Absolutely simplest approach - use direct concatenation
                        concat_list_path = tempfile.mktemp(suffix='.txt')
                        with open(concat_list_path, 'w') as f:
                            if start_time > 0:
                                # Create a silent MP3 for the pre-music segment
                                pre_silence_path = tempfile.mktemp(suffix='.mp3')
                                pre_silence_cmd = [
                                    "ffmpeg",
                                    "-y",
                                    "-f", "lavfi",
                                    "-i", f"anullsrc=r=44100:cl=stereo:d={start_time}",
                                    "-c:a", "mp3",
                                    pre_silence_path
                                ]
                                
                                try:
                                    subprocess.run(pre_silence_cmd, capture_output=True)
                                    f.write(f"file '{pre_silence_path}'\n")
                                except:
                                    print("Could not create pre-silence")
                            
                            # Add the background music segment
                            f.write(f"file '{trimmed_audio_path}'\n")
                            
                            # If there's time after the music, add silence
                            if end_time < video_duration:
                                post_silence_duration = video_duration - end_time
                                post_silence_path = tempfile.mktemp(suffix='.mp3')
                                post_silence_cmd = [
                                    "ffmpeg",
                                    "-y",
                                    "-f", "lavfi",
                                    "-i", f"anullsrc=r=44100:cl=stereo:d={post_silence_duration}",
                                    "-c:a", "mp3",
                                    post_silence_path
                                ]
                                
                                try:
                                    subprocess.run(post_silence_cmd, capture_output=True)
                                    f.write(f"file '{post_silence_path}'\n")
                                except:
                                    print("Could not create post-silence")
                        
                        # Concatenate the audio segments
                        concat_audio_path = tempfile.mktemp(suffix='.mp3')
                        concat_cmd = [
                            "ffmpeg",
                            "-y",
                            "-f", "concat",
                            "-safe", "0",
                            "-i", concat_list_path,
                            "-c:a", "mp3",
                            concat_audio_path
                        ]
                        
                        print(f"Concatenating audio segments: {' '.join(concat_cmd)}")
                        try:
                            subprocess.run(concat_cmd, capture_output=True, check=True)
                            
                            # Finally, combine with the video
                            last_cmd = [
                                "ffmpeg",
                                "-y",
                                "-i", silent_video_path,
                                "-i", concat_audio_path,
                                "-c:v", "copy",
                                "-c:a", "aac",
                                "-map", "0:v",
                                "-map", "1:a",
                                "-shortest",
                                temp_output_path
                            ]
                            
                            print(f"Final combine: {' '.join(last_cmd)}")
                            subprocess.run(last_cmd, capture_output=True, check=True)
                        except subprocess.CalledProcessError as e:
                            print(f"Error in final concatenation: {str(e)}")
                            
                            # As an absolute last resort, just use the simple approach
                            print("Using absolute simplest approach - direct overlay without timing")
                            last_resort_cmd = [
                                "ffmpeg",
                                "-y",
                                "-i", video_temp_path,
                                "-i", trimmed_audio_path,  # Use the trimmed music directly
                                "-c:v", "copy",
                                "-c:a", "aac",
                                "-map", "0:v",
                                "-map", "1:a",  # Use audio directly
                                "-shortest",
                                temp_output_path
                            ]
                            
                            print(f"Last resort command: {' '.join(last_resort_cmd)}")
                            subprocess.run(last_resort_cmd, capture_output=True, check=True)
            
            # Verify the output has audio
            verify_cmd = [
                "ffprobe",
                "-v", "error",
                "-select_streams", "a",
                "-show_entries", "stream=codec_type",
                "-of", "default=noprint_wrappers=1:nokey=1",
                temp_output_path
            ]
            
            verify_result = subprocess.run(verify_cmd, capture_output=True, text=True)
            has_output_audio = verify_result.stdout.strip() == "audio"
            
            print(f"- Output video has audio track: {has_output_audio}")
            
            # Update the video output_with_bg file instead of the original output
            filename = f"{os.path.splitext(os.path.basename(video.output.name))[0]}_with_bg_watermark.mp4"
            with open(temp_output_path, 'rb') as f:
                # Save to output_with_bg instead of output
                video.output_with_bg_watermark.save(filename, File(f), save=True)

            # Clean up temporary files
            for temp_file in [video_temp_path, audio_temp_path, temp_output_path, trimmed_audio_path]:
                if os.path.exists(temp_file):
                    try:
                        os.unlink(temp_file)
                    except:
                        pass
            
            logger.info(f"Successfully applied background music to video {video.id}, saved as output_with_bg")
            return True
            
        except Exception as e:
            logger.error(f"Error applying background music to video {video.id}: {str(e)}")
            print(f"Error applying background music: {str(e)}")
            # Clean up temporary files if they exist
            for var_name in ['video_temp_path', 'audio_temp_path', 'temp_output_path', 'trimmed_audio_path']:
                if var_name in locals() and locals()[var_name] and os.path.exists(locals()[var_name]):
                    try:
                        os.unlink(locals()[var_name])
                    except:
                        pass
            return False


    def apply_all_background_music(self, bg_music_queryset):
        """
        Applies multiple background music tracks to the video output in a single operation.
        All tracks are mixed together with proper timing and volume adjustments.
        
        Args:
            bg_music_queryset: QuerySet of BackgroundMusic objects containing audio files and timing information
        
        Returns:
            bool: True if successful, False otherwise
        """
        video = self.video
        
        # Check if the video has an output file
        if not video.output:
            logger.error(f"No output file found for video {video.id}")
            return False
        
        # Check if there are any background music tracks to process
        if not bg_music_queryset.exists():
            logger.info(f"No background music tracks found for video {video.id}")
            return True
        
        try:
            logger.info(f"Applying {bg_music_queryset.count()} background music tracks to video {video.id}")
            
            # Create temporary files for processing
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp_video:
                # Download the video file to temp location
                with default_storage.open(video.output.name, 'rb') as s3_video:
                    tmp_video.write(s3_video.read())
                video_temp_path = tmp_video.name
            
            # Create output temp file
            temp_output_path = tempfile.mktemp(suffix='.mp4')
            
            # Get video duration using ffprobe
            video_duration_cmd = [
                "ffprobe", 
                "-v", "error", 
                "-show_entries", "format=duration", 
                "-of", "default=noprint_wrappers=1:nokey=1", 
                video_temp_path
            ]
            video_duration = float(subprocess.check_output(video_duration_cmd).decode("utf-8").strip())
            
            # Check if the video has an audio track
            has_audio_cmd = [
                "ffprobe",
                "-v", "error",
                "-select_streams", "a",
                "-show_entries", "stream=codec_type",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_temp_path
            ]
            
            has_audio_result = subprocess.run(has_audio_cmd, capture_output=True, text=True)
            has_audio = has_audio_result.stdout.strip() == "audio"
            
            # Process all background music tracks
            audio_tracks = []
            temp_audio_files = []
            filter_complex_parts = []
            
            for idx, bg_music in enumerate(bg_music_queryset):
                if not bg_music.audio_file:
                    logger.warning(f"Skipping background music {bg_music.id} - no audio file")
                    continue
                
                # Download the audio file to temp location
                with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp_audio:
                    with default_storage.open(bg_music.audio_file.name, 'rb') as s3_audio:
                        tmp_audio.write(s3_audio.read())
                    audio_temp_path = tmp_audio.name
                    temp_audio_files.append(audio_temp_path)
                
                # Get audio duration
                audio_duration_cmd = [
                    "ffprobe", 
                    "-v", "error", 
                    "-show_entries", "format=duration", 
                    "-of", "default=noprint_wrappers=1:nokey=1", 
                    audio_temp_path
                ]
                try:
                    audio_duration = float(subprocess.check_output(audio_duration_cmd).decode("utf-8").strip())
                except:
                    audio_duration = 0
                
                # Calculate timing for this track
                start_time = min(bg_music.start_time, video_duration)
                
                if bg_music.end_time <= bg_music.start_time or bg_music.end_time > video_duration:
                    end_time = min(video_duration, start_time + audio_duration)
                else:
                    end_time = min(bg_music.end_time, video_duration)
                
                if end_time <= start_time:
                    end_time = video_duration
                
                duration = end_time - start_time
                
                if duration <= 0:
                    duration = min(audio_duration, video_duration - start_time)
                    end_time = start_time + duration
                    
                    if duration <= 0:
                        start_time = 0
                        duration = min(audio_duration, video_duration)
                        end_time = start_time + duration
                
                # Use volume from bg_music (range 0 to 1)
                volume_level = bg_music.volumn if hasattr(bg_music, 'volumn') and 0 <= bg_music.volumn <= 1 else 0.3
                
                # Print report for this track
                print(f"\nBackground Music Track {idx + 1}:")
                print(f"- Music File: {os.path.basename(bg_music.audio_file.name)}")
                print(f"- Start Time: {start_time:.2f} seconds")
                print(f"- End Time: {end_time:.2f} seconds")
                print(f"- Volume Level: {volume_level:.2f}")
                print(f"- Duration: {duration:.2f} seconds")
                
                # Create trimmed and volume-adjusted version of this track
                trimmed_audio_path = tempfile.mktemp(suffix='.mp3')
                temp_audio_files.append(trimmed_audio_path)
                
                audio_trim_cmd = [
                    "ffmpeg",
                    "-y",
                    "-i", audio_temp_path,
                    "-ss", "0",
                    "-t", str(duration),
                    "-af", f"volume={volume_level}",
                    "-c:a", "mp3",
                    trimmed_audio_path
                ]
                
                subprocess.run(audio_trim_cmd, capture_output=True, check=True)
                
                # Add this track to the filter complex
                audio_tracks.append({
                    'path': trimmed_audio_path,
                    'start_time': start_time,
                    'end_time': end_time,
                    'volume': volume_level,
                    'index': idx + 1  # Start from 1 (0 is reserved for original audio)
                })
                
                # Create filter for this track with proper timing
                filter_complex_parts.append(f"[{idx + 1}:a]adelay={int(start_time*1000)}|{int(start_time*1000)}[a{idx + 1}]")
            
            if not audio_tracks:
                logger.warning(f"No valid audio tracks found for video {video.id}")
                return False
            
            # Prepare the final complex filter
            if has_audio:
                # First, check if we have the original audio file
                original_audio_path = None
                
                if hasattr(video, 'audio_file') and video.audio_file:
                    # Use the original audio file if available
                    print(f"Using original audio file from video.audio_file")
                    with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp_audio:
                        with default_storage.open(video.audio_file.name, 'rb') as s3_audio:
                            tmp_audio.write(s3_audio.read())
                        original_audio_path = tmp_audio.name
                        temp_audio_files.append(original_audio_path)
                else:
                    # Extract original audio from video
                    print(f"Extracting original audio from video")
                    original_audio_path = tempfile.mktemp(suffix='.mp3')
                    temp_audio_files.append(original_audio_path)
                    
                    extract_cmd = [
                        "ffmpeg",
                        "-y",
                        "-i", video_temp_path,
                        "-vn",
                        "-ac", "2",  # Ensure stereo
                        "-ar", "44100",  # Standard sample rate
                        "-c:a", "mp3",
                        "-b:a", "320k",  # Maximum quality
                        original_audio_path
                    ]
                    subprocess.run(extract_cmd, capture_output=True, check=True)
                
                # SIMPLE APPROACH: Keep original at full volume, add background music with reduced volume
                filter_complex_parts_all = []
                
                # Original audio stays at FULL VOLUME - no changes!
                filter_complex_parts_all.append("[0:a]volume=1[orig]")
                
                # Add all background music tracks with delays AND reduced volume
                # Background music is already volume-adjusted during trimming
                filter_complex_parts_all.extend(filter_complex_parts)
                
                # Use amerge to combine tracks without reducing original volume
                # First, we'll layer all the background music together
                if len(audio_tracks) > 1:
                    # Mix all background music together first
                    bg_mix_inputs = [f"[a{i+1}]" for i in range(len(audio_tracks))]
                    bg_mix = f"{';'.join(bg_mix_inputs)}amix=inputs={len(audio_tracks)}:duration=longest[bgmix]"
                    filter_complex_parts_all.append(bg_mix)
                    
                    # Then overlay the mixed background on the original
                    final_mix = "[orig][bgmix]amerge=inputs=2[merged];[merged]pan=stereo|FL<0.5*FL+0.5*FC|FR<0.5*FR+0.5*FC[final]"
                else:
                    # Single background track - directly overlay on original
                    final_mix = f"[orig][a1]amerge=inputs=2[merged];[merged]pan=stereo|FL<0.5*FL+0.5*FC|FR<0.5*FR+0.5*FC[final]"
                
                # Combine all filter parts
                complete_filter = ';'.join(filter_complex_parts_all) + ';' + final_mix
                
                # Create the final command
                ffmpeg_cmd = ["ffmpeg", "-y", "-i", original_audio_path]
                
                # Add all background music inputs
                for track in audio_tracks:
                    ffmpeg_cmd.extend(["-i", track['path']])
                
                mixed_audio_path = tempfile.mktemp(suffix='.mp3')
                temp_audio_files.append(mixed_audio_path)
                
                ffmpeg_cmd.extend([
                    "-filter_complex", complete_filter,
                    "-map", "[final]",
                    "-c:a", "mp3",
                    "-b:a", "320k",  # Maximum quality
                    mixed_audio_path
                ])
                
                print(f"Filter complex: {complete_filter}")
                print(f"Mixing all audio tracks with FULL ORIGINAL VOLUME: {' '.join(ffmpeg_cmd[:6])}...")
                
                subprocess.run(ffmpeg_cmd, capture_output=True, check=True)
                
                # Combine with video using maximum quality settings
                final_cmd = [
                    "ffmpeg",
                    "-y",
                    "-i", video_temp_path,
                    "-i", mixed_audio_path,
                    "-c:v", "copy",
                    "-c:a", "aac",
                    "-b:a", "320k",  # Maximum quality
                    "-ac", "2",
                    "-ar", "44100",
                    "-map", "0:v",
                    "-map", "1:a",
                    "-shortest",
                    temp_output_path
                ]
                
                subprocess.run(final_cmd, capture_output=True, check=True)
                
                # Combine with video
                final_cmd = [
                    "ffmpeg",
                    "-y",
                    "-i", video_temp_path,
                    "-i", mixed_audio_path,
                    "-c:v", "copy",
                    "-c:a", "aac",
                    "-map", "0:v",
                    "-map", "1:a",
                    "-shortest",
                    temp_output_path
                ]
                
                subprocess.run(final_cmd, capture_output=True, check=True)
            else:
                # Video has no audio - create mixed background music directly
                # Create a silent base
                silent_base_path = tempfile.mktemp(suffix='.mp3')
                temp_audio_files.append(silent_base_path)
                
                silence_cmd = [
                    "ffmpeg",
                    "-y",
                    "-f", "lavfi",
                    "-i", f"anullsrc=r=44100:cl=stereo:d={video_duration}",
                    "-c:a", "mp3",
                    silent_base_path
                ]
                subprocess.run(silence_cmd, capture_output=True, check=True)
                
                # Build complex filter for all background music
                filter_complex = ';'.join(filter_complex_parts)
                mix_inputs = ["[0:a]"] + [f"[a{i+1}]" for i in range(len(audio_tracks))]
                filter_complex += f";{';'.join(mix_inputs)}amix=inputs={len(mix_inputs)}:duration=first[final]"
                
                # Create mixed audio
                ffmpeg_cmd = ["ffmpeg", "-y", "-i", silent_base_path]
                
                for track in audio_tracks:
                    ffmpeg_cmd.extend(["-i", track['path']])
                
                ffmpeg_cmd.extend([
                    "-filter_complex", filter_complex,
                    "-map", "[final]",
                    "-c:a", "mp3",
                    tempfile.mktemp(suffix='.mp3')
                ])
                
                mixed_audio_path = ffmpeg_cmd[-1]
                temp_audio_files.append(mixed_audio_path)
                
                subprocess.run(ffmpeg_cmd, capture_output=True, check=True)
                
                # Combine with video
                final_cmd = [
                    "ffmpeg",
                    "-y",
                    "-i", video_temp_path,
                    "-i", mixed_audio_path,
                    "-c:v", "copy",
                    "-c:a", "aac",
                    "-map", "0:v",
                    "-map", "1:a",
                    "-shortest",
                    temp_output_path
                ]
                
                subprocess.run(final_cmd, capture_output=True, check=True)
            
            # Verify the output has audio
            verify_cmd = [
                "ffprobe",
                "-v", "error",
                "-select_streams", "a",
                "-show_entries", "stream=codec_type",
                "-of", "default=noprint_wrappers=1:nokey=1",
                temp_output_path
            ]
            
            verify_result = subprocess.run(verify_cmd, capture_output=True, text=True)
            has_output_audio = verify_result.stdout.strip() == "audio"
            
            print(f"\n- Output video has audio track: {has_output_audio}")
            
            # Update the video output_with_bg file
            filename = f"{os.path.splitext(os.path.basename(video.output.name))[0]}_with_bg.mp4"
            with open(temp_output_path, 'rb') as f:
                video.output_with_bg.save(filename, File(f), save=True)
            
            # Clean up all temporary files
            for temp_file in [video_temp_path, temp_output_path] + temp_audio_files:
                if temp_file and os.path.exists(temp_file):
                    try:
                        os.unlink(temp_file)
                    except:
                        pass
            
            logger.info(f"Successfully applied all background music to video {video.id}")
            return True
            
        except Exception as e:
            logger.error(f"Error applying background music to video {video.id}: {str(e)}")
            print(f"Error applying background music: {str(e)}")
            
            # Clean up temporary files on error
            for temp_file in [video_temp_path, temp_output_path] + temp_audio_files if 'temp_audio_files' in locals() else []:
                if temp_file and os.path.exists(temp_file):
                    try:
                        os.unlink(temp_file)
                    except:
                        pass
            return False


    def apply_all_background_music_watermark(self, bg_music_queryset):
        """
        Applies multiple background music tracks to the watermarked video output in a single operation.
        All tracks are mixed together with proper timing and volume adjustments.
        
        Args:
            bg_music_queryset: QuerySet of BackgroundMusic objects containing audio files and timing information
        
        Returns:
            bool: True if successful, False otherwise
        """
        video = self.video
        
        # Check if the video has an output file
        if not video.output_with_watermark:
            logger.error(f"No watermarked output file found for video {video.id}")
            return False
        
        # Check if there are any background music tracks to process
        if not bg_music_queryset.exists():
            logger.info(f"No background music tracks found for video {video.id}")
            return True
        
        try:
            logger.info(f"Applying {bg_music_queryset.count()} background music tracks to watermarked video {video.id}")
            
            # Create temporary files for processing
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp_video:
                # Download the watermarked video file to temp location
                with default_storage.open(video.output_with_watermark.name, 'rb') as s3_video:
                    tmp_video.write(s3_video.read())
                video_temp_path = tmp_video.name
            
            # Create output temp file
            temp_output_path = tempfile.mktemp(suffix='.mp4')
            
            # Get video duration using ffprobe
            video_duration_cmd = [
                "ffprobe", 
                "-v", "error", 
                "-show_entries", "format=duration", 
                "-of", "default=noprint_wrappers=1:nokey=1", 
                video_temp_path
            ]
            video_duration = float(subprocess.check_output(video_duration_cmd).decode("utf-8").strip())
            
            # Check if the video has an audio track
            has_audio_cmd = [
                "ffprobe",
                "-v", "error",
                "-select_streams", "a",
                "-show_entries", "stream=codec_type",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_temp_path
            ]
            
            has_audio_result = subprocess.run(has_audio_cmd, capture_output=True, text=True)
            has_audio = has_audio_result.stdout.strip() == "audio"
            
            # Process all background music tracks
            audio_tracks = []
            temp_audio_files = []
            filter_complex_parts = []
            
            for idx, bg_music in enumerate(bg_music_queryset):
                if not bg_music.audio_file:
                    logger.warning(f"Skipping background music {bg_music.id} - no audio file")
                    continue
                
                # Download the audio file to temp location
                with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as tmp_audio:
                    with default_storage.open(bg_music.audio_file.name, 'rb') as s3_audio:
                        tmp_audio.write(s3_audio.read())
                    audio_temp_path = tmp_audio.name
                    temp_audio_files.append(audio_temp_path)
                
                # Get audio duration
                audio_duration_cmd = [
                    "ffprobe", 
                    "-v", "error", 
                    "-show_entries", "format=duration", 
                    "-of", "default=noprint_wrappers=1:nokey=1", 
                    audio_temp_path
                ]
                try:
                    audio_duration = float(subprocess.check_output(audio_duration_cmd).decode("utf-8").strip())
                except:
                    audio_duration = 0
                
                # Calculate timing for this track
                start_time = min(bg_music.start_time, video_duration)
                
                if bg_music.end_time <= bg_music.start_time or bg_music.end_time > video_duration:
                    end_time = min(video_duration, start_time + audio_duration)
                else:
                    end_time = min(bg_music.end_time, video_duration)
                
                if end_time <= start_time:
                    end_time = video_duration
                
                duration = end_time - start_time
                
                if duration <= 0:
                    duration = min(audio_duration, video_duration - start_time)
                    end_time = start_time + duration
                    
                    if duration <= 0:
                        start_time = 0
                        duration = min(audio_duration, video_duration)
                        end_time = start_time + duration
                
                # Use volume from bg_music (range 0 to 1)
                volume_level = bg_music.volumn if hasattr(bg_music, 'volumn') and 0 <= bg_music.volumn <= 1 else 0.3
                
                # Print report for this track
                print(f"\nBackground Music Track {idx + 1} (Watermarked):")
                print(f"- Music File: {os.path.basename(bg_music.audio_file.name)}")
                print(f"- Start Time: {start_time:.2f} seconds")
                print(f"- End Time: {end_time:.2f} seconds")
                print(f"- Volume Level: {volume_level:.2f}")
                print(f"- Duration: {duration:.2f} seconds")
                
                # Create trimmed and volume-adjusted version of this track
                trimmed_audio_path = tempfile.mktemp(suffix='.mp3')
                temp_audio_files.append(trimmed_audio_path)
                
                audio_trim_cmd = [
                    "ffmpeg",
                    "-y",
                    "-i", audio_temp_path,
                    "-ss", "0",
                    "-t", str(duration),
                    "-af", f"volume={volume_level}",
                    "-c:a", "mp3",
                    trimmed_audio_path
                ]
                
                subprocess.run(audio_trim_cmd, capture_output=True, check=True)
                
                # Add this track to the filter complex
                audio_tracks.append({
                    'path': trimmed_audio_path,
                    'start_time': start_time,
                    'end_time': end_time,
                    'volume': volume_level,
                    'index': idx + 1  # Start from 1 (0 is reserved for original audio)
                })
                
                # Create filter for this track with proper timing
                filter_complex_parts.append(f"[{idx + 1}:a]adelay={int(start_time*1000)}|{int(start_time*1000)}[a{idx + 1}]")
            
            if not audio_tracks:
                logger.warning(f"No valid audio tracks found for video {video.id}")
                return False
            
            # Prepare the final complex filter
            if has_audio:
                # Extract original audio and reduce its volume during background music
                original_audio_path = tempfile.mktemp(suffix='.mp3')
                temp_audio_files.append(original_audio_path)
                
                extract_cmd = [
                    "ffmpeg",
                    "-y",
                    "-i", video_temp_path,
                    "-vn",
                    "-c:a", "mp3",
                    original_audio_path
                ]
                subprocess.run(extract_cmd, capture_output=True, check=True)
                
                # Create a single filter complex for all audio mixing
                filter_complex = []
                
                # Add volume control for original audio
                volume_sections = []
                for track in audio_tracks:
                    volume_sections.append(f"volume=0.7:enable='between(t,{track['start_time']},{track['end_time']})'")
                
                if volume_sections:
                    filter_complex.append(f"[0:a]{','.join(volume_sections)}[orig]")
                else:
                    filter_complex.append("[0:a]volume=1[orig]")
                
                # Add all background music tracks with delays
                filter_complex.extend(filter_complex_parts)
                
                # Mix all tracks together
                mix_inputs = ["[orig]"] + [f"[a{i+1}]" for i in range(len(audio_tracks))]
                filter_complex.append(f"{';'.join(filter_complex)};{';'.join(mix_inputs)}amix=inputs={len(mix_inputs)}:duration=first[final]")
                
                # Create the final command
                ffmpeg_cmd = ["ffmpeg", "-y", "-i", original_audio_path]
                
                # Add all background music inputs
                for track in audio_tracks:
                    ffmpeg_cmd.extend(["-i", track['path']])
                
                ffmpeg_cmd.extend([
                    "-filter_complex", ';'.join(filter_complex),
                    "-map", "[final]",
                    "-c:a", "mp3",
                    tempfile.mktemp(suffix='.mp3')
                ])
                
                print(f"Mixing all audio tracks for watermarked video: {' '.join(ffmpeg_cmd[:10])}...")  # Print first part of command
                mixed_audio_path = ffmpeg_cmd[-1]
                temp_audio_files.append(mixed_audio_path)
                
                subprocess.run(ffmpeg_cmd, capture_output=True, check=True)
                
                # Combine with video
                final_cmd = [
                    "ffmpeg",
                    "-y",
                    "-i", video_temp_path,
                    "-i", mixed_audio_path,
                    "-c:v", "copy",
                    "-c:a", "aac",
                    "-map", "0:v",
                    "-map", "1:a",
                    "-shortest",
                    temp_output_path
                ]
                
                subprocess.run(final_cmd, capture_output=True, check=True)
            else:
                # Video has no audio - create mixed background music directly
                # Create a silent base
                silent_base_path = tempfile.mktemp(suffix='.mp3')
                temp_audio_files.append(silent_base_path)
                
                silence_cmd = [
                    "ffmpeg",
                    "-y",
                    "-f", "lavfi",
                    "-i", f"anullsrc=r=44100:cl=stereo:d={video_duration}",
                    "-c:a", "mp3",
                    silent_base_path
                ]
                subprocess.run(silence_cmd, capture_output=True, check=True)
                
                # Build complex filter for all background music
                filter_complex = ';'.join(filter_complex_parts)
                mix_inputs = ["[0:a]"] + [f"[a{i+1}]" for i in range(len(audio_tracks))]
                filter_complex += f";{';'.join(mix_inputs)}amix=inputs={len(mix_inputs)}:duration=first[final]"
                
                # Create mixed audio
                ffmpeg_cmd = ["ffmpeg", "-y", "-i", silent_base_path]
                
                for track in audio_tracks:
                    ffmpeg_cmd.extend(["-i", track['path']])
                
                ffmpeg_cmd.extend([
                    "-filter_complex", filter_complex,
                    "-map", "[final]",
                    "-c:a", "mp3",
                    tempfile.mktemp(suffix='.mp3')
                ])
                
                mixed_audio_path = ffmpeg_cmd[-1]
                temp_audio_files.append(mixed_audio_path)
                
                subprocess.run(ffmpeg_cmd, capture_output=True, check=True)
                
                # Combine with video
                final_cmd = [
                    "ffmpeg",
                    "-y",
                    "-i", video_temp_path,
                    "-i", mixed_audio_path,
                    "-c:v", "copy",
                    "-c:a", "aac",
                    "-map", "0:v",
                    "-map", "1:a",
                    "-shortest",
                    temp_output_path
                ]
                
                subprocess.run(final_cmd, capture_output=True, check=True)
            
            # Verify the output has audio
            verify_cmd = [
                "ffprobe",
                "-v", "error",
                "-select_streams", "a",
                "-show_entries", "stream=codec_type",
                "-of", "default=noprint_wrappers=1:nokey=1",
                temp_output_path
            ]
            
            verify_result = subprocess.run(verify_cmd, capture_output=True, text=True)
            has_output_audio = verify_result.stdout.strip() == "audio"
            
            print(f"\n- Watermarked output video has audio track: {has_output_audio}")
            
            # Update the video output_with_bg_watermark file
            filename = f"{os.path.splitext(os.path.basename(video.output.name))[0]}_with_bg_watermark.mp4"
            with open(temp_output_path, 'rb') as f:
                video.output_with_bg_watermark.save(filename, File(f), save=True)
            
            # Clean up all temporary files
            for temp_file in [video_temp_path, temp_output_path] + temp_audio_files:
                if temp_file and os.path.exists(temp_file):
                    try:
                        os.unlink(temp_file)
                    except:
                        pass
            
            logger.info(f"Successfully applied all background music to watermarked video {video.id}")
            return True
            
        except Exception as e:
            logger.error(f"Error applying background music to watermarked video {video.id}: {str(e)}")
            print(f"Error applying background music: {str(e)}")
            
            # Clean up temporary files on error
            for temp_file in [video_temp_path, temp_output_path] + temp_audio_files if 'temp_audio_files' in locals() else []:
                if temp_file and os.path.exists(temp_file):
                    try:
                        os.unlink(temp_file)
                    except:
                        pass
            return False


        
    # def replace_subclip(self, subclip: Subclip):
    #     """
    #     Replace the video file for a specific subclip with a new file and overlay it on the main video
    #     with appropriate subtitles, maintaining the same styling as the main video.
        
    #     Args:
    #         subclip: The Subclip object to replace in the video
            
    #     Returns:
    #         bool: True if successful, False otherwise
    #     """
    #     dimensions = self.video.dimensions
    #     if (dimensions == "16:9"):
    #         width, height = 1920, 1080
    #     elif (dimensions == "9:16"):
    #         width, height = 1080, 1920
    #     elif (dimensions == "1:1"):
    #         width, height = 1080, 1080
    #     elif (dimensions == "4:5"):
    #         width, height = 1080, 1350
    #     else:
    #         width, height = 1920, 1080 
            
    #     try:
    #         if not subclip.video_file:
    #             logger.error(f"No video file exists for subclip {subclip.id}")
    #             return False
            
    #         # Create temporary files for processing
    #         with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_file:
    #             # Download the subclip file from storage
    #             with default_storage.open(subclip.video_file.name, 'rb') as s3_file:
    #                 temp_file.write(s3_file.read())
    #             subclip_video_path = temp_file.name
                
    #         with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_file:
    #             # Download the main video file from storage
    #             with default_storage.open(self.video.output.name, 'rb') as s3_file:
    #                 temp_file.write(s3_file.read())
    #             main_video_path = temp_file.name
                
    #         # Create temp directory for intermediate files
    #         with tempfile.TemporaryDirectory() as temp_dir:
    #             output_path = os.path.join(temp_dir, "replaced_output.mp4")
                
    #             # Check if NVIDIA GPU is available for encoding
    #             try:
    #                 nvidia_info = subprocess.run(["nvidia-smi"], capture_output=True, check=False, text=True)
    #                 use_gpu = nvidia_info.returncode == 0
                    
    #                 if use_gpu:
    #                     # Test if h264_nvenc is available and check supported presets
    #                     preset_test = subprocess.run(
    #                         ["ffmpeg", "-h", "encoder=h264_nvenc"],
    #                         capture_output=True, check=False, text=True
    #                     )
                        
    #                     if "p4" in preset_test.stdout:
    #                         nvenc_preset = "p4"
    #                     elif "p7" in preset_test.stdout:
    #                         nvenc_preset = "p7"
    #                     elif "fast" in preset_test.stdout:
    #                         nvenc_preset = "fast"
    #                     else:
    #                         nvenc_preset = "default"
    #                     print(f"Using GPU acceleration with preset: {nvenc_preset}")
    #                 else:
    #                     print("Using CPU encoding")
    #                     nvenc_preset = None
    #             except Exception as e:
    #                 use_gpu = False
    #                 nvenc_preset = None
    #                 print(f"Error checking GPU, falling back to CPU encoding: {str(e)}")
                    
    #             # Set video codec based on GPU availability
    #             video_codec = "h264_nvenc" if use_gpu else "libx264"
    #             video_options = ["-preset", nvenc_preset if use_gpu else "medium"]
                
    #             # Determine timing for subclip overlay
    #             start_time = subclip.start_time
    #             end_time = subclip.end_time + 0.02
    #             duration = end_time - start_time
                
    #             # Get the actual duration of the subclip video file
    #             probe_cmd = [
    #                 "ffprobe", "-v", "error",
    #                 "-show_entries", "format=duration",
    #                 "-of", "default=noprint_wrappers=1:nokey=1",
    #                 subclip_video_path
    #             ]
    #             try:
    #                 actual_subclip_duration = float(subprocess.check_output(probe_cmd).decode("utf-8").strip())
    #                 print(f"Actual subclip duration: {actual_subclip_duration}s, target duration: {duration}s")
    #             except Exception as e:
    #                 logger.warning(f"Could not determine subclip duration: {str(e)}")
    #                 actual_subclip_duration = duration
                    
    #             # Process the subclip to match required dimensions with blurred background
    #             processed_subclip_path = os.path.join(temp_dir, "processed_subclip.mp4")
                
    #             # If subclip needs to be stretched to match the timing
    #             speed_factor = actual_subclip_duration / duration if actual_subclip_duration < duration else 1.0
    #             if speed_factor != 1.0:
    #                 print(f"Adjusting subclip speed by factor: {speed_factor}")
                    
    #             # Process the subclip with blurred background approach (same as in _process_clip)
    #             normalize_filters = [
    #                 # Split the video into two streams
    #                 f"split=2[original][blurred];",
                    
    #                 # Scale and blur one stream to fill the frame
    #                 f"[blurred]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},boxblur=luma_radius=min(h\\,w)/20:luma_power=1[blurred];",
                    
    #                 # Scale original with precise aspect ratio preservation
    #                 f"[original]scale=iw*min({width}/iw\\,{height}/ih):ih*min({width}/iw\\,{height}/ih)[original];",
    #             ]
                
    #             # Add speed adjustment if needed
    #             if speed_factor != 1.0:
    #                 normalize_filters.append(f"[original]setpts={speed_factor}*PTS[original];")
                    
    #             # Complete the filter chain
    #             normalize_filters.extend([
    #                 # Overlay original on blurred background with precise centering
    #                 f"[blurred][original]overlay=(W-w)/2:(H-h)/2",
                    
    #                 # Ensure proper format
    #                 ",format=yuv420p",
                    
    #                 # Apply framerate correction
    #                 f",fps={self.framerate}"
    #             ])
                
    #             # Join all filters into a single string
    #             filter_string = "".join(normalize_filters)
                
    #             # Process the subclip
    #             subclip_cmd = [
    #                 "ffmpeg", "-y",
    #                 "-i", subclip_video_path,
    #                 "-vf", filter_string,
    #                 "-c:v", video_codec,
    #             ]
    #             subclip_cmd.extend(video_options)
    #             subclip_cmd.extend([
    #                 "-pix_fmt", "yuv420p",
    #                 "-r", str(self.framerate),
    #                 "-t", str(duration),  # Ensure exact timing
    #                 processed_subclip_path
    #             ])
                
    #             print(f"Processing subclip with command: {' '.join(subclip_cmd)}")
    #             subprocess.run(subclip_cmd, check=True)
                
    #             # Create subtitle text for overlay
    #             # Extract the main clip text for subtitles
    #             clip_text = subclip.clip.text if subclip.clip.text else ""
                
    #             # Determine if we're working with vertical video (9:16 aspect ratio)
    #             is_vertical_video = self.video.dimensions == "9:16"
                
    #             # Calculate font size based on video dimensions
    #             if self.video.font_size > 0:
    #                 if is_vertical_video:
    #                     font_size = 52  # For vertical video
    #                 else:
    #                     font_size = self.video.font_size * 2
    #             else:
    #                 font_size = int(height / self.font_size_ratio)
                    
    #             # Adjust text position based on aspect ratio
    #             if is_vertical_video:
    #                 text_y_position = int(height * 0.78)  # Position at 78% of height for vertical
    #             else:
    #                 text_y_position = int(height * 0.85)  # Lower third for horizontal
                    
    #             # Calculate max subtitle width
    #             max_subtitle_width = int(width * (0.85 if is_vertical_video else 0.8))
                
    #             # Wrap text appropriately
    #             text_lines = self._wrap_text(clip_text, max_subtitle_width)
                
    #             # Calculate vertical spacing between lines (1.2x font size)
    #             line_spacing = int(font_size * 1.2)
    #             num_lines = len(text_lines)
                
    #             # Adjust starting y-position based on aspect ratio and number of lines
    #             if is_vertical_video:
    #                 start_y = text_y_position - (line_spacing * num_lines) + 60  # Added offset to move up
    #             else:
    #                 if num_lines > 3:
    #                     start_y = text_y_position - (line_spacing * (num_lines - 2))
    #                 else:
    #                     start_y = text_y_position - (line_spacing * (num_lines - 1) // 2)
                        
    #             # Calculate proper box padding based on font size and video dimensions
    #             padding_factor = self.subtitle_box_padding
    #             horizontal_padding = font_size * (padding_factor * 0.3 if is_vertical_video else padding_factor * 0.7)
    #             vertical_padding = font_size * padding_factor
                
    #             # Prepare overlay commands
    #             overlay_filter = []
                
    #             # Add "enable" parameter to show the overlay only during the subclip timing
    #             if is_vertical_video:
    #                 # For vertical videos, create individual boxes for each line
    #                 box_filters = []
    #                 text_filters = []
                    
    #                 for line_idx, line_text in enumerate(text_lines):
    #                     if not line_text.strip():
    #                         continue  # Skip empty lines
                            
    #                     # Calculate y position for this specific line
    #                     line_y = start_y + (line_idx * line_spacing) - (vertical_padding * 0.2)
                        
    #                     # Calculate individual box dimensions for this line
    #                     avg_char_width = font_size * 0.54
    #                     line_text_width = len(line_text) * avg_char_width
    #                     line_box_width = int(line_text_width + (horizontal_padding*1.3))
    #                     line_box_height = int(line_spacing + (vertical_padding * 0.9))
                        
    #                     # Ensure minimum width for short texts
    #                     min_width = int(width * 0.15)
    #                     line_box_width = max(line_box_width, min_width)
                        
    #                     # Cap maximum width
    #                     max_width = int(width * 0.9)
    #                     line_box_width = min(line_box_width, max_width)
                        
    #                     # Calculate box position for this line (centered)
    #                     line_box_x = int((width - line_box_width) / 2)
    #                     line_box_y = line_y - (vertical_padding * 0.8)
                        
    #                     # Create drawbox filter for subtitle background
    #                     if self.box_roundness > 0:
    #                         # For rounded boxes with PIL, we'll use standard boxes in the direct filter approach
    #                         box_filters.append(
    #                             f"drawbox=x={line_box_x}:y={line_box_y}:"
    #                             f"w={line_box_width}:h={line_box_height}:"
    #                             f"color={self.subtitle_box_color}@1.0:t=fill"
    #                         )
    #                     else:
    #                         box_filters.append(
    #                             f"drawbox=x={line_box_x}:y={line_box_y}:"
    #                             f"w={line_box_width}:h={line_box_height}:"
    #                             f"color={self.subtitle_box_color}@1.0:t=fill"
    #                         )
                        
    #                     # Calculate y position for text
    #                     if is_vertical_video:
    #                         line_y = start_y + (line_idx * (line_spacing * 0.95))
    #                     else:
    #                         line_y = start_y + (line_idx * line_spacing)
                            
    #                     # Escape special characters in text
    #                     escaped_text = (
    #                         line_text.replace("'", "\\'")
    #                         .replace(":", "\\:")
    #                         .replace(",", "\\,")
    #                     )
                        
    #                     # Add font configuration
    #                     if is_vertical_video:
    #                         adjusted_font_size = int(font_size * 1.1)
    #                         font_config = f"fontsize={adjusted_font_size}:fontcolor={self.font_color}"
    #                     else:
    #                         font_config = f"fontsize={font_size}:fontcolor={self.font_color}"
                            
    #                     # Add font file if available
    #                     if self.font_path and os.path.exists(self.font_path):
    #                         font_path_escaped = self.font_path.replace("\\", "\\\\").replace(":", "\\:")
    #                         font_config += f":fontfile='{font_path_escaped}'"
                            
    #                     # Add drawtext filter for this line
    #                     text_filters.append(
    #                         f"drawtext=text='{escaped_text}':{font_config}:"
    #                         f"x=(w-tw)/2:y={line_y}"
    #                     )
                    
    #                 # Combine all filters
    #                 all_filters = box_filters + text_filters
    #                 subtitle_filter = ",".join(all_filters)
                    
    #             else:
    #                 # For non-vertical videos, use a single box for all lines
    #                 longest_line = max(text_lines, key=len) if text_lines else ""
                    
    #                 if num_lines > 0:
    #                     # Calculate box height based on number of lines and padding
    #                     box_height = (num_lines * line_spacing) + (vertical_padding * 1.1)
                        
    #                     # Calculate width
    #                     avg_char_width = font_size * (0.44 if self.video.dimensions == "16:9" else 0.5)
    #                     estimated_text_width = len(longest_line) * avg_char_width
    #                     box_width = int(estimated_text_width + horizontal_padding)
                        
    #                     # Ensure minimum width for short texts
    #                     min_width = int(width * 0.15)
    #                     box_width = max(box_width, min_width)
                        
    #                     # Cap maximum width
    #                     max_width = int(width * 0.8)
    #                     box_width = min(box_width, max_width)
                        
    #                     # Calculate box position (centered)
    #                     box_x = int((width - box_width) / 2)
    #                     box_y = start_y - (vertical_padding - (vertical_padding*0.1))
                        
    #                     # Create drawbox filter for subtitle background
    #                     subtitle_filter = f"drawbox=x={box_x}:y={box_y}:w={box_width}:h={box_height}:"
    #                     subtitle_filter += f"color={self.subtitle_box_color}@1.0:t=fill"
                        
    #                     # Add text lines
    #                     for line_idx, line_text in enumerate(text_lines):
    #                         line_y = start_y + (line_idx * line_spacing)
                            
    #                         # Escape special characters in text
    #                         escaped_text = (
    #                             line_text.replace("'", "\\'")
    #                             .replace(":", "\\:")
    #                             .replace(",", "\\,")
    #                         )
                            
    #                         # Add font configuration
    #                         font_config = f"fontsize={font_size}:fontcolor={self.font_color}"
                            
    #                         # Add font file if available
    #                         if self.font_path and os.path.exists(self.font_path):
    #                             font_path_escaped = self.font_path.replace("\\", "\\\\").replace(":", "\\:")
    #                             font_config += f":fontfile='{font_path_escaped}'"
                                
    #                         # Add drawtext filter for this line
    #                         subtitle_filter += f",drawtext=text='{escaped_text}':{font_config}:x=(w-tw)/2:y={line_y}"
    #                 else:
    #                     subtitle_filter = "null"  # No text to display
                    
    #             # Create an overlay segment map based on subclip timing
    #             # The trick is to create a filter that replaces a segment of the main video with the subclip
    #             overlay_cmd = [
    #                 "ffmpeg", "-y",
    #                 "-i", main_video_path,           # Main video input
    #                 "-i", processed_subclip_path,    # Processed subclip input
    #                 "-filter_complex",
    #                 # Trim main video into 3 segments: before, during, and after the subclip
    #                 f"[0:v]trim=end={start_time},setpts=PTS-STARTPTS[before];"+
    #                 f"[0:v]trim=start={end_time},setpts=PTS-STARTPTS[after];"+
    #                 # Process subclip with subtitles
    #                 f"[1:v]{subtitle_filter}[subclipwithtext];"+
    #                 # Concatenate the segments
    #                 f"[before][subclipwithtext][after]concat=n=3:v=1:a=0[v]",
    #                 # Map the processed video stream
    #                 "-map", "[v]",
    #                 # Copy audio from main video
    #                 "-map", "0:a?",
    #                 "-c:v", video_codec,
    #             ]
    #             overlay_cmd.extend(video_options)
    #             overlay_cmd.extend([
    #                 "-c:a", "copy",
    #                 output_path
    #             ])
                
    #             print(f"Replacing subclip with command: {' '.join(overlay_cmd)}")
    #             subprocess.run(overlay_cmd, check=True)
                
    #             # Verify the final video
    #             if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
    #                 # Save the new video to the model
    #                 with open(output_path, 'rb') as output_file:
    #                     output_filename = f"video_{self.video.id}_updated_{int(time.time())}.mp4"
    #                     self.video.output.save(output_filename, File(output_file), save=True)
    #                 print(f"Successfully replaced subclip {subclip.id} in video {self.video.id}")
    #                 return True
    #             else:
    #                 raise Exception(f"Output file not created or empty: {output_path}")

    #         # Clean up temp files
    #         for path in [subclip_video_path, main_video_path]:
    #             if os.path.exists(path):
    #                 os.unlink(path)
                    
    #         return True
            
    #     except Exception as e:
    #         logger.error(f"Error replacing subclip {subclip.id}: {str(e)}")
    #         # Attempt to clean up temp files if they exist
    #         for var in ['subclip_video_path', 'main_video_path']:
    #             if var in locals() and locals()[var] and os.path.exists(locals()[var]):
    #                 try:
    #                     os.unlink(locals()[var])
    #                 except:
    #                     pass
    #         return False

    def replace_subclip(self, subclip: Subclip):
        """
        Replace the video file for a specific subclip with a new file and overlay it on the main video
        with appropriate subtitles, maintaining the same styling as the main video.
        
        Args:
            subclip: The Subclip object to replace in the video
            
        Returns:
            bool: True if successful, False otherwise
        """
        dimensions = self.video.dimensions
        if (dimensions == "16:9"):
            width, height = 1920, 1080
        elif (dimensions == "9:16"):
            width, height = 1080, 1920
        elif (dimensions == "1:1"):
            width, height = 1080, 1080
        elif (dimensions == "4:5"):
            width, height = 1080, 1350
        else:
            width, height = 1920, 1080 
            
        try:
            if not subclip.video_file:
                logger.error(f"No video file exists for subclip {subclip.id}")
                return False
            
            # Create temporary files for processing
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_file:
                # Download the subclip file from storage
                with default_storage.open(subclip.video_file.name, 'rb') as s3_file:
                    temp_file.write(s3_file.read())
                subclip_video_path = temp_file.name
                
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_file:
                # Download the main video file from storage
                with default_storage.open(self.video.output.name, 'rb') as s3_file:
                    temp_file.write(s3_file.read())
                main_video_path = temp_file.name
                
            # Create temp directory for intermediate files
            with tempfile.TemporaryDirectory() as temp_dir:
                output_path = os.path.join(temp_dir, "replaced_output.mp4")
                
                # Check if NVIDIA GPU is available for encoding
                try:
                    nvidia_info = subprocess.run(["nvidia-smi"], capture_output=True, check=False, text=True)
                    use_gpu = nvidia_info.returncode == 0
                    
                    if use_gpu:
                        # Test if h264_nvenc is available and check supported presets
                        preset_test = subprocess.run(
                            ["ffmpeg", "-h", "encoder=h264_nvenc"],
                            capture_output=True, check=False, text=True
                        )
                        
                        if "p4" in preset_test.stdout:
                            nvenc_preset = "p4"
                        elif "p7" in preset_test.stdout:
                            nvenc_preset = "p7"
                        elif "fast" in preset_test.stdout:
                            nvenc_preset = "fast"
                        else:
                            nvenc_preset = "default"
                        print(f"Using GPU acceleration with preset: {nvenc_preset}")
                    else:
                        print("Using CPU encoding")
                        nvenc_preset = None
                except Exception as e:
                    use_gpu = False
                    nvenc_preset = None
                    print(f"Error checking GPU, falling back to CPU encoding: {str(e)}")
                    
                # Set video codec based on GPU availability
                video_codec = "h264_nvenc" if use_gpu else "libx264"
                video_options = ["-preset", nvenc_preset if use_gpu else "medium"]
                
                # Determine timing for subclip overlay
                start_time = subclip.start_time
                end_time = subclip.end_time + 0.02
                duration = end_time - start_time
                
                # Get the actual duration of the subclip video file
                probe_cmd = [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    subclip_video_path
                ]
                try:
                    actual_subclip_duration = float(subprocess.check_output(probe_cmd).decode("utf-8").strip())
                    print(f"Actual subclip duration: {actual_subclip_duration}s, target duration: {duration}s")
                except Exception as e:
                    logger.warning(f"Could not determine subclip duration: {str(e)}")
                    actual_subclip_duration = duration
                    
                # Process the subclip to match required dimensions with blurred background
                processed_subclip_path = os.path.join(temp_dir, "processed_subclip.mp4")
                
                # If subclip needs to be stretched to match the timing
                speed_factor = actual_subclip_duration / duration if actual_subclip_duration < duration else 1.0
                if speed_factor != 1.0:
                    print(f"Adjusting subclip speed by factor: {speed_factor}")
                    
                # Process the subclip with blurred background approach (same as in _process_clip)
                normalize_filters = [
                    # Split the video into two streams
                    f"split=2[original][blurred];",
                    
                    # Scale and blur one stream to fill the frame
                    f"[blurred]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},boxblur=luma_radius=min(h\\,w)/20:luma_power=1[blurred];",
                    
                    # Scale original with precise aspect ratio preservation
                    f"[original]scale=iw*min({width}/iw\\,{height}/ih):ih*min({width}/iw\\,{height}/ih)[original];",
                ]
                
                # Add speed adjustment if needed
                if speed_factor != 1.0:
                    normalize_filters.append(f"[original]setpts={speed_factor}*PTS[original];")
                    
                # Complete the filter chain
                normalize_filters.extend([
                    # Overlay original on blurred background with precise centering
                    f"[blurred][original]overlay=(W-w)/2:(H-h)/2",
                    
                    # Ensure proper format
                    ",format=yuv420p",
                    
                    # Apply framerate correction
                    f",fps={self.framerate}"
                ])
                
                # Join all filters into a single string
                filter_string = "".join(normalize_filters)
                
                # Process the subclip
                subclip_cmd = [
                    "ffmpeg", "-y",
                    "-i", subclip_video_path,
                    "-vf", filter_string,
                    "-c:v", video_codec,
                ]
                subclip_cmd.extend(video_options)
                subclip_cmd.extend([
                    "-pix_fmt", "yuv420p",
                    "-r", str(self.framerate),
                    "-t", str(duration),  # Ensure exact timing
                    processed_subclip_path
                ])
                
                print(f"Processing subclip with command: {' '.join(subclip_cmd)}")
                subprocess.run(subclip_cmd, check=True)
                
                # Create subtitle text for overlay
                # Extract the main clip text for subtitles
                clip_text = subclip.clip.text if subclip.clip.text else ""
                
                # Determine if we're working with vertical video (9:16 aspect ratio)
                is_vertical_video = self.video.dimensions == "9:16"
                
                # Calculate font size based on video dimensions
                if self.video.font_size > 0:
                    if is_vertical_video:
                        font_size = 52  # For vertical video
                    else:
                        font_size = self.video.font_size * 2
                else:
                    font_size = int(height / self.font_size_ratio)
                    
                # Adjust text position based on aspect ratio
                if is_vertical_video:
                    text_y_position = int(height * 0.78)  # Position at 78% of height for vertical
                else:
                    text_y_position = int(height * 0.85)  # Lower third for horizontal
                    
                # Calculate max subtitle width
                max_subtitle_width = int(width * (0.85 if is_vertical_video else 0.8))
                
                # Wrap text appropriately
                text_lines = self._wrap_text(clip_text, max_subtitle_width)
                
                # Calculate vertical spacing between lines (1.2x font size)
                line_spacing = int(font_size * 1.2)
                num_lines = len(text_lines)
                
                # Adjust starting y-position based on aspect ratio and number of lines
                if is_vertical_video:
                    start_y = text_y_position - (line_spacing * num_lines) + 60  # Added offset to move up
                else:
                    if num_lines > 3:
                        start_y = text_y_position - (line_spacing * (num_lines - 2))
                    else:
                        start_y = text_y_position - (line_spacing * (num_lines - 1) // 2)
                        
                # Calculate proper box padding based on font size and video dimensions
                padding_factor = self.subtitle_box_padding
                horizontal_padding = font_size * (padding_factor * 0.3 if is_vertical_video else padding_factor * 0.7)
                vertical_padding = font_size * padding_factor
                
                # Initialize PNG overlays list if it doesn't exist already
                if not hasattr(self, '_png_overlays'):
                    self._png_overlays = []
                    
                # Process subtitles with rounded corners support
                if is_vertical_video:
                    # For vertical videos, create individual boxes for each line
                    box_filters = []
                    text_filters = []
                    png_inputs = []
                    png_overlays = []
                    
                    for line_idx, line_text in enumerate(text_lines):
                        if not line_text.strip():
                            continue  # Skip empty lines
                            
                        # Calculate y position for this specific line
                        line_y = start_y + (line_idx * line_spacing) - (vertical_padding * 0.2)
                        
                        # Calculate individual box dimensions for this line
                        avg_char_width = font_size * 0.54
                        line_text_width = len(line_text) * avg_char_width
                        line_box_width = int(line_text_width + (horizontal_padding*1.3))
                        line_box_height = int(line_spacing + (vertical_padding * 0.9))
                        
                        # Ensure minimum width for short texts
                        min_width = int(width * 0.15)
                        line_box_width = max(line_box_width, min_width)
                        
                        # Cap maximum width
                        max_width = int(width * 0.9)
                        line_box_width = min(line_box_width, max_width)
                        
                        # Calculate box position for this line (centered)
                        line_box_x = int((width - line_box_width) / 2)
                        line_box_y = line_y - (vertical_padding * 0.8)
                        
                        # If we have a box_roundness value, create a rounded box as PNG
                        if self.box_roundness > 0:
                            # Use larger radius for vertical videos (more rounded corners)
                            radius_percentage = min(self.box_roundness / 100, 0.5)  # Max 50% of smaller dimension
                            radius = int(min(line_box_width, line_box_height) * radius_percentage)
                            
                            # Create a temp PNG file for this line's rounded box
                            rounded_box_path = os.path.join(temp_dir, f"rounded_box_line_{line_idx}.png")
                            
                            try:
                                from PIL import Image, ImageDraw
                                
                                # Create a new RGBA image with transparent background
                                img = Image.new('RGBA', (int(line_box_width), int(line_box_height)), (0, 0, 0, 0))
                                draw = ImageDraw.Draw(img)
                                
                                # Convert hex color to RGBA
                                color = self.subtitle_box_color
                                if color.startswith('#'):
                                    color = color[1:]
                                r = int(color[0:2], 16)
                                g = int(color[2:4], 16)
                                b = int(color[4:6], 16)
                                a = 255  # Fully opaque
                                
                                # Draw rounded rectangle with anti-aliasing
                                draw.rounded_rectangle(
                                    [(0, 0), (int(line_box_width) - 1, int(line_box_height) - 1)],
                                    radius=radius,
                                    fill=(r, g, b, a)
                                )
                                
                                # Save the image with maximum quality
                                img.save(rounded_box_path, 'PNG')
                                
                                # Add to list of PNG inputs
                                png_inputs.append(rounded_box_path)
                                png_overlays.append({
                                    'path': rounded_box_path,
                                    'x': line_box_x,
                                    'y': line_box_y
                                })
                                
                                print(f"Created rounded box for line {line_idx} with radius {radius}px")
                            except Exception as e:
                                print(f"Error creating rounded box for line {line_idx}, falling back to standard box: {str(e)}")
                                box_filters.append(
                                    f"drawbox=x={line_box_x}:y={line_box_y}:"
                                    f"w={line_box_width}:h={line_box_height}:"
                                    f"color={self.subtitle_box_color}@1.0:t=fill"
                                )
                        else:
                            box_filters.append(
                                f"drawbox=x={line_box_x}:y={line_box_y}:"
                                f"w={line_box_width}:h={line_box_height}:"
                                f"color={self.subtitle_box_color}@1.0:t=fill"
                            )
                        
                        # Calculate y position for text
                        line_y = start_y + (line_idx * (line_spacing * 0.95)) if is_vertical_video else start_y + (line_idx * line_spacing)
                            
                        # Escape special characters in text
                        escaped_text = (
                            line_text.replace("'", "\\'")
                            .replace(":", "\\:")
                            .replace(",", "\\,")
                        )
                        
                        # Add font configuration
                        adjusted_font_size = int(font_size * 1.1) if is_vertical_video else font_size
                        font_config = f"fontsize={adjusted_font_size}:fontcolor={self.font_color}"
                        
                        # Add font file if available
                        if self.font_path and os.path.exists(self.font_path):
                            font_path_escaped = self.font_path.replace("\\", "\\\\").replace(":", "\\:")
                            font_config += f":fontfile='{font_path_escaped}'"
                            
                        # Add drawtext filter for this line
                        text_filters.append(
                            f"drawtext=text='{escaped_text}':{font_config}:"
                            f"x=(w-tw)/2:y={line_y}"
                        )
                    
                    # Combine all filters
                    all_filters = box_filters + text_filters
                    subtitle_filter = ",".join(all_filters)
                    
                else:
                    # For non-vertical videos, use a single box for all lines
                    longest_line = max(text_lines, key=len) if text_lines else ""
                    png_inputs = []
                    png_overlays = []
                    
                    if num_lines > 0:
                        # Calculate box height based on number of lines and padding
                        box_height = (num_lines * line_spacing) + (vertical_padding * 1.1)
                        
                        # Calculate width
                        avg_char_width = font_size * (0.44 if self.video.dimensions == "16:9" else 0.5)
                        estimated_text_width = len(longest_line) * avg_char_width
                        box_width = int(estimated_text_width + horizontal_padding)
                        
                        # Ensure minimum width for short texts
                        min_width = int(width * 0.15)
                        box_width = max(box_width, min_width)
                        
                        # Cap maximum width
                        max_width = int(width * 0.8)
                        box_width = min(box_width, max_width)
                        
                        # Calculate box position (centered)
                        box_x = int((width - box_width) / 2)
                        box_y = start_y - (vertical_padding - (vertical_padding*0.1))
                        
                        # If we have a box_roundness value, create a rounded box as PNG
                        if self.box_roundness > 0:
                            # Calculate appropriate radius based on box_roundness
                            radius_percentage = self.box_roundness / 100  # Convert percentage to decimal
                            radius = int(min(box_width, box_height) * radius_percentage)
                            
                            # Create a temp PNG file for the rounded box
                            rounded_box_path = os.path.join(temp_dir, "rounded_box.png")
                            
                            try:
                                from PIL import Image, ImageDraw
                                
                                # Create a new RGBA image with transparent background
                                img = Image.new('RGBA', (int(box_width), int(box_height)), (0, 0, 0, 0))
                                draw = ImageDraw.Draw(img)
                                
                                # Convert hex color to RGBA
                                color = self.subtitle_box_color
                                if color.startswith('#'):
                                    color = color[1:]
                                r = int(color[0:2], 16)
                                g = int(color[2:4], 16)
                                b = int(color[4:6], 16)
                                a = 255  # Fully opaque
                                
                                # Draw rounded rectangle with anti-aliasing
                                draw.rounded_rectangle(
                                    [(0, 0), (int(box_width) - 1, int(box_height) - 1)],
                                    radius=radius,
                                    fill=(r, g, b, a)
                                )
                                
                                # Save the image with maximum quality
                                img.save(rounded_box_path, 'PNG')
                                
                                # Add to list of PNG inputs
                                png_inputs.append(rounded_box_path)
                                png_overlays.append({
                                    'path': rounded_box_path,
                                    'x': box_x,
                                    'y': box_y
                                })
                                
                                print(f"Successfully created rounded box with radius {radius}px")
                                
                                # Initialize subtitle_filter with text filters only
                                subtitle_filter = ""
                            except Exception as e:
                                print(f"Error creating rounded box, falling back to standard box: {str(e)}")
                                subtitle_filter = f"drawbox=x={box_x}:y={box_y}:w={box_width}:h={box_height}:"
                                subtitle_filter += f"color={self.subtitle_box_color}@1.0:t=fill"
                        else:
                            # Standard box without rounded corners
                            subtitle_filter = f"drawbox=x={box_x}:y={box_y}:w={box_width}:h={box_height}:"
                            subtitle_filter += f"color={self.subtitle_box_color}@1.0:t=fill"
                        
                        # Add text lines
                        for line_idx, line_text in enumerate(text_lines):
                            line_y = start_y + (line_idx * line_spacing)
                            
                            # Escape special characters in text
                            escaped_text = (
                                line_text.replace("'", "\\'")
                                .replace(":", "\\:")
                                .replace(",", "\\,")
                            )
                            
                            # Add font configuration
                            font_config = f"fontsize={font_size}:fontcolor={self.font_color}"
                            
                            # Add font file if available
                            if self.font_path and os.path.exists(self.font_path):
                                font_path_escaped = self.font_path.replace("\\", "\\\\").replace(":", "\\:")
                                font_config += f":fontfile='{font_path_escaped}'"
                                
                            # Add drawtext filter for this line
                            if subtitle_filter:
                                # If we already have a box filter, append text
                                subtitle_filter += f",drawtext=text='{escaped_text}':{font_config}:x=(w-tw)/2:y={line_y}"
                            else:
                                # Otherwise, just start with the text
                                if line_idx == 0:
                                    subtitle_filter = f"drawtext=text='{escaped_text}':{font_config}:x=(w-tw)/2:y={line_y}"
                                else:
                                    subtitle_filter += f",drawtext=text='{escaped_text}':{font_config}:x=(w-tw)/2:y={line_y}"
                    else:
                        subtitle_filter = "null"  # No text to display
                
                # Create filter complex command based on whether we have PNG overlay boxes
                if png_overlays:
                    # Process the subclip with subtitles first
                    with_text_path = os.path.join(temp_dir, "with_text.mp4")
                    
                    # Add text only (not boxes since we'll overlay the PNGs)
                    text_only_filter = ""
                    for line_idx, line_text in enumerate(text_lines):
                        if not line_text.strip():
                            continue
                            
                        # Calculate line y position
                        if is_vertical_video:
                            line_y = start_y + (line_idx * (line_spacing * 0.95))
                        else:
                            line_y = start_y + (line_idx * line_spacing)
                        
                        # Escape special characters in text
                        escaped_text = (
                            line_text.replace("'", "\\'")
                            .replace(":", "\\:")
                            .replace(",", "\\,")
                        )
                        
                        # Add font configuration
                        if is_vertical_video:
                            adjusted_font_size = int(font_size * 1.1)
                            font_config = f"fontsize={adjusted_font_size}:fontcolor={self.font_color}"
                        else:
                            font_config = f"fontsize={font_size}:fontcolor={self.font_color}"
                        
                        # Add font file if available
                        if self.font_path and os.path.exists(self.font_path):
                            font_path_escaped = self.font_path.replace("\\", "\\\\").replace(":", "\\:")
                            font_config += f":fontfile='{font_path_escaped}'"
                        
                        # Add drawtext filter
                        if text_only_filter:
                            text_only_filter += f",drawtext=text='{escaped_text}':{font_config}:x=(w-tw)/2:y={line_y}"
                        else:
                            text_only_filter = f"drawtext=text='{escaped_text}':{font_config}:x=(w-tw)/2:y={line_y}"
                    
                    # If we have no text, use null filter
                    if not text_only_filter:
                        text_only_filter = "null"
                    
                    # First, add text to the subclip
                    subclip_with_text_cmd = [
                        "ffmpeg", "-y",
                        "-i", processed_subclip_path,
                        "-vf", text_only_filter,
                        "-c:v", video_codec,
                    ]
                    subclip_with_text_cmd.extend(video_options)
                    subclip_with_text_cmd.extend([
                        "-pix_fmt", "yuv420p",
                        "-r", str(self.framerate),
                        with_text_path
                    ])
                    
                    print(f"Adding text to subclip: {' '.join(subclip_with_text_cmd)}")
                    subprocess.run(subclip_with_text_cmd, check=True)
                    
                    # Now build a complex filter chain with PNG box overlays
                    overlay_chain_cmd = ["ffmpeg", "-y", "-i", with_text_path]
                    
                    # Add PNG inputs
                    for png_path in png_inputs:
                        overlay_chain_cmd.extend(["-i", png_path])
                    
                    # Start building the filter chain
                    filter_chain = []
                    input_label = "[0:v]"
                    
                    # Add each PNG overlay
                    for i, overlay in enumerate(png_overlays):
                        output_label = f"[v{i}]" if i < len(png_overlays) - 1 else "[vout]"
                        overlay_filter = f"{input_label}[{i+1}:v]overlay={overlay['x']}:{overlay['y']}:format=rgb{output_label}"
                        filter_chain.append(overlay_filter)
                        input_label = output_label
                    
                    # Build the final filter complex
                    overlay_chain_cmd.extend([
                        "-filter_complex", ";".join(filter_chain),
                        "-map", "[vout]",
                        "-c:v", video_codec,
                    ])
                    overlay_chain_cmd.extend(video_options)
                    overlay_chain_cmd.extend([
                        "-pix_fmt", "yuv420p",
                        "-r", str(self.framerate),
                        os.path.join(temp_dir, "subclip_with_overlays.mp4")
                    ])
                    
                    print(f"Adding rounded box overlays: {' '.join(overlay_chain_cmd)}")
                    subprocess.run(overlay_chain_cmd, check=True)
                    
                    # Update processed_subclip_path to point to the version with text and rounded boxes
                    processed_subclip_path = os.path.join(temp_dir, "subclip_with_overlays.mp4")
                    
                    # Now create the main overlay command without filters (since we already applied them)
                    overlay_cmd = [
                        "ffmpeg", "-y",
                        "-i", main_video_path,           # Main video input
                        "-i", processed_subclip_path,    # Processed subclip with text and rounded boxes
                        "-filter_complex",
                        # Trim main video into 3 segments: before, during, and after the subclip
                        f"[0:v]trim=end={start_time},setpts=PTS-STARTPTS[before];"+
                        f"[0:v]trim=start={end_time},setpts=PTS-STARTPTS[after];"+
                        # No additional processing needed for the subclip since it's already processed
                        f"[1:v]copy[subclipwithtext];"+
                        # Concatenate the segments
                        f"[before][subclipwithtext][after]concat=n=3:v=1:a=0[v]",
                        # Map the processed video stream
                        "-map", "[v]",
                        # Copy audio from main video
                        "-map", "0:a?",
                        "-c:v", video_codec,
                    ]
                    overlay_cmd.extend(video_options)
                    overlay_cmd.extend([
                        "-c:a", "copy",
                        output_path
                    ])
                    
                else:
                    # Use the standard approach with filter-based subtitles
                    overlay_cmd = [
                        "ffmpeg", "-y",
                        "-i", main_video_path,           # Main video input
                        "-i", processed_subclip_path,    # Processed subclip input
                        "-filter_complex",
                        # Trim main video into 3 segments: before, during, and after the subclip
                        f"[0:v]trim=end={start_time},setpts=PTS-STARTPTS[before];"+
                        f"[0:v]trim=start={end_time},setpts=PTS-STARTPTS[after];"+
                        # Process subclip with subtitles
                        f"[1:v]{subtitle_filter}[subclipwithtext];"+
                        # Concatenate the segments
                        f"[before][subclipwithtext][after]concat=n=3:v=1:a=0[v]",
                        # Map the processed video stream
                        "-map", "[v]",
                        # Copy audio from main video
                        "-map", "0:a?",
                        "-c:v", video_codec,
                    ]
                    overlay_cmd.extend(video_options)
                    overlay_cmd.extend([
                        "-c:a", "copy",
                        output_path
                    ])
                
                print(f"Replacing subclip with command: {' '.join(overlay_cmd)}")
                subprocess.run(overlay_cmd, check=True)
                
                # Verify the final video
                if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                    # Save the new video to the model
                    with open(output_path, 'rb') as output_file:
                        output_filename = f"video_{self.video.id}_updated_{int(time.time())}.mp4"
                        self.video.output.save(output_filename, File(output_file), save=True)
                    print(f"Successfully replaced subclip {subclip.id} in video {self.video.id}")
                    return True
                else:
                    raise Exception(f"Output file not created or empty: {output_path}")

            # Clean up temp files
            for path in [subclip_video_path, main_video_path]:
                if os.path.exists(path):
                    os.unlink(path)
                    
            return True
            
        except Exception as e:
            logger.error(f"Error replacing subclip {subclip.id}: {str(e)}")
            # Attempt to clean up temp files if they exist
            for var in ['subclip_video_path', 'main_video_path']:
                if var in locals() and locals()[var] and os.path.exists(locals()[var]):
                    try:
                        os.unlink(locals()[var])
                    except:
                        pass
            return False
        


    def add_watermarks_to_video(self):
        """
        Add watermarks to both regular output and output with background music.
        Saves watermarked versions to separate fields in the Video model.
        
        Returns:
            bool: True if successful, False otherwise
        """
        success = True
        video = self.video
        
        try:
            # Create temporary directory for processing
            with tempfile.TemporaryDirectory() as temp_dir:
                # Process regular output
                if video.output and default_storage.exists(video.output.name):
                    # Create temp file for the input video
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_file:
                        # Download the file from storage
                        with default_storage.open(video.output.name, 'rb') as s3_file:
                            temp_file.write(s3_file.read())
                        input_path = temp_file.name
                    
                    # Create path for watermarked output
                    output_path = os.path.join(temp_dir, f"output_watermarked_{int(time.time())}.mp4")
                    
                    # Apply watermark
                    if self.apply_watermark(input_path, output_path, True, None):  # Try GPU first
                        # Save to model
                        with open(output_path, 'rb') as output_file:
                            filename = f"video_{video.id}_watermarked.mp4"
                            video.output_with_watermark.save(filename, File(output_file), save=True)
                        print(f"Successfully saved watermarked output to video.output_with_watermark")
                    else:
                        print("Failed to apply watermark to regular output")
                        success = False
                    
                    # Clean up input temp file
                    os.unlink(input_path)
                
                # Process output with background music if it exists
                if video.output_with_bg and default_storage.exists(video.output_with_bg.name):
                    # Create temp file for the input video with bg music
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_file:
                        # Download the file from storage
                        with default_storage.open(video.output_with_bg.name, 'rb') as s3_file:
                            temp_file.write(s3_file.read())
                        bg_input_path = temp_file.name
                    
                    # Create path for watermarked output
                    bg_output_path = os.path.join(temp_dir, f"output_bg_watermarked_{int(time.time())}.mp4")
                    
                    # Apply watermark
                    if self.apply_watermark(bg_input_path, bg_output_path, True, None):  # Try GPU first
                        # Save to model
                        with open(bg_output_path, 'rb') as output_file:
                            filename = f"video_{video.id}_bg_watermarked.mp4"
                            video.output_with_bg_watermark.save(filename, File(output_file), save=True)
                        print(f"Successfully saved watermarked background music output to video.output_with_bg_watermark")
                    else:
                        print("Failed to apply watermark to output with background music")
                        success = False
                    
                    # Clean up temp file
                    os.unlink(bg_input_path)
            
            return success
            
        except Exception as e:
            print(f"Error adding watermarks to video: {str(e)}")
            return False
            
    def apply_watermark(self, input_path, output_path, use_gpu=False, nvenc_preset=None):
        """
        Apply a watermark to the video file
        
        Args:
            input_path: Path to the input video file (local file path)
            output_path: Path to save the watermarked video (local file path)
            use_gpu: Whether to use GPU acceleration
            nvenc_preset: NVENC preset to use for GPU encoding
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Set the watermark path - check if it exists in static folder
            watermark_path = os.path.join(settings.BASE_DIR, "static", "watermark.png")
            
            if not os.path.exists(watermark_path):
                print(f"Watermark image not found at {watermark_path}, checking alternate locations")
                # Try some alternate locations
                alt_paths = [
                    os.path.join(settings.BASE_DIR, "media", "watermark.png"),
                    os.path.join(settings.BASE_DIR, "assets", "watermark.png")
                ]
                for path in alt_paths:
                    if os.path.exists(path):
                        watermark_path = path
                        print(f"Found watermark at alternate location: {watermark_path}")
                        break
                else:
                    print("Watermark not found in any standard location")
                    return False
            
            # Determine video dimensions using ffprobe
            probe_cmd = [
                "ffprobe", 
                "-v", "error", 
                "-select_streams", "v:0", 
                "-show_entries", "stream=width,height", 
                "-of", "csv=s=x:p=0", 
                input_path
            ]
            
            dimensions = subprocess.check_output(probe_cmd).decode("utf-8").strip()
            width, height = map(int, dimensions.split('x'))
            print(f"Video dimensions: {width}x{height}")
            
            # Calculate watermark scale - different for portrait vs landscape
            if height > width:  # Portrait video
                watermark_scale = 0.15  # 15% of width for portrait videos
            else:  # Landscape or square video
                watermark_scale = 0.25  # 25% of width for landscape videos
                
            # Calculate overlay position - place in bottom right corner with margin
            margin_percentage = 0.05  # 5% margin
            margin_x = int(width * margin_percentage)
            margin_y = int(height * margin_percentage)
            
            # Define encoder based on GPU availability
            video_codec = "h264_nvenc" if use_gpu else "libx264"
            
            # Set encoder preset options
            if use_gpu:
                preset_option = ["-preset", nvenc_preset] if nvenc_preset else ["-preset", "p4"]
            else:
                # CPU optimization - faster preset for watermarking
                preset_option = ["-preset", "fast", "-tune", "fastdecode"]
            
            # Apply watermark overlay with scale parameter
            overlay_filter = (
                f"movie={watermark_path} [watermark]; "
                f"[watermark] scale=iw*{watermark_scale}:-1 [scaled_watermark]; "
                f"[0:v][scaled_watermark] overlay=main_w-overlay_w-{margin_x}:main_h-overlay_h-{margin_y}:"
                f"eval=init:format=auto [v]"
            )
            
            # Build the ffmpeg command
            cmd = [
                "ffmpeg",
                "-y",  # Overwrite output files
                "-i", input_path,
                "-filter_complex", overlay_filter,
                "-map", "[v]",       # Map the processed video
                "-map", "0:a?",      # Map audio if present (optional)
                "-c:v", video_codec,
            ]
            cmd.extend(preset_option)
            cmd.extend([
                "-c:a", "copy",      # Copy audio stream without re-encoding
                "-pix_fmt", "yuv420p",
                "-r", str(self.framerate),
                output_path
            ])
            
            print(f"Applying watermark with command: {' '.join(cmd)}")
            subprocess.run(cmd, check=True)
            
            # Verify the output file was created
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                print(f"Successfully applied watermark to video, saved to {output_path}")
                return True
            else:
                print("Watermarked output file was not created or is empty")
                return False
                
        except subprocess.CalledProcessError as e:
            print(f"Error applying watermark with GPU, falling back to CPU: {str(e)}")
            
            # Try again with CPU if GPU failed
            if use_gpu:
                try:
                    return self.apply_watermark(input_path, output_path, False, None)
                except Exception as fallback_error:
                    print(f"CPU fallback also failed: {str(fallback_error)}")
                    return False
            return False
            
        except Exception as e:
            print(f"Error applying watermark: {str(e)}")
            return False