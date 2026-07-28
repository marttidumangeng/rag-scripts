"""
Video Optimizer for Hero Background Videos
==========================================

Compresses and resizes a video for web hero background usage.
Targets < 1MB output following best practices:
  - H.264 (MP4) for broad compatibility
  - WebM (VP9) as a smaller modern-browser alternative
    - Resolution capped at 960x540 (balanced quality while staying sub-1MB)
  - 24fps, no audio track
  - CRF-based quality for efficient compression

Requirements:
  pip install ffmpeg-python

FFmpeg must be installed and on PATH:
  - Windows: choco install ffmpeg  OR  download from https://ffmpeg.org/download.html
  - macOS:   brew install ffmpeg
  - Linux:   sudo apt install ffmpeg
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path


def get_video_info(input_path: str) -> dict:
    """Get video metadata using ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        input_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ffprobe error: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    import json
    return json.loads(result.stdout)


def format_size(size_bytes: int) -> str:
    """Format bytes to human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def optimize_video(
    input_path: str,
    output_dir: str,
    max_width: int = 960,
    max_height: int = 540,
    fps: int = 24,
    crf_mp4: int = 26,
    crf_webm: int = 33,
    duration: float | None = None,
) -> None:
    """
    Optimize a video file for web hero background usage.

    Args:
        input_path:  Path to the source video file.
        output_dir:  Directory to write optimized outputs.
        max_width:   Maximum output width (default 1280).
        max_height:  Maximum output height (default 720).
        fps:         Target frame rate (default 24).
        crf_mp4:     CRF value for H.264 (lower = better quality, bigger file).
        crf_webm:    CRF value for VP9 WebM.
        duration:    If set, trim the video to this many seconds.
    """
    input_path = os.path.abspath(input_path)
    if not os.path.isfile(input_path):
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    os.makedirs(output_dir, exist_ok=True)

    stem = Path(input_path).stem
    original_size = os.path.getsize(input_path)
    print(f"Input:  {input_path}")
    print(f"Size:   {format_size(original_size)}")

    # Probe original video
    info = get_video_info(input_path)
    for stream in info.get("streams", []):
        if stream.get("codec_type") == "video":
            w = stream.get("width", "?")
            h = stream.get("height", "?")
            r = stream.get("r_frame_rate", "?")
            print(f"Source: {w}x{h} @ {r} fps")
            break
    print()

    # Scale filter: fit within max_width x max_height, keep aspect ratio, divisible by 2
    scale_filter = (
        f"scale='min({max_width},iw)':min'({max_height},ih)'"
        f":force_original_aspect_ratio=decrease,"
        f"scale=trunc(iw/2)*2:trunc(ih/2)*2"
    )
    # Simpler approach using the two-pass scale trick
    scale_filter = (
        f"scale=w='min({max_width},iw)':h='min({max_height},ih)'"
        f":force_original_aspect_ratio=decrease,"
        f"pad=ceil(iw/2)*2:ceil(ih/2)*2"
    )

    # --- MP4 (H.264) ---
    mp4_out = os.path.join(output_dir, f"{stem}-optimized.mp4")
    print(f"[1/2] Encoding MP4 (H.264, CRF {crf_mp4}) ...")

    mp4_cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-an",                         # Remove audio
        "-vf", scale_filter,
        "-c:v", "libx264",
        "-crf", str(crf_mp4),
        "-preset", "slow",            # Better compression
        "-profile:v", "main",
        "-level", "4.0",
        "-movflags", "+faststart",     # Web streaming friendly
        "-pix_fmt", "yuv420p",
        "-r", str(fps),
    ]
    if duration:
        mp4_cmd.extend(["-t", str(duration)])
    mp4_cmd.append(mp4_out)

    result = subprocess.run(mp4_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"FFmpeg MP4 error:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)

    mp4_size = os.path.getsize(mp4_out)
    print(f"   -> {mp4_out}")
    print(f"      Size: {format_size(mp4_size)} ({(1 - mp4_size / original_size) * 100:.0f}% reduction)")
    print()

    # --- WebM (VP9) ---
    webm_out = os.path.join(output_dir, f"{stem}-optimized.webm")
    print(f"[2/2] Encoding WebM (VP9, CRF {crf_webm}) ...")

    webm_cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-an",
        "-vf", scale_filter,
        "-c:v", "libvpx-vp9",
        "-crf", str(crf_webm),
        "-b:v", "0",                  # Constant quality mode
        "-row-mt", "1",               # Multi-threaded row encoding
        "-pix_fmt", "yuv420p",
        "-r", str(fps),
    ]
    if duration:
        webm_cmd.extend(["-t", str(duration)])
    webm_cmd.append(webm_out)

    result = subprocess.run(webm_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"FFmpeg WebM error:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)

    webm_size = os.path.getsize(webm_out)
    print(f"   -> {webm_out}")
    print(f"      Size: {format_size(webm_size)} ({(1 - webm_size / original_size) * 100:.0f}% reduction)")
    print()

    # --- Poster Image (first frame) ---
    poster_out = os.path.join(output_dir, f"{stem}-poster.jpg")
    print("Extracting poster image (first frame) ...")

    poster_cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vframes", "1",
        "-vf", scale_filter,
        "-q:v", "2",
        poster_out,
    ]
    result = subprocess.run(poster_cmd, capture_output=True, text=True)
    if result.returncode == 0:
        poster_size = os.path.getsize(poster_out)
        print(f"   -> {poster_out} ({format_size(poster_size)})")
    else:
        print(f"   Poster extraction failed (non-critical): {result.stderr[:200]}")

    # --- Summary ---
    print()
    print("=" * 50)
    print("SUMMARY")
    print("=" * 50)
    print(f"Original:   {format_size(original_size)}")
    print(f"MP4 (H264): {format_size(mp4_size)}")
    print(f"WebM (VP9): {format_size(webm_size)}")
    print()
    print("Usage in HTML:")
    print("""
