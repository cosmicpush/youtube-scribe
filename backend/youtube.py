import asyncio
import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


def sanitize_filename(title: str) -> str:
    return re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '_')[:80]


async def extract_audio(
    url: str,
    output_dir: Path,
    cookies_path: Path | None = None,
) -> tuple[Path, dict]:
    """Download YouTube video audio as mp3. Returns (audio_path, video_info)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(output_dir / "%(id)s.%(ext)s")

    cmd = [
        "yt-dlp",
        "--extract-audio",
        "--audio-format", "mp3",
        "--audio-quality", "3",
        "--output", output_template,
        "--print-json",
        "--no-playlist",
        "--no-warnings",
    ]
    if cookies_path:
        cmd.extend(["--cookies", str(cookies_path)])
    cmd.append(url)

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        error_msg = stderr.decode().strip()
        raise RuntimeError(f"yt-dlp failed: {error_msg}")

    info = json.loads(stdout.decode().strip().split('\n')[-1])

    video_id = info.get("id", "unknown")
    audio_path = output_dir / f"{video_id}.mp3"

    if not audio_path.exists():
        # Try finding any mp3 in the output dir
        mp3_files = list(output_dir.glob(f"{video_id}.*"))
        if mp3_files:
            audio_path = mp3_files[0]
        else:
            raise FileNotFoundError(f"Audio file not found for {video_id}")

    video_info = {
        "id": video_id,
        "title": info.get("title", "Unknown"),
        "duration": info.get("duration", 0),
        "channel": info.get("channel", "Unknown"),
        "thumbnail": info.get("thumbnail", ""),
    }

    logger.info(f"Extracted audio: {audio_path} ({video_info['duration']}s)")
    return audio_path, video_info


async def transcode_to_mp3(
    video_path: Path,
    output_dir: Path,
    job_id: str,
    display_title: str,
) -> tuple[Path, dict]:
    """Extract audio track from an uploaded video file. Returns (mp3_path, video_info)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    audio_path = output_dir / f"{job_id}.mp3"

    cmd = [
        "ffmpeg",
        "-i", str(video_path),
        "-vn",
        "-acodec", "libmp3lame",
        "-q:a", "3",
        "-y",
        str(audio_path),
    ]
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    if process.returncode != 0:
        tail = stderr.decode().strip().splitlines()[-5:]
        raise RuntimeError("ffmpeg failed: " + " | ".join(tail))

    duration = 0
    probe = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(audio_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    probe_out, _ = await probe.communicate()
    try:
        duration = int(float(probe_out.decode().strip()))
    except (ValueError, AttributeError):
        pass

    video_info = {
        "id": job_id,
        "title": display_title or "Uploaded video",
        "duration": duration,
        "channel": "Local upload",
        "thumbnail": "",
    }

    logger.info(f"Transcoded upload to {audio_path} ({duration}s)")
    return audio_path, video_info
