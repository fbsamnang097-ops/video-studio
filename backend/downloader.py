"""yt-dlp wrapper: metadata lookup + downloads with resolution selection."""
import os, tempfile
from pathlib import Path
from yt_dlp import YoutubeDL
from jobs import update

def _extra_opts() -> dict:
    """Optional env settings for servers whose IPs get blocked by some sites (e.g. YouTube)."""
    o = {}
    cookies = os.environ.get("YT_COOKIES")          # contents of a Netscape cookies.txt
    if cookies:
        path = os.path.join(tempfile.gettempdir(), "yt_cookies.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(cookies)
        o["cookiefile"] = path
    if os.environ.get("YTDLP_PROXY"):
        o["proxy"] = os.environ["YTDLP_PROXY"]
    return o

def fetch_info(url: str) -> dict:
    opts = {"quiet": True, "noplaylist": True, "skip_download": True, **_extra_opts()}
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    formats = info.get("formats") or []
    heights = sorted({f["height"] for f in formats
                      if f.get("height") and f.get("vcodec") not in (None, "none")},
                     reverse=True)

    # A progressive (video+audio in one file) HTTP stream lets us preview before downloading.
    progressive = [f for f in formats
                   if f.get("vcodec") not in (None, "none")
                   and f.get("acodec") not in (None, "none")
                   and str(f.get("protocol", "")).startswith("http")
                   and f.get("ext") == "mp4"]
    progressive.sort(key=lambda f: f.get("height") or 0)
    preview_url = progressive[-1]["url"] if progressive else None

    return {
        "title": info.get("title"),
        "uploader": info.get("uploader"),
        "duration": info.get("duration"),
        "thumbnail": info.get("thumbnail"),
        "heights": heights,
        "preview_url": preview_url,
    }

def _format_for(quality: str) -> str:
    if quality == "audio":
        return "bestaudio/best"
    h = int(quality)
    return f"bestvideo[height<={h}]+bestaudio/best[height<={h}]/best"

def download(job_id: str, url: str, quality: str, out_dir: str):
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    def hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            pct = d.get("downloaded_bytes", 0) / total * 100 if total else 0
            update(job_id, status="downloading", stage="Downloading",
                   percent=round(pct, 1),
                   speed=(d.get("_speed_str") or "").strip(),
                   eta=(d.get("_eta_str") or "").strip())
        elif d["status"] == "finished":
            update(job_id, status="processing", stage="Merging / converting", percent=100)

    opts = {
        "format": _format_for(quality),
        "outtmpl": str(Path(out_dir) / "%(title).150B [%(id)s].%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "progress_hooks": [hook],
        "merge_output_format": "mp4",
    }
    opts.update(_extra_opts())
    if quality == "audio":
        opts["postprocessors"] = [{"key": "FFmpegExtractAudio",
                                   "preferredcodec": "mp3", "preferredquality": "192"}]
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            path = info["requested_downloads"][0]["filepath"]
        update(job_id, status="done", stage="Finished", percent=100, file=path)
    except Exception as e:  # surface a readable message to the UI
        update(job_id, status="error", error=str(e))
