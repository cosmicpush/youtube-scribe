import asyncio
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


def sanitize_filename(title: str) -> str:
    return re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '_')[:80]


async def extract_audio(url: str, output_dir: Path) -> tuple[Path, dict]:
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
        url,
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        error_msg = stderr.decode().strip()
        raise RuntimeError(f"yt-dlp failed: {error_msg}")

    import json
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
