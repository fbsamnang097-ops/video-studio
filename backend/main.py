import argparse, ipaddress, os, secrets, socket, threading, time
from pathlib import Path
from urllib.parse import urlparse

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import downloader, transcriber, translator
from jobs import JOBS, new_job

app = FastAPI(title="Video Studio backend")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

OUT_DIR = os.environ.get("DOWNLOAD_DIR") or str(Path.home() / "Downloads" / "VideoStudio")
PASSWORD = os.environ.get("APP_PASSWORD")                     # set on a public server
CLEANUP_HOURS = float(os.environ.get("CLEANUP_HOURS", "0"))   # >0: delete old downloads (cloud)
PROTECTED = ("/info", "/download", "/transcribe", "/translate", "/jobs", "/media", "/files", "/config")

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
    if req.engine == "google":
        threading.Thread(target=translator.run, args=(job_id, texts, req.target), daemon=True).start()
    else:
        lang = src["result"].get("language")
        threading.Thread(target=translator.run_nllb, args=(job_id, texts, req.target, lang), daemon=True).start()
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
