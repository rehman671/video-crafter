# VideoCrafter

A high-performance video creation system that automatically assembles videos from a script with highlighted words/phrases and associated video clips.

## Features

- **Hardware-accelerated processing** - Uses NVIDIA CUDA, AMD AMF, Intel QSV, or Apple VideoToolbox for fast video processing
- **Multiple video dimensions** - Support for 1:1, 9:16, 4:5, and 16:9 aspect ratios
- **Word-level alignment** - Uses Aeneas for precise alignment of text and audio
- **Parallel processing** - Processes multiple video clips simultaneously for maximum speed
- **ElevenLabs integration** - High-quality voiceovers from text
- **Intelligent caching** - Avoids reprocessing unchanged clips
- **Quick scene updates** - Change individual clips without reprocessing the entire video

## Requirements

- Python 3.8+
- FFmpeg with hardware acceleration support
- Aeneas for audio-text alignment
- ElevenLabs API key for voiceovers

## Installation

```bash
pip install -r requirements.txt
```

Make sure FFmpeg is installed with hardware acceleration support:

```bash
# For Ubuntu with NVIDIA GPU
apt-get install ffmpeg nvidia-cuda-toolkit

# For macOS
brew install ffmpeg
```

## Usage

### Basic usage

```python
from video_crafter import VideoCrafter

# Initialize with ElevenLabs API key
crafter = VideoCrafter(api_key="your_elevenlabs_api_key")

# Set video dimensions
crafter.set_dimension("16:9")  # Options: "1:1", "9:16", "4:5", "16:9"

# Set script
crafter.set_script("Welcome to our tutorial on machine learning. Today we'll explore neural networks.")

# Add highlighted words with associated clips
crafter.add_highlighted_word("machine learning", "clips/machine_learning.mp4")
crafter.add_highlighted_word("neural networks", "clips/neural_networks.mp4")

# Generate voiceover
crafter.generate_voiceover()

# Align audio with text
crafter.align_audio_with_text()

# Process video clips
crafter.process_video_clips()

# Assemble final video
output_path = crafter.assemble_final_video("tutorial.mp4")
print(f"Video saved to: {output_path}")
```

### Update a single clip

```python
# Update a clip without reprocessing everything
crafter.update_clip(1, "clips/new_neural_networks.mp4")
```

### One-step video creation

```python
output = crafter.create_full_video(
    script="Welcome to our tutorial on machine learning. Today we'll explore neural networks.",
    highlighted_words=[
        {"text": "machine learning", "clip_path": "clips/machine_learning.mp4"},
        {"text": "neural networks", "clip_path": "clips/neural_networks.mp4"}
    ],
    dimension="16:9",
    voice_id="your_voice_id"  # Optional
)
```

## Performance

The system is optimized to process a 5-minute video with 150 clips in approximately 90 seconds using hardware acceleration on a modern GPU.

## How it works

1. User selects video dimensions and writes script with highlighted words/phrases
2. ElevenLabs API generates high-quality voiceover
3. Aeneas aligns the script with the voiceover audio at word level
4. Each highlighted word is associated with a video clip
5. All clips are processed in parallel using hardware acceleration
6. The final video is assembled with FFmpeg
7. Project metadata is saved for quick scene updates

## License

MIT
