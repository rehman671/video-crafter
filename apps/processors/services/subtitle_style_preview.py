import os
import subprocess
import tempfile

def create_subtitle_preview():
    """Create a video with different subtitle box styles"""
    width, height = 1920, 1080
    duration = 20  # seconds
    font_size = 60
    
    # Create temporary directory for files
    with tempfile.TemporaryDirectory() as temp_dir:
        # First create a black video
        base_video = os.path.join(temp_dir, "base.mp4")
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", f"color=black:s={width}x{height}:d={duration}:r=30", 
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p", base_video
        ])
        
        # Now add subtitles with different styles
        output_video = "subtitle_styles_preview.mp4"
        
        # Build the filter complex for multiple subtitle styles
        filters = []
        
        # Example text
        text = "This is how subtitles look with different box_roundness settings"
        styles = [
            {"name": "No box (box_roundness=0)", "roundness": 0, "time": "0,5"},
            {"name": "Slight box (box_roundness=2)", "roundness": 2, "time": "5,10"},
            {"name": "Medium box (box_roundness=5)", "roundness": 5, "time": "10,15"},
            {"name": "Large box (box_roundness=10)", "roundness": 10, "time": "15,20"}
        ]
        
        # Filter starting point
        filters.append("[0:v]")
        
        # Add each style
        for style in styles:
            # Style name at top
            filters.append(
                f"drawtext=text='{style['name']}':fontcolor=white:fontsize=40:"
                f"x=(w-tw)/2:y=100:enable='between(t,{style['time']})',"
            )
            
            # Main text at bottom with different styles
            box_padding = int(style["roundness"] * 2)
            if style["roundness"] > 0:
                filters.append(
                    f"drawtext=text='{text}':fontcolor=white:fontsize={font_size}:"
                    f"x=(w-tw)/2:y=800:enable='between(t,{style['time']})':"
                    f"box=1:boxcolor=black@0.7:boxborderw={box_padding}:borderw=1:bordercolor=white@0.9,"
                )
            else:
                filters.append(
                    f"drawtext=text='{text}':fontcolor=white:fontsize={font_size}:"
                    f"x=(w-tw)/2:y=800:enable='between(t,{style['time']})':"
                    f"borderw=2:bordercolor=black@0.8,"
                )
        
        # Remove the trailing comma
        if filters[-1].endswith(","):
            filters[-1] = filters[-1][:-1]
        
        filter_complex = "".join(filters)
        
        # Create the styled video
        subprocess.run([
            "ffmpeg", "-y", "-i", base_video, 
            "-vf", filter_complex,
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
            output_video
        ])
        
        print(f"Preview video created: {output_video}")
        print("Open this file to see different subtitle box styles with various box_roundness values.")

if __name__ == "__main__":
    create_subtitle_preview()
