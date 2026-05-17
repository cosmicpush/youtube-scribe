import asyncio
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from config import load_config, save_config
from soniox_client import SonioxTranscriber
from transcript_formatter import tokens_to_srt, tokens_to_text
from youtube import extract_audio, transcode_to_mp3

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="YouTube Scribe API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_DIR = Path(os.environ.get("DATA_DIR", "/app/data"))
AUDIO_DIR = DATA_DIR / "audio"
JOBS_DIR = DATA_DIR / "jobs"
UPLOADS_DIR = DATA_DIR / "uploads"

UPLOAD_CHUNK = 1024 * 1024  # 1 MiB streaming chunks

# In-memory job tracking
jobs: dict[str, dict] = {}


class ConfigUpdate(BaseModel):
    soniox_api_key: str | None = None
    default_language: str | None = None
    enable_speaker_diarization: bool | None = None
    translation_mode: str | None = None


# --- Startup: clean up orphaned files ---


@app.on_event("startup")
async def cleanup_orphaned_files():
    """Remove leftover audio/upload files from previous runs."""
    for directory, label in ((AUDIO_DIR, "audio"), (UPLOADS_DIR, "upload")):
        if directory.exists():
            count = 0
            for f in directory.iterdir():
                if f.is_file():
                    f.unlink()
                    count += 1
            if count:
                logger.info(f"Startup cleanup: removed {count} orphaned {label} file(s)")

    # Mark any jobs that were in-progress as crashed so UI can show retry
    if JOBS_DIR.exists():
        for job_file in JOBS_DIR.glob("*.json"):
            try:
                with open(job_file) as f:
                    data = json.load(f)
                if data.get("status") in ("downloading", "processing", "uploading", "transcribing", "retrying"):
                    data["status"] = "error"
                    data["error"] = "Server restarted while this job was running. Click Retry to resume."
                    data["progress"] = "Error: Server restarted"
                    with open(job_file, "w") as f:
                        json.dump(data, f, indent=2)
                    logger.info(f"Marked crashed job {data['id']} as error")
            except Exception:
                pass


# --- Config endpoints ---


@app.get("/api/config")
def get_config():
    config = load_config()
    # Mask API key for frontend display
    masked = config.copy()
    key = masked.get("soniox_api_key", "")
    if key and len(key) > 8:
        masked["soniox_api_key_masked"] = key[:4] + "..." + key[-4:]
    else:
        masked["soniox_api_key_masked"] = "Not set"
    masked["has_api_key"] = bool(key)
    del masked["soniox_api_key"]
    return masked


@app.put("/api/config")
def update_config(update: ConfigUpdate):
    config = load_config()
    for field, value in update.model_dump(exclude_none=True).items():
        config[field] = value
    save_config(config)
    return {"status": "ok"}


@app.get("/api/config/key")
def get_raw_api_key():
    """Return the full API key (for settings page edit field)."""
    config = load_config()
    return {"soniox_api_key": config.get("soniox_api_key", "")}


# --- Transcription endpoints ---


async def _stream_upload_to_disk(upload: UploadFile, dest: Path) -> None:
    with open(dest, "wb") as out:
        while True:
            chunk = await upload.read(UPLOAD_CHUNK)
            if not chunk:
                break
            out.write(chunk)


