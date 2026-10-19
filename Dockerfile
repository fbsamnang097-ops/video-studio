# ---- 1) build the React app ----
FROM node:20-slim AS web
ENV ELECTRON_SKIP_BINARY_DOWNLOAD=1
WORKDIR /web
COPY package.json ./
RUN npm install --no-audit --no-fund
COPY index.html vite.config.js ./
COPY src ./src
RUN npx vite build

# ---- 2) Python server (serves the API and the built app) ----
FROM python:3.11-slim
# Change to 1 to include Whisper + speaker detection (needs a plan with 2 GB+ RAM)
ARG WITH_AI=1
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg curl unzip ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL https://deno.land/install.sh | DENO_INSTALL=/usr/local sh
WORKDIR /app
COPY backend/requirements-web.txt backend/requirements-ai.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements-web.txt
RUN if [ "$WITH_AI" = "1" ]; then \
      pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -r backend/requirements-ai.txt; \
    fi
COPY backend ./backend
COPY --from=web /web/dist ./dist
ENV STATIC_DIR=/app/dist DOWNLOAD_DIR=/tmp/videostudio CLEANUP_HOURS=2 PYTHONUNBUFFERED=1
CMD ["sh", "-c", "python backend/main.py --host 0.0.0.0 --port ${PORT:-10000}"]
