import argparse, ipaddress, os, secrets, shutil, socket, subprocess, threading, time
from pathlib import Path
from urllib.parse import urlparse

import uvicorn
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import downloader, transcriber, translator
from jobs import JOBS, new_job, update as job_update

app = FastAPI(title="Video Studio backend")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

OUT_DIR = os.environ.get("DOWNLOAD_DIR") or str(Path.home() / "Downloads" / "VideoStudio")
PASSWORD = os.environ.get("APP_PASSWORD")                     # set on a public server
CLEANUP_HOURS = float(os.environ.get("CLEANUP_HOURS", "0"))   # >0: delete old downloads (cloud)
PROTECTED = ("/info", "/upload", "/download", "/transcribe", "/translate", "/convert", "/jobs", "/media", "/files", "/config")

@app.middleware("http")
async def require_password(request: Request, call_next):
    p = request.url.path
    if PASSWORD and request.method != "OPTIONS" and p.startswith(PROTECTED):
        key = request.headers.get("x-app-key") or request.query_params.get("key") or ""
        if not secrets.compare_digest(key, PASSWORD):
            return JSONResponse({"detail": "Wrong or missing password"}, status_code=401)
    return await call_next(request)

def check_url(url: str):
    """Only public http(s) links: stops the server being used to reach internal addresses."""
    u = urlparse(url.strip())
    if u.scheme not in ("http", "https") or not u.hostname:
        raise HTTPException(400, "Please paste a full http(s) link.")
    try:
        for fam, _, _, _, addr in socket.getaddrinfo(u.hostname, None):
            ip = ipaddress.ip_address(addr[0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                raise HTTPException(400, "That address is not allowed.")
    except socket.gaierror:
        raise HTTPException(400, "Could not resolve that address.")

class UrlReq(BaseModel):
    url: str

class DownloadReq(UrlReq):
    quality: str = "720"          # "1080" | "720" | "480" | ... | "audio"
    out_dir: str | None = None    # desktop only: folder chosen in the app

class TranscribeReq(BaseModel):
    job_id: str                   # the finished download job
    hf_token: str | None = None
    model: str = "small"
    num_speakers: int | None = None
    language: str | None = None

class TranslateReq(BaseModel):
    job_id: str                   # the finished transcript job
    target: str = "km"            # km | en | th | vi | zh-CN ...
    engine: str = "nllb"          # "nllb" (offline) | "google" (online, rate-limited)

@app.get("/config")
def config():
    return {"out_dir": OUT_DIR}

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/info")
def info(req: UrlReq):
    check_url(req.url)
    try:
        return downloader.fetch_info(req.url)
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/download")
def download(req: DownloadReq):
    check_url(req.url)
    # On a public server the folder is always the server's own temp folder
    out_dir = OUT_DIR if PASSWORD or CLEANUP_HOURS else (req.out_dir or OUT_DIR)
    job_id = new_job("download")
    threading.Thread(target=downloader.download,
                     args=(job_id, req.url, req.quality, out_dir), daemon=True).start()
    return {"job_id": job_id}

UPLOAD_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".3gp",
               ".mp3", ".m4a", ".wav", ".aac", ".ogg", ".flac"}
# 0 = unlimited (default). Set the MAX_UPLOAD_MB env var to cap uploads, e.g. on a small web server.
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "0"))