@app.post("/api/transcribe")
async def transcribe(
    youtube_url: Optional[str] = Form(None),
    language_hints: str = Form("en,hi"),
    enable_speaker_diarization: bool = Form(False),
    translate_to_english: bool = Form(False),
    cookies_file: Optional[UploadFile] = File(None),
    video_file: Optional[UploadFile] = File(None),
):
    config = load_config()
    api_key = config.get("soniox_api_key", "")
    if not api_key:
        raise HTTPException(status_code=400, detail="Soniox API key not configured. Go to Settings.")

    has_url = bool(youtube_url and youtube_url.strip())
    has_video = bool(video_file and video_file.filename)
    if not has_url and not has_video:
        raise HTTPException(status_code=400, detail="Provide either a YouTube URL or a video file.")
    if has_url and has_video:
        raise HTTPException(status_code=400, detail="Provide either a YouTube URL or a video file, not both.")

    job_id = str(uuid.uuid4())[:8]
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

    cookies_path: Path | None = None
    if cookies_file and cookies_file.filename:
        cookies_path = UPLOADS_DIR / f"{job_id}_cookies.txt"
        await _stream_upload_to_disk(cookies_file, cookies_path)

    uploaded_video_path: Path | None = None
    original_filename: str | None = None
    if has_video:
        original_filename = video_file.filename
        ext = Path(original_filename or "video.mp4").suffix or ".mp4"
        uploaded_video_path = UPLOADS_DIR / f"{job_id}_video{ext}"
        await _stream_upload_to_disk(video_file, uploaded_video_path)

    hints = [s.strip() for s in language_hints.split(",") if s.strip()] or ["en"]
    source = "youtube" if has_url else "upload"
    display_url = youtube_url.strip() if has_url else (original_filename or "Uploaded video")

    jobs[job_id] = {
        "id": job_id,
        "status": "downloading" if source == "youtube" else "processing",
        "progress": "Downloading YouTube audio..." if source == "youtube" else "Extracting audio from upload...",
        "youtube_url": display_url,
        "source": source,
        "video_info": None,
        "transcript_text": None,
        "transcript_srt": None,
        "tokens": None,
        "error": None,
        "_audio_path": None,
        "_file_id": None,
        "_cookies_path": str(cookies_path) if cookies_path else None,
        "_uploaded_video_path": str(uploaded_video_path) if uploaded_video_path else None,
        "_original_filename": original_filename,
        "_request": {
            "youtube_url": youtube_url.strip() if has_url else "",
            "language_hints": hints,
            "enable_speaker_diarization": enable_speaker_diarization,
            "translate_to_english": translate_to_english,
            "source": source,
        },
    }

    asyncio.create_task(_run_transcription(job_id, api_key))
    return {"job_id": job_id}


