import asyncio
import json
import logging
import os
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from config import load_config, save_config
from soniox_client import SonioxTranscriber
from transcript_formatter import tokens_to_srt, tokens_to_text
from youtube import extract_audio

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

# In-memory job tracking
jobs: dict[str, dict] = {}


class TranscribeRequest(BaseModel):
    youtube_url: str
    language_hints: list[str] = ["en", "hi"]
    enable_speaker_diarization: bool = False
    translate_to_english: bool = False


class ConfigUpdate(BaseModel):
    soniox_api_key: str | None = None
    default_language: str | None = None
    enable_speaker_diarization: bool | None = None
    translation_mode: str | None = None


# --- Startup: clean up orphaned audio files ---


@app.on_event("startup")
async def cleanup_orphaned_audio():
    """Remove any leftover audio files from previous runs."""
    if AUDIO_DIR.exists():
        count = 0
        for f in AUDIO_DIR.iterdir():
            if f.is_file():
                f.unlink()
                count += 1
        if count:
            logger.info(f"Startup cleanup: removed {count} orphaned audio file(s)")

    # Mark any jobs that were in-progress as crashed so UI can show retry
    if JOBS_DIR.exists():
        for job_file in JOBS_DIR.glob("*.json"):
            try:
                with open(job_file) as f:
                    data = json.load(f)
                if data.get("status") in ("downloading", "uploading", "transcribing", "retrying"):
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


@app.post("/api/transcribe")
async def transcribe(req: TranscribeRequest):
    config = load_config()
    api_key = config.get("soniox_api_key", "")
    if not api_key:
        raise HTTPException(status_code=400, detail="Soniox API key not configured. Go to Settings.")

    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "id": job_id,
        "status": "downloading",
        "progress": "Downloading YouTube audio...",
        "youtube_url": req.youtube_url,
        "video_info": None,
        "transcript_text": None,
        "transcript_srt": None,
        "tokens": None,
        "error": None,
        # Internal state for retry
        "_audio_path": None,
        "_file_id": None,
        "_request": req.model_dump(),
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
    transcription_id: str | None = None

    try:
        # Step 1: Download audio (skip if already downloaded)
        if audio_path and audio_path.exists():
            logger.info(f"Job {job_id}: reusing cached audio {audio_path}")
            _update_job_status(job_id, job, "uploading", "Audio already downloaded, resuming...")
        else:
            _update_job_status(job_id, job, "downloading", "Downloading YouTube audio...")
            audio_path, video_info = await extract_audio(req_data["youtube_url"], AUDIO_DIR)
            job["video_info"] = video_info
            job["_audio_path"] = str(audio_path)
            _save_job(job_id, job)

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

        # Cleanup on success: remove audio and soniox resources
        if audio_path and audio_path.exists():
            audio_path.unlink(missing_ok=True)
        job["_audio_path"] = None
        if file_id:
            await client.delete_file(file_id)
            job["_file_id"] = None
        if transcription_id:
            await client.delete_transcription(transcription_id)

    except Exception as e:
        logger.exception(f"Job {job_id} failed")
        job["error"] = str(e)
        _update_job_status(job_id, job, "error", f"Error: {e}")
        # On error: keep audio_path and file_id so retry can resume
        # Only clean up the failed transcription
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
