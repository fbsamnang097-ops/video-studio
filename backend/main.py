import argparse, threading
from pathlib import Path
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

import downloader, transcriber, translator
from jobs import JOBS, new_job

app = FastAPI(title="Video Studio backend")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
OUT_DIR = str(Path.home() / "Downloads" / "VideoStudio")

class UrlReq(BaseModel):
    url: str

class DownloadReq(UrlReq):
    quality: str = "720"          # "1080" | "720" | "480" | ... | "audio"

class TranscribeReq(BaseModel):
    job_id: str                   # the finished download job
    hf_token: str | None = None
    model: str = "small"
    num_speakers: int | None = None
    language: str | None = None

class TranslateReq(BaseModel):
    job_id: str                   # the finished transcript job
    target: str = "km"            # km | en | th | vi | zh-CN ...
    engine: str = "nllb"          # "nllb" (offline, unlimited) | "google" (online, rate-limited)

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

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/info")
def info(req: UrlReq):
    try:
        return downloader.fetch_info(req.url)
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/download")
def download(req: DownloadReq):
    job_id = new_job("download")
    threading.Thread(target=downloader.download,
                     args=(job_id, req.url, req.quality, OUT_DIR), daemon=True).start()
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

@app.get("/jobs/{job_id}")
def job(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(404, "Unknown job")
    return JOBS[job_id]

@app.get("/media/{job_id}")
def media(job_id: str):
    f = JOBS.get(job_id, {}).get("file")
    if not f or not Path(f).exists():
        raise HTTPException(404, "File not found")
    return FileResponse(f)   # Starlette serves HTTP Range requests, so seeking works

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--out", default=OUT_DIR)
    a = ap.parse_args()
    OUT_DIR = a.out
    uvicorn.run(app, host="127.0.0.1", port=a.port, log_level="warning")
