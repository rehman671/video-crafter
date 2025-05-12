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

        # Font configuration - properly use the font from the Video model
        if self.video.subtitle_font and os.path.exists(os.path.join(settings.BASE_DIR, self.video.subtitle_font.font_path)):
            # Use the font specified in the video model
            self.font_path = os.path.join(settings.BASE_DIR, self.video.subtitle_font.font_path)
            print(f"Using specified font: {self.video.subtitle_font.name} at {self.font_path}")
        else:
            # Fallback to system fonts if the specified font is not available
            self.font_path = self._find_available_font()
            print(f"Using fallback font: {self.font_path}")

        # Use the font size from the video model, with a fallback ratio
        self.font_size = self.video.font_size if self.video.font_size > 0 else 20
        self.font_size_ratio = 40  # Only used if calculating font size based on video height
        
        # Get font color from video model
        self.font_color = self.video.font_color
        
        # Get subtitle box color and padding from video model
        self.subtitle_box_color = self.video.subtitle_box_color
        self.subtitle_box_padding = 0.4
        
        # Get box roundness from video model
        self.box_roundness = self.video.box_roundness
        
        # Set global framerate for consistency
        self.framerate = 30

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
        Smart text wrapping for subtitles to ensure all text is visible.
        Prioritizes readability while guaranteeing that all text fits within constraints.
        
        Args:
            text: The text to wrap
            max_width: Maximum width in pixels (if known)
        """
        words = text.split()
        total_words = len(words)
        total_chars = len(text)
        
        # Very short text (few words or characters) - keep as single line
        if total_words <= 4 or total_chars <= 30:
            return [text]
        
        # For medium-to-long text, use a more reliable character-based approach
        # Aim for 30-40 characters per line for short/medium text, less for longer text
        max_chars_per_line = 40
        if total_chars > 100:
            max_chars_per_line = 35  # Shorter lines for very long text
        elif total_chars > 60:
            max_chars_per_line = 38  # Medium length for medium text
        
        # Initialize variables for line building
        lines = []
        current_line = []
        current_chars = 0
        
        # Process each word
        for word in words:
            # Check if adding this word would exceed max line length
            # Account for space before word
            space_needed = 1 if current_line else 0
            if current_chars + space_needed + len(word) > max_chars_per_line and current_line:
                # Complete the current line and start a new one
                lines.append(" ".join(current_line))
                current_line = [word]
                current_chars = len(word)
            else:
                # Add word to current line
                if current_line:  # Add space character count
                    current_chars += 1
                current_line.append(word)
                current_chars += len(word)
        
        # Add any remaining words
        if current_line:
            lines.append(" ".join(current_line))
        
        # If we have more than 3 lines for longer text, try to optimize line distribution
        if len(lines) > 3:
            optimized_lines = []
            merged_line = ""
            
            for i, line in enumerate(lines):
                # If adding this line wouldn't exceed our target length or this is the last line
                if len(merged_line) + len(line) + 1 <= max_chars_per_line * 1.2 and merged_line:
                    merged_line += " " + line
                else:
                    if merged_line:
                        optimized_lines.append(merged_line)
                    merged_line = line
            
            # Add the last merged line
            if merged_line:
                optimized_lines.append(merged_line)
            
            lines = optimized_lines
        
        # For extremely long text that still results in too many lines,
        # we'll keep the first 3 lines and indicate continuation with "..."
        if len(lines) > 3:
            first_two_lines = lines[:2]
            remaining_text = " ".join(lines[2:])
            
            # Trim the remaining text if it's too long and add ellipsis
            if len(remaining_text) > max_chars_per_line:
                # Find the last space before the limit
                cutoff = max_chars_per_line - 3  # Allow space for "..."
                last_space = remaining_text.rfind(" ", 0, cutoff)
                if last_space > 0:
                    remaining_text = remaining_text[:last_space] + "..."
                else:
                    remaining_text = remaining_text[:cutoff] + "..."
            
            # Use the first two lines plus the trimmed final line
            lines = first_two_lines + [remaining_text]
        
        return lines

    def generate_video(self):
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
        else:
            width, height = 1920, 1080  # Default to 16:9

        # Calculate font size based on video height or use model setting
        if self.video.font_size > 0:
            font_size = self.video.font_size
        else:
            font_size = int(height / self.font_size_ratio)

        # Calculate safe area for text (positioned in lower third)
        text_y_position = int(height * 0.85)  # Lower third of the screen

        # Create temp directory for intermediate files - make it easy to identify
        temp_dir_suffix = f"videocrafter_temp_{self.video.id}_{int(time.time())}"
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
                        subtitle_timings.append(
                            {"text": clip.text, "start": clip.start_time, "end": clip.end_time, "is_main_clip": True}
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
                        
                        # If there's a portion of the main clip before this subclip, process it
                        if subclip_start > current_pos:
                            # Process clip segment before the subclip
                            clip_segment_path = os.path.join(temp_dir, f"clip_{i}_segment_{j}.mp4")
                            segment_duration = subclip_start - current_pos
                            
                            if segment_duration > 0:
                                # Create clip segment processing task
                                process_tasks.append(
                                    (
                                        {
                                            "type": "segment",
                                            "clip": clip,
                                            "start_offset": current_pos - clip.start_time,  # Offset from clip start
                                            "duration": segment_duration,
                                            "text": clip.text
                                        },
                                        clip_segment_path,
                                        f"{i}_segment_{j}",
                                        width,
                                        height,
                                        use_gpu,
                                        nvenc_preset if use_gpu else None,
                                        1.0,  # No speed adjustment for segments
                                        current_pos,
                                        subclip_start,
                                    )
                                )
                                
                                # Add to segment files
                                segment_files.append(
                                    {
                                        "file": clip_segment_path,
                                        "text": clip.text,
                                        "start_time": current_pos,
                                        "end_time": subclip_start,
                                        "is_black": False,
                                        "clip_index": f"{i}_segment_{j}",
                                        "is_segment": True,
                                    }
                                )
                                
                                # We no longer add subtitle timing for individual segments
                                # since we added one subtitle for the entire clip above
                                
                                print(f"Added clip segment before subclip: {current_pos:.3f} to {subclip_start:.3f}")
                        
                        # Process the subclip
                        if subclip.video_file and os.path.exists(subclip.video_file.path):
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
                            
                            # We no longer add subtitle timing for subclips
                            
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
                            target_duration = min(self.min_clip_duration, final_segment_duration * 1.5)
                            speed_factor = final_segment_duration / target_duration
                            adjusted_end_time = current_pos + target_duration
                        else:
                            target_duration = min(final_segment_duration, self.max_clip_duration)
                            adjusted_end_time = current_pos + target_duration
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
                        
                        # We no longer add subtitle timing for individual segments
                        # since we added one subtitle for the entire clip above
                        
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
            
            # Make sure we use the FULL text from clips, not just segments
            # This ensures complete sentences are shown
            updated_subtitles = []
            for clip in clips_list:
                if clip.text:
                    # Don't look for matching subtitles, just use the clip's own timing
                    updated_subtitles.append({
                        "text": clip.text,
                        "start": clip.start_time,
                        "end": clip.end_time,
                        "is_main_clip": True
                    })
            # If we have updated subtitles, use them instead
            if updated_subtitles:
                subtitle_timings = updated_subtitles
                print(f"Using {len(subtitle_timings)} consolidated subtitles with FULL text")
            
            # Filter subtitle_timings to only include main clip subtitles if needed
            subtitle_timings = [st for st in subtitle_timings if st.get("is_main_clip", False)]
            print(f"Using {len(subtitle_timings)} main clip subtitles for final video")

            # If we have an audio file, get its EXACT duration
            precise_audio_duration = 0
            if self.video.audio_file and os.path.exists(self.video.audio_file.path):
                try:
                    # Get PRECISE audio duration using ffprobe
                    probe_cmd = [
                        "ffprobe",
                        "-v",
                        "error",
                        "-show_entries",
                        "format=duration",
                        "-of",
                        "default=noprint_wrappers=1:nokey=1",
                        self.video.audio_file.path,
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
                            # We'll handle this in the final output step

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
                for idx, segment in enumerate(segment_files):
                    # Debug the last few segments being written to the concat file
                    if idx >= len(segment_files) - 3:
                        print(f"Writing to concat file [{idx}]: {os.path.basename(segment['file'])}, duration={(segment['end_time'] - segment['start_time']):.3f}s")
                    
                    # Fix for last clip: Make sure we're including the last segment even if it slightly exceeds audio duration
                    if total_duration < precise_audio_duration or idx == len(segment_files) - 1:
                        f.write(f"file '{segment['file']}'\n")
                        duration = segment["end_time"] - segment["start_time"]
                        total_duration += duration

            # Concatenate all segments
            concat_start_time = time.time()
            print("Starting clip concatenation with EXACT timing")
            self._update_progress(60, "Concatenating video segments")
            
            intermediate_output = os.path.join(temp_dir, "intermediate.mp4")

            subprocess.run(
                [
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
                    str(self.framerate),  # Force 30fps output
                    intermediate_output,
                ],
                check=True,
            )

            concat_end_time = time.time()
            self._update_progress(70, "Adding subtitles and audio")
            
            print(
                f"Finished clip concatenation in {concat_end_time - concat_start_time:.2f} seconds"
            )

            # Add text overlays to the final video - ensure strict subtitle alignment
            final_output_path = os.path.join(temp_dir, "final_output.mp4")
            temp_output_path = os.path.join(temp_dir, "temp_output.mp4")
            filter_complex = []

            # Start with the base video
            filter_complex.append("[0:v]")

            # Add text overlays using the EXACT subtitle timings
            has_text = False

            # Calculate maximum text width as percentage of video width (80% of width to leave margins)
            max_text_width = int(width * 0.8)

            for i, subtitle in enumerate(subtitle_timings):
                if subtitle["text"]:  # Only add text if it exists
                    has_text = True
                    # Use EXACT subtitle timestamps
                    start_time_sec = subtitle["start"]
                    end_time_sec = subtitle["end"]

                    # Calculate approx max width in pixels based on video width (80% of screen width)
                    max_subtitle_width = int(width * 0.8)
                    
                    # Estimate approx characters per line based on font size and width
                    # This is an approximation: avg character width is roughly 0.5-0.7x font height
                    avg_char_width = font_size * 0.6  # Approximation
                    max_chars_per_line = int(max_subtitle_width / avg_char_width)
                    
                    # Use the improved text wrapping function with width constraints
                    text_lines = self._wrap_text(subtitle["text"], max_chars_per_line)
                    
                    # Limit to 2 lines maximum - combine any extra lines into second line
                    if len(text_lines) > 2:
                        text_lines = [text_lines[0], " ".join(text_lines[1:])]

                    # Calculate vertical spacing between lines (1.2x font size)
                    line_spacing = int(font_size * 1.2)

                    # Calculate starting y-position based on how many lines we have
                    # Position text block in lower third, accounting for multiple lines
                    num_lines = len(text_lines)

                    # Start position is the baseline for the first line
                    # For multi-line text, move up so the block is centered vertically
                    start_y = text_y_position - (line_spacing * (num_lines - 1) // 2)
                    
                    # Calculate proper box padding based on font size and user-defined padding factor
                    horizontal_padding = font_size * self.subtitle_box_padding
                    vertical_padding = font_size * self.subtitle_box_padding
                    
                    # Create a single unified box for all lines of this subtitle
                    # First, determine the maximum text width among all lines to make all boxes the same width
                    longest_line = max(text_lines, key=len) if text_lines else ""
                    
                    # Now we need to create a filter for the background box that will cover all lines
                    # We'll use a drawbox filter instead of relying on the box parameter in drawtext
                    
                    if num_lines > 0:
                        # Estimate box dimensions based on text lines
                        # We need to create a slightly larger box to account for padding
                        box_height = (num_lines * line_spacing) + (vertical_padding * 2)
                        
                        # For width estimation: calculate an approximation based on longest line
                        # Use a more precise estimation based on character count of the longest line
                        # Plus some additional padding for visual comfort
                        estimated_text_width = len(longest_line) * avg_char_width * 1  # 0.85 factor for better estimation
                        box_width = int(estimated_text_width + (horizontal_padding * 3))
                        
                        # Ensure box is not too narrow
                        min_width = int(width * 0.2)  # At least 20% of video width
                        box_width = max(box_width, min_width)
                        
                        # Ensure box is not too wide
                        max_width = int(width * 0.7)  # At most 70% of video width
                        box_width = min(box_width, max_width)
                        
                        # Calculate box position
                        # Use explicit calculation with integers for proper centering
                        box_x = f"(w-{box_width})/2"  # Center horizontally/
                        
                        # For better positioning, use absolute pixel values
                        # This ensures we get exactly centered boxes every time
                        box_x_fixed = int((width - box_width) / 2)
                        box_y = start_y - vertical_padding  # Top of first line minus padding
                        

                        filter_complex.append(
                            f"drawbox=x={box_x_fixed}:y={box_y}:"
                            f"w={box_width}:h={box_height}:"
                            f"color={self.subtitle_box_color}@1.0:t=fill:"
                            f"enable='between(t,{start_time_sec},{end_time_sec})'"
                        )
                        
                        if self.box_roundness > 0:
                            # Add a note about border radius
                            # (FFmpeg doesn't directly support rounded box corners, would need overlay)
                            print(f"Box roundness value {self.box_roundness} requested - simulated with padding")
                        
                        # Add comma for next filter
                        filter_complex.append(",")
                    
                    # Now add each line of text WITHOUT individual boxes
                    for line_idx, line_text in enumerate(text_lines):
                        # Calculate y position for this line
                        line_y = start_y + (line_idx * line_spacing)

                        # Prepare text (escape special characters)
                        escaped_text = (
                            line_text.replace("'", "\\'")
                            .replace(":", "\\:")
                            .replace(",", "\\,")
                        )

                        # Add drawtext filter with font size proportional to video dimensions
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

            # Check if we have an audio file to include
            if self.video.audio_file and os.path.exists(self.video.audio_file.path):
                # Apply text overlays and add audio
                if has_text:
                    # Only include the filter if we actually have text
                    cmd = [
                        "ffmpeg",
                        "-y",
                        "-i",
                        intermediate_output,
                        "-i",
                        self.video.audio_file.path,
                        "-vf",
                        filter_complex_str,
                        "-c:v",
                        video_codec,
                    ]
                else:
                    # Skip the filter if we don't have any text
                    cmd = [
                        "ffmpeg",
                        "-y",
                        "-i",
                        intermediate_output,
                        "-i",
                        self.video.audio_file.path,
                        "-c:v",
                        video_codec,
                    ]

                cmd.extend(video_options)
                cmd.extend(
                    [
                        "-c:a",
                        "aac",
                        "-map",
                        "0:v",
                        "-map",
                        "1:a",
                        "-r",
                        str(self.framerate),  # Force 30fps
                        temp_output_path,
                    ]
                )

                # Debug the command
                print(f"Running ffmpeg command: {' '.join(cmd)}")
                subprocess.run(cmd, check=True)

                # Now TRIM to EXACT audio duration
                trim_cmd = [
                    "ffmpeg",
                    "-y",
                    "-i",
                    temp_output_path,
                    "-t",
                    str(precise_audio_duration),  # EXACT trim to audio duration
                    "-c:v",
                    "copy",
                    "-c:a",
                    "copy",
                    final_output_path,
                ]
                print(f"Trimming to EXACT audio duration: {precise_audio_duration}s")
                subprocess.run(trim_cmd, check=True)

                # Verify the final duration
                verify_cmd = [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    final_output_path,
                ]
                final_duration = float(
                    subprocess.check_output(verify_cmd).decode("utf-8").strip()
                )
                print(
                    f"FINAL VIDEO DURATION: {final_duration:.6f}s (Target: {precise_audio_duration:.6f}s)"
                )

            else:
                # Apply text overlays without adding audio
                if has_text:
                    # Only include the filter if we actually have text
                    cmd = [
                        "ffmpeg",
                        "-y",
                        "-i",
                        intermediate_output,
                        "-vf",
                        filter_complex_str,
                        "-c:v",
                        video_codec,
                    ]
                else:
                    # Skip the filter if we don't have any text
                    cmd = [
                        "ffmpeg",
                        "-y",
                        "-i",
                        intermediate_output,
                        "-c:v",
                        video_codec,
                    ]

                cmd.extend(video_options)
                cmd.extend([final_output_path])

                # Debug the command
                print(f"Running final ffmpeg command: {' '.join(cmd)}")

                subprocess.run(cmd, check=True)

            final_end_time = time.time()
            self._update_progress(90, "Saving final video")
            
            print(
                f"Finished final video processing in {final_end_time - final_start_time:.2f} seconds"
            )

            # Save to the model
            save_start_time = time.time()
            final_output_path = os.path.join(temp_dir, "final_output.mp4")
            
            # Create a copy of the file in a location that won't be deleted when the temp dir is closed
            permanent_output_path = os.path.join(tempfile.gettempdir(), f"video_{self.video.id}_output_{int(time.time())}.mp4")
            with open(final_output_path, "rb") as src, open(permanent_output_path, "wb") as dst:
                dst.write(src.read())

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
        """Process an individual clip, segment, or subclip to standardized dimensions with strict timing"""
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

        # Set codec based on GPU availability
        video_codec = "h264_nvenc" if use_gpu else "libx264"
        video_options = ["-preset", nvenc_preset if use_gpu else "medium"]

        try:
            # Determine what type of item we're processing
            if isinstance(clip_data, dict) and clip_data.get("type") == "segment":
                # We're processing a segment of a clip
                main_clip = clip_data["clip"]
                
                # Check if there's a valid video file available
                if (main_clip.video_file and os.path.exists(main_clip.video_file.path)):
                    # Build filter for segment extraction and standardization
                    start_offset = clip_data["start_offset"]  # Time from the start of the original clip
                    segment_duration = clip_data["duration"]  # Duration of this segment
                    
                    # Process the segment with proper seeking and trimming
                    cmd = [
                        "ffmpeg",
                        "-y",
                        "-i",
                        main_clip.video_file.path,
                        "-ss",
                        str(start_offset),  # Start from offset within original clip
                        "-t",
                        str(segment_duration),  # Extract exact duration
                        "-vf",
                        f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}",
                        "-c:v",
                        video_codec,
                    ]
                    cmd.extend(video_options)
                    cmd.extend([
                        "-pix_fmt",
                        "yuv420p",
                        "-r",
                        str(self.framerate),
                        output_path,
                    ])
                    
                    subprocess.run(cmd, check=True)
                    print(f"Processed clip segment {index}: from offset {start_offset:.3f}s, duration {segment_duration:.3f}s")
                else:
                    # Create black video if no video file exists or file is missing
                    self._create_black_video(output_path, target_duration, width, height, use_gpu, nvenc_preset)
                    print(f"Created black screen for missing clip segment {index}, duration: {target_duration:.3f}s")
                    
            elif isinstance(clip_data, Subclip):
                # We're processing a subclip
                if clip_data.video_file and os.path.exists(clip_data.video_file.path):
                    # Process the subclip with standard parameters
                    filter_complex = [
                        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                        f"crop={width}:{height}"
                    ]
                    
                    # Add speed adjustment if needed
                    if speed_factor != 1.0:
                        filter_complex.append(f",setpts={speed_factor}*PTS")
                    
                    cmd = [
                        "ffmpeg",
                        "-y",
                        "-i",
                        clip_data.video_file.path,
                        "-t",
                        str(target_duration),
                        "-vf",
                        "".join(filter_complex),
                        "-c:v",
                        video_codec,
                    ]
                    cmd.extend(video_options)
                    cmd.extend([
                        "-pix_fmt",
                        "yuv420p",
                        "-r",
                        str(self.framerate),
                        output_path,
                    ])
                    
                    subprocess.run(cmd, check=True)
                    print(f"Processed subclip {index} with duration {target_duration:.3f}s")
                else:
                    # Create black video if no video file exists or file is missing
                    self._create_black_video(output_path, target_duration, width, height, use_gpu, nvenc_preset)
                    print(f"Created black screen for missing subclip {index}, duration: {target_duration:.3f}s")
            
            else:
                # Regular clip processing (original implementation)
                if clip_data.video_file and os.path.exists(clip_data.video_file.path):
                    # Build filter for standardization
                    filter_complex = [
                        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                        f"crop={width}:{height}"
                    ]
                    
                    # Add speed adjustment if needed
                    if speed_factor != 1.0:
                        filter_complex.append(f",setpts={speed_factor}*PTS")
                    
                    cmd = [
                        "ffmpeg",
                        "-y",
                        "-i",
                        clip_data.video_file.path,
                        "-t",
                        str(target_duration),
                        "-vf",
                        "".join(filter_complex),
                        "-c:v",
                        video_codec,
                    ]
                    cmd.extend(video_options)
                    cmd.extend([
                        "-pix_fmt",
                        "yuv420p",
                        "-r",
                        str(self.framerate),
                        output_path,
                    ])
                    
                    subprocess.run(cmd, check=True)
                    print(f"Processed clip {index} with duration {target_duration:.3f}s")
                else:
                    # Create black video if no video file exists or file is missing
                    self._create_black_video(output_path, target_duration, width, height, use_gpu, nvenc_preset)
                    print(f"Created black screen for clip {index}, duration: {target_duration:.3f}s")

        except Exception as e:
            logger.error(f"Error processing item {index}: {str(e)}")
            # Fallback to black screen
            try:
                self._create_black_video(output_path, target_duration, width, height, False, None)
                print(f"Fallback to black screen for {index} after error")
            except Exception as e2:
                logger.error(f"Critical error creating fallback for {index}: {str(e2)}")

    def _create_black_video(
        self, output_path, duration, width, height, use_gpu=False, nvenc_preset=None
    ):
        """Create a black video clip with specified duration and dimensions"""
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
        
        Args:
            bg_music: BackgroundMusic object containing audio file and timing information
        
        Returns:
            bool: True if successful, False otherwise
        """
        video = self.video
        
        # Check if the video has an output file
        if not video.output or not os.path.exists(video.output.path):
            logger.error(f"No output file found for video {video.id}")
            return False
        
        # Check if background music has a valid audio file
        if not bg_music.audio_file:
            logger.error(f"No audio file associated with background music for video {video.id}")
            return False
            
        if not bg_music.audio_file.name or not os.path.exists(bg_music.audio_file.path if bg_music.audio_file else ''):
            logger.error(f"Invalid or missing audio file for background music (video {video.id})")
            return False
        
        try:
            logger.info(f"Applying background music to video {video.id}")
            
            # Create temporary files for processing
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp_video:
                temp_output_path = tmp_video.name
            
            # Get the audio file path - ensure it exists
            audio_path = bg_music.audio_file.path
            if not os.path.exists(audio_path):
                logger.error(f"Audio file path does not exist: {audio_path}")
                return False
            
            # Get video duration using ffprobe
            video_duration_cmd = [
                "ffprobe", 
                "-v", "error", 
                "-show_entries", "format=duration", 
                "-of", "default=noprint_wrappers=1:nokey=1", 
                video.output.path
            ]
            video_duration = float(subprocess.check_output(video_duration_cmd).decode("utf-8").strip())
            
            # Check if audio needs to be trimmed
            end_time = min(bg_music.end_time, video_duration)
            
            # Use volume from bg_music (range 0 to 1)
            volume_level = bg_music.volume if hasattr(bg_music, 'volume') and 0 <= bg_music.volume <= 1 else 0.3
            
            # Create ffmpeg command to apply background music
            cmd = [
                "ffmpeg",
                "-y",
                "-i", video.output.path,  # Input video
                "-i", audio_path,         # Input audio
                "-filter_complex",
                # Trim audio if needed and set volume level from bg_music
                f"[1:a]atrim=start={bg_music.start_time}:end={end_time},asetpts=PTS-STARTPTS,volume={volume_level}[bgm];"
                # Mix with existing audio if present, otherwise just use background music
                f"[0:a][bgm]amix=inputs=2:duration=first[aout]",
                # Map the streams
                "-map", "0:v",            # Use original video stream
                "-map", "[aout]",         # Use mixed audio stream
                "-c:v", "copy",           # Copy video stream without re-encoding
                "-c:a", "aac",            # Re-encode audio as AAC
                "-b:a", "192k",           # Audio bitrate
                temp_output_path
            ]
            
            logger.info(f"Executing command: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            
            # Check if command was successful
            if result.returncode != 0:
                logger.error(f"FFmpeg command failed: {result.stderr}")
                # Clean up temporary file
                os.unlink(temp_output_path)
                return False
            
            # Update the video output_with_bg file instead of the original output
            filename = f"{os.path.splitext(os.path.basename(video.output.name))[0]}_with_bg.mp4"
            with open(temp_output_path, 'rb') as f:
                # Save to output_with_bg instead of output
                video.output_with_bg.save(filename, File(f), save=True)
            
            # Clean up temporary file
            os.unlink(temp_output_path)
            logger.info(f"Successfully applied background music to video {video.id}, saved as output_with_bg")
            return True
            
        except Exception as e:
            logger.error(f"Error applying background music to video {video.id}: {str(e)}")
            # Clean up temporary file if it exists
            if 'temp_output_path' in locals() and os.path.exists(temp_output_path):
                try:
                    os.unlink(temp_output_path)
                except:
                    pass
            return False



    # Add this method to your generator class:
    def _create_rounded_box(self, width, height, radius, color):
        from PIL import Image, ImageDraw

        """Create a rounded rectangle PNG for overlay."""
        img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # Convert hex color to RGBA
        if color.startswith('#'):
            color = color[1:]
        r = int(color[0:2], 16)
        g = int(color[2:4], 16)
        b = int(color[4:6], 16)
        a = 255
        
        draw.rounded_rectangle(
            [(0, 0), (width, height)],
            radius=radius,
            fill=(r, g, b, a)
        )
        
        return img