@app.post("/api/jobs/{job_id}/retry")
async def retry_job(job_id: str):
    """Retry a failed job, resuming from the last successful step."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found or expired")

    job = jobs[job_id]
    if job["status"] != "error":
        raise HTTPException(status_code=400, detail="Job is not in error state")

    config = load_config()
    api_key = config.get("soniox_api_key", "")
    if not api_key:
        raise HTTPException(status_code=400, detail="Soniox API key not configured. Go to Settings.")

    # Clear error state
    job["status"] = "retrying"
    job["error"] = None
    job["progress"] = "Retrying..."

    asyncio.create_task(_run_transcription(job_id, api_key))
    return {"status": "retrying"}


async def _run_transcription(job_id: str, api_key: str):
    job = jobs[job_id]
    req_data = job["_request"]
    client = SonioxTranscriber(api_key)

    # Recover state from previous attempt
    audio_path: Path | None = Path(job["_audio_path"]) if job.get("_audio_path") else None
    file_id: str | None = job.get("_file_id")
    cookies_path: Path | None = Path(job["_cookies_path"]) if job.get("_cookies_path") else None
    uploaded_video_path: Path | None = (
        Path(job["_uploaded_video_path"]) if job.get("_uploaded_video_path") else None
    )
    source = req_data.get("source", "youtube")
    transcription_id: str | None = None

    try:
        # Step 1: Get audio (download from YouTube OR transcode upload)
        if audio_path and audio_path.exists():
            logger.info(f"Job {job_id}: reusing cached audio {audio_path}")
            _update_job_status(job_id, job, "uploading", "Audio already ready, resuming...")
        elif source == "youtube":
            _update_job_status(job_id, job, "downloading", "Downloading YouTube audio...")
            audio_path, video_info = await extract_audio(
                req_data["youtube_url"],
                AUDIO_DIR,
                cookies_path=cookies_path,
            )
            job["video_info"] = video_info
            job["_audio_path"] = str(audio_path)
            _save_job(job_id, job)
            # Cookies served their purpose
            if cookies_path and cookies_path.exists():
                cookies_path.unlink(missing_ok=True)
                job["_cookies_path"] = None
        else:
            if not uploaded_video_path or not uploaded_video_path.exists():
                raise FileNotFoundError("Uploaded video file is missing — please re-upload.")
            _update_job_status(job_id, job, "processing", "Extracting audio from uploaded video...")
            title_hint = job.get("_original_filename") or "Uploaded video"
            audio_path, video_info = await transcode_to_mp3(
                uploaded_video_path, AUDIO_DIR, job_id, display_title=title_hint,
            )
            job["video_info"] = video_info
            job["_audio_path"] = str(audio_path)
            _save_job(job_id, job)
            # Source video no longer needed
            uploaded_video_path.unlink(missing_ok=True)
            job["_uploaded_video_path"] = None

        # Step 2: Upload to Soniox (skip if already uploaded)
        if file_id:
            logger.info(f"Job {job_id}: reusing uploaded file {file_id}")
            _update_job_status(job_id, job, "transcribing", "File already uploaded, resuming transcription...")
        else:
            _update_job_status(job_id, job, "uploading", "Uploading audio to Soniox...")
            file_id = await client.upload_file(audio_path)
            job["_file_id"] = file_id

        # Step 3: Create transcription
        _update_job_status(job_id, job, "transcribing", "Transcribing audio (this may take a few minutes)...")
        transcription_id = await client.create_transcription(
            file_id=file_id,
            language_hints=req_data["language_hints"],
            enable_diarization=req_data["enable_speaker_diarization"],
            translate_to_english=req_data["translate_to_english"],
        )

        # Step 4: Wait for completion
        await client.wait_for_transcription(transcription_id)

        # Step 5: Get transcript
        _update_job_status(job_id, job, "transcribing", "Fetching transcript...")
        transcript = await client.get_transcript(transcription_id)
        tokens = transcript.get("tokens", [])

        job["tokens"] = tokens
        job["transcript_text"] = tokens_to_text(tokens, include_speakers=req_data["enable_speaker_diarization"])
        job["transcript_srt"] = tokens_to_srt(tokens)
        _update_job_status(job_id, job, "completed", "Done!")

        # Cleanup on success
        if audio_path and audio_path.exists():
            audio_path.unlink(missing_ok=True)
        job["_audio_path"] = None
        if file_id:
            await client.delete_file(file_id)
            job["_file_id"] = None
        if transcription_id:
            await client.delete_transcription(transcription_id)
        if cookies_path and cookies_path.exists():
            cookies_path.unlink(missing_ok=True)
            job["_cookies_path"] = None
        if uploaded_video_path and uploaded_video_path.exists():
            uploaded_video_path.unlink(missing_ok=True)
            job["_uploaded_video_path"] = None

    except Exception as e:
        logger.exception(f"Job {job_id} failed")
        job["error"] = str(e)
        _update_job_status(job_id, job, "error", f"Error: {e}")
        # On error: keep audio/cookies/uploaded video so retry can resume.
        # Only clean up the failed transcription.
        if transcription_id:
            await client.delete_transcription(transcription_id)


def _save_job(job_id: str, job: dict):
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    job_file = JOBS_DIR / f"{job_id}.json"
    # Save without internal/large fields
    save_data = {k: v for k, v in job.items() if not k.startswith("_") and k != "tokens"}
    with open(job_file, "w") as f:
        json.dump(save_data, f, indent=2)


def _update_job_status(job_id: str, job: dict, status: str, progress: str):
    """Update job status and persist to disk immediately."""
    job["status"] = status
    job["progress"] = progress
    _save_job(job_id, job)


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    if job_id in jobs:
        job = jobs[job_id]
        return {k: v for k, v in job.items() if not k.startswith("_") and k != "tokens"}
    # Try loading from disk
    job_file = JOBS_DIR / f"{job_id}.json"
    if job_file.exists():
        with open(job_file) as f:
            return json.load(f)
    raise HTTPException(status_code=404, detail="Job not found")


@app.get("/api/jobs/{job_id}/download/txt", response_class=PlainTextResponse)
def download_txt(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found or expired")
    job = jobs[job_id]
    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail="Transcription not complete")
    return PlainTextResponse(
        content=job["transcript_text"],
        headers={"Content-Disposition": f'attachment; filename="transcript_{job_id}.txt"'},
    )


@app.get("/api/jobs/{job_id}/download/srt", response_class=PlainTextResponse)
def download_srt(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found or expired")
    job = jobs[job_id]
    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail="Transcription not complete")
    return PlainTextResponse(
        content=job["transcript_srt"],
        headers={"Content-Disposition": f'attachment; filename="transcript_{job_id}.srt"'},
    )


@app.get("/api/jobs")
def list_jobs():
    """List recent jobs from memory and disk."""
    all_jobs = []
    for job in jobs.values():
        all_jobs.append({k: v for k, v in job.items() if not k.startswith("_") and k not in ("tokens", "transcript_text", "transcript_srt")})
    return {"jobs": all_jobs}


@app.get("/api/jobs/active/latest")
def get_active_job():
    """Get the most recent non-completed job (for restoring UI on page refresh)."""
    # Check in-memory jobs first
    for job in reversed(list(jobs.values())):
        if job["status"] not in ("completed",):
            return {k: v for k, v in job.items() if not k.startswith("_") and k != "tokens"}
    # Check disk for recently active jobs
    if JOBS_DIR.exists():
        job_files = sorted(JOBS_DIR.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
        for jf in job_files[:10]:
            with open(jf) as f:
                data = json.load(f)
            if data.get("status") not in ("completed",):
                return data
    return None


@app.get("/api/health")
def health():
    return {"status": "ok"}