@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in UPLOAD_EXTS:
        raise HTTPException(400, "Unsupported file type. Use a video or audio file (mp4, mov, mkv, webm, mp3, m4a, wav).")
    Path(OUT_DIR).mkdir(parents=True, exist_ok=True)
    dest = Path(OUT_DIR) / ("upload_" + secrets.token_hex(6) + ext)
    limit = MAX_UPLOAD_MB * 1024 * 1024
    size = 0
    try:
        with open(dest, "wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if limit and size > limit:
                    raise HTTPException(413, "File is too large (max %d MB)." % MAX_UPLOAD_MB)
                out.write(chunk)
    except HTTPException:
        dest.unlink(missing_ok=True)
        raise
    job_id = new_job("upload")
    JOBS[job_id]["file"] = str(dest)
    JOBS[job_id]["status"] = "done"
    JOBS[job_id]["stage"] = "Uploaded"
    JOBS[job_id]["percent"] = 100
    return {"job_id": job_id, "name": file.filename}

@app.post("/transcribe")
def transcribe(req: TranscribeReq):
    src = JOBS.get(req.job_id)
    if not src or not src.get("file"):
        raise HTTPException(400, "Download the video first.")
    job_id = new_job("transcribe")
    threading.Thread(target=transcriber.run,
                     args=(job_id, src["file"], req.hf_token, req.model,
                           req.num_speakers, req.language), daemon=True).start()
    return {"job_id": job_id}

@app.post("/translate")
def translate(req: TranslateReq):
    src = JOBS.get(req.job_id)
    if not src or not src.get("result"):
        raise HTTPException(400, "Generate a transcript first.")
    texts = [seg["text"] for seg in src["result"]["segments"]]
    job_id = new_job("translate")
    import importlib.util
    use_nllb = req.engine == "nllb" and importlib.util.find_spec("transformers") is not None
    if not use_nllb:
        threading.Thread(target=translator.run, args=(job_id, texts, req.target), daemon=True).start()
    else:
        lang = src["result"].get("language")
        threading.Thread(target=translator.run_nllb, args=(job_id, texts, req.target, lang), daemon=True).start()
    return {"job_id": job_id}

class ConvertReq(BaseModel):
    job_id: str
    bitrate: str = "192k"

def _run_convert(job_id: str, src: str, bitrate: str):
    try:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise RuntimeError("FFmpeg is not available.")
        s = Path(src)
        dst = s.with_suffix(".mp3")
        n = 1
        while dst.exists():
            dst = s.with_name(f"{s.stem} ({n}).mp3")
            n += 1
        job_update(job_id, status="running", stage="Converting to MP3", percent=10)
        r = subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-n", "-i", str(s),
             "-vn", "-codec:a", "libmp3lame", "-b:a", bitrate, str(dst)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if r.returncode != 0 or not dst.exists():
            dst.unlink(missing_ok=True)
            raise RuntimeError((r.stderr or "FFmpeg failed").strip()[-400:])
        job_update(job_id, status="done", stage="Converted", percent=100, file=str(dst))
    except Exception as e:
        job_update(job_id, status="error", stage="Failed", error=str(e))

@app.post("/convert")
def convert(req: ConvertReq):
    src = JOBS.get(req.job_id)
    f = src.get("file") if src else None
    if not f or not Path(f).is_file():
        raise HTTPException(400, "Download the video first.")
    if Path(f).suffix.lower() == ".mp3":
        raise HTTPException(400, "This file is already an MP3.")
    if req.bitrate not in ("128k", "192k", "256k", "320k"):
        raise HTTPException(400, "Unsupported bitrate.")
    if not shutil.which("ffmpeg"):
        raise HTTPException(400, "FFmpeg is not available on this server.")
    job_id = new_job("convert")
    threading.Thread(target=_run_convert, args=(job_id, f, req.bitrate), daemon=True).start()
    return {"job_id": job_id}


@app.get("/jobs/{job_id}")
def job(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(404, "Unknown job (the server may have restarted).")
    return JOBS[job_id]

def _file(job_id: str) -> str:
    f = JOBS.get(job_id, {}).get("file")
    if not f or not Path(f).exists():
        raise HTTPException(404, "File not found (it may have been cleaned up).")
    return f

@app.get("/media/{job_id}")           # inline playback in the <video> player
def media(job_id: str):
    return FileResponse(_file(job_id))   # Starlette serves Range requests, so seeking works

@app.get("/files/{job_id}")           # "Download file" button in the browser
def files(job_id: str):
    f = _file(job_id)
    return FileResponse(f, filename=Path(f).name)

def _cleanup_loop():
    while True:
        time.sleep(600)
        cutoff = time.time() - CLEANUP_HOURS * 3600
        for p in Path(OUT_DIR).glob("*"):
            try:
                if p.is_file() and p.stat().st_mtime < cutoff:
                    p.unlink()
            except OSError:
                pass

# Serve the built React app when deployed as one service (Docker/Render)
STATIC_DIR = os.environ.get("STATIC_DIR")
if STATIC_DIR and Path(STATIC_DIR).exists():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="web")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8765)))
    ap.add_argument("--out", default=OUT_DIR)
    a = ap.parse_args()
    OUT_DIR = a.out
    Path(OUT_DIR).mkdir(parents=True, exist_ok=True)
    if CLEANUP_HOURS > 0:
        threading.Thread(target=_cleanup_loop, daemon=True).start()
    uvicorn.run(app, host=a.host, port=a.port, log_level="warning")