<video autoplay muted loop playsinline preload="auto" poster="hero-video-poster.jpg">
  <source src="hero-video-optimized.webm" type="video/webm" />
  <source src="hero-video-optimized.mp4" type="video/mp4" />
</video>
""")

    # Warn if files are still large
    target_mb = 1
    if mp4_size > target_mb * 1024 * 1024:
        print(f"WARNING: MP4 is still > {target_mb}MB. Consider:")
        print(f"  - Increasing CRF (current: {crf_mp4}, try {crf_mp4 + 2})")
        print(f"  - Reducing resolution (current: {max_width}x{max_height}, try 854x480)")
        print(f"  - Trimming duration with --duration 8")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Optimize a video for web hero background usage.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python optimize_hero_video.py hero-video.mp4
  python optimize_hero_video.py hero-video.mp4 -o ./output --width 960 --height 540
  python optimize_hero_video.py hero-video.mp4 --crf-mp4 26 --crf-webm 33 --duration 8
  python optimize_hero_video.py hero-video.mp4 --crf-mp4 24 --crf-webm 30 --duration 8  # higher quality
  python optimize_hero_video.py hero-video.mp4 --crf-mp4 28 --crf-webm 35 --duration 8  # smaller file
        """,
    )
    parser.add_argument("input", help="Path to the input video file")
    parser.add_argument("-o", "--output-dir", default="./optimized", help="Output directory (default: ./optimized)")
    parser.add_argument("--width", type=int, default=960, help="Max output width (default: 960)")
    parser.add_argument("--height", type=int, default=540, help="Max output height (default: 540)")
    parser.add_argument("--fps", type=int, default=24, help="Target frame rate (default: 24)")
    parser.add_argument("--crf-mp4", type=int, default=26, help="H.264 CRF quality (default: 26, lower = better quality, bigger file)")
    parser.add_argument("--crf-webm", type=int, default=33, help="VP9 CRF quality (default: 33, lower = better quality, bigger file)")
    parser.add_argument("--duration", type=float, default=None, help="Trim video to N seconds (e.g. 8)")

    args = parser.parse_args()

    # Check ffmpeg is available
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except FileNotFoundError:
        print("Error: ffmpeg not found on PATH.", file=sys.stderr)
        print("Install it: choco install ffmpeg (Windows) / brew install ffmpeg (macOS)", file=sys.stderr)
        sys.exit(1)

    optimize_video(
        input_path=args.input,
        output_dir=args.output_dir,
        max_width=args.width,
        max_height=args.height,
        fps=args.fps,
        crf_mp4=args.crf_mp4,
        crf_webm=args.crf_webm,
        duration=args.duration,
    )


if __name__ == "__main__":
    main()
