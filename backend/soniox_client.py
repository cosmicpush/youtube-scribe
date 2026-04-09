import httpx
import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

SONIOX_API_BASE = "https://api.soniox.com/v1"


class SonioxTranscriber:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
        }

    async def upload_file(self, file_path: Path) -> str:
        """Upload audio file to Soniox and return file_id."""
        async with httpx.AsyncClient(timeout=300) as client:
            with open(file_path, "rb") as f:
                resp = await client.post(
                    f"{SONIOX_API_BASE}/files",
                    headers=self.headers,
                    files={"file": (file_path.name, f, "audio/mpeg")},
                )
            resp.raise_for_status()
            data = resp.json()
            logger.info(f"Uploaded file: {data['id']}")
            return data["id"]

    async def create_transcription(
        self,
        file_id: str,
        language_hints: list[str],
        enable_diarization: bool = False,
        translate_to_english: bool = False,
    ) -> str:
        """Create a transcription job and return transcription_id."""
        body: dict = {
            "model": "stt-async-v4",
            "file_id": file_id,
            "language_hints": language_hints,
            "enable_speaker_diarization": enable_diarization,
            "enable_language_identification": True,
        }
        if translate_to_english:
            body["translation"] = {
                "type": "one_way",
                "target_language": "en",
            }

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{SONIOX_API_BASE}/transcriptions",
                headers={**self.headers, "Content-Type": "application/json"},
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()
            logger.info(f"Created transcription: {data['id']}")
            return data["id"]

    async def wait_for_transcription(
        self, transcription_id: str, poll_interval: float = 3.0, max_wait: float = 1800
    ) -> dict:
        """Poll until transcription completes or fails."""
        elapsed = 0.0
        async with httpx.AsyncClient(timeout=30) as client:
            while elapsed < max_wait:
                resp = await client.get(
                    f"{SONIOX_API_BASE}/transcriptions/{transcription_id}",
                    headers=self.headers,
                )
                resp.raise_for_status()
                data = resp.json()
                status = data.get("status")
                logger.info(f"Transcription {transcription_id} status: {status}")
                if status == "completed":
                    return data
                if status == "error":
                    error_msg = data.get("error_message", "Unknown error")
                    error_type = data.get("error_type", "unknown")
                    raise Exception(f"Soniox error ({error_type}): {error_msg}")
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval
        raise TimeoutError(f"Transcription did not complete within {max_wait}s")

    async def get_transcript(self, transcription_id: str) -> dict:
        """Get the completed transcript with tokens."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{SONIOX_API_BASE}/transcriptions/{transcription_id}/transcript",
                headers=self.headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def delete_file(self, file_id: str):
        """Clean up uploaded file."""
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                await client.delete(
                    f"{SONIOX_API_BASE}/files/{file_id}",
                    headers=self.headers,
                )
                logger.info(f"Deleted file: {file_id}")
        except Exception as e:
            logger.warning(f"Failed to delete file {file_id}: {e}")

    async def delete_transcription(self, transcription_id: str):
        """Clean up transcription."""
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                await client.delete(
                    f"{SONIOX_API_BASE}/transcriptions/{transcription_id}",
                    headers=self.headers,
                )
                logger.info(f"Deleted transcription: {transcription_id}")
        except Exception as e:
            logger.warning(f"Failed to delete transcription {transcription_id}: {e}")
