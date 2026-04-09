# YouTube Scribe

Transcribe YouTube videos using [Soniox](https://soniox.com) speech AI. Supports English, Hindi, and mixed-language lectures with speaker diarization and translation.

## Features

- Paste a YouTube link and get a full transcript
- English, Hindi, and English+Hindi language support
- Optional speaker diarization (label different speakers)
- Optional translation to English
- Download transcripts as `.txt` or `.srt` (subtitles)
- Light / Dark / System theme
- Persistent settings via JSON config (Docker volume)

## Quick Start (Docker)

```bash
docker pull ghcr.io/cosmicpush/youtube-scribe:latest

docker run -d \
  -p 3000:3000 \
  -p 8000:8000 \
  -v transcriber-data:/app/data \
  ghcr.io/cosmicpush/youtube-scribe:latest
```

Open [http://localhost:3000](http://localhost:3000) and configure your Soniox API key in Settings.

### Docker Compose

```bash
docker compose up -d
```

## Get a Soniox API Key

1. Go to [console.soniox.com](https://console.soniox.com)
2. Create an account and get your API key
3. Enter it in the Settings page of the app

## Architecture

```
├── frontend/       # Next.js + shadcn/ui + Tailwind
├── backend/        # FastAPI + yt-dlp + Soniox API client
├── Dockerfile      # Multi-stage build (single container)
├── docker-compose.yml
└── .github/workflows/docker-build.yml  # CI → ghcr.io
```

**Ports:**
- `3000` — Web UI (Next.js)
- `8000` — API (FastAPI)

**Persistence:** Mount `/app/data` as a volume to persist your API key and transcription history.

## Local Development

### Backend
```bash
cd backend
pip install -r requirements.txt
DATA_DIR=../data uvicorn main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```
