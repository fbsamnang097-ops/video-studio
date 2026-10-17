# Video Studio (Electron + React + Python)

## Architecture
```
video-studio/
├─ electron/main.js        # Starts the Python backend, waits for /health, opens the window
├─ src/                    # React UI (Vite)
│  ├─ App.jsx              # URL input, quality select, progress, player, transcript, TXT export
│  ├─ api.js               # fetch helpers + job polling
│  └─ styles.css           # Light/dark theme tokens
├─ backend/                # FastAPI on 127.0.0.1:8765
│  ├─ main.py              # REST endpoints (/info /download /transcribe /jobs /media)
│  ├─ downloader.py        # yt-dlp: metadata, quality formats, progress hooks
│  ├─ transcriber.py       # ffmpeg -> faster-whisper -> pyannote -> speaker-labelled lines
│  ├─ translator.py        # transcript -> Khmer/English/Thai/Vietnamese (Google Translate, needs internet)
│  └─ jobs.py              # in-memory job store
└─ package.json, vite.config.js, index.html
```
Flow: React -> HTTP -> FastAPI -> background thread -> job status polled every 600 ms.
Downloaded files are served back through `/media/{job}` so the `<video>` player can seek.

## Setup
**Prerequisites:** Node 18+, Python 3.10–3.11, [ffmpeg](https://ffmpeg.org/download.html) on your PATH.

**Backend**
```bash
cd backend
python -m venv .venv
# macOS/Linux: source .venv/bin/activate     Windows: .venv\Scripts\activate
pip install -r requirements.txt
```
For GPU, install the CUDA build of PyTorch first (https://pytorch.org/get-started/locally/).

**Speaker diarization access (one-time):**
1. Create a free Hugging Face account and an access token (Settings > Access Tokens).
2. Accept the terms on both model pages: `pyannote/speaker-diarization-3.1` and `pyannote/segmentation-3.0`.
3. Paste the token into the app's "Hugging Face token" field (kept in local storage).

**Frontend**
```bash
npm install
npm run dev      # Vite + Electron (Electron launches the backend from backend/.venv)
npm start        # production-style run from the built dist/
```
Set `PYTHON_BIN=/path/to/python` if your venv lives elsewhere.

## Notes
- Translation (default Khmer) uses offline NLLB-200 (free, unlimited; one-time model download) or Google (online, rate-limited); subtitles on the video can show original, translation, or both.
- Videos save to `~/Downloads/VideoStudio`. Whisper models download on first use.
- Pre-download preview works only when the site offers a direct MP4 stream; otherwise play it after downloading.
- Without a Hugging Face token the transcript is produced without speaker labels.
- Keep yt-dlp current (`pip install -U yt-dlp`), since sites change often.
- Download only content you have the right to save.
- To ship installers: bundle the backend with PyInstaller and package with electron-builder.
