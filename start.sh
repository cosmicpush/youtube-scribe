#!/bin/sh
set -e

echo "Starting YouTube Scribe..."

# Start FastAPI backend
cd /app/backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# Start Next.js frontend
cd /app/frontend
node server.js &
FRONTEND_PID=$!

echo "Backend running on :8000"
echo "Frontend running on :3000"

# Wait for both — if either exits, the container stops
wait $BACKEND_PID $FRONTEND_PID
