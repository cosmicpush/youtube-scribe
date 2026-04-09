# ============================================
# Stage 1: Build Next.js frontend
# ============================================
FROM node:22-alpine AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ============================================
# Stage 2: Final image — Python + Node runtime
# ============================================
FROM python:3.13-slim

# Install Node.js (for Next.js standalone server) and ffmpeg (for yt-dlp)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    ffmpeg \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy backend source
COPY backend/ ./backend/

# Copy Next.js standalone build
COPY --from=frontend-builder /app/frontend/.next/standalone ./frontend/
COPY --from=frontend-builder /app/frontend/.next/static ./frontend/.next/static
COPY --from=frontend-builder /app/frontend/public ./frontend/public

# Create data directory
RUN mkdir -p /app/data

# Copy startup script
COPY start.sh ./start.sh
RUN chmod +x ./start.sh

ENV DATA_DIR=/app/data
ENV NODE_ENV=production

EXPOSE 3000 8000

CMD ["./start.sh"]
