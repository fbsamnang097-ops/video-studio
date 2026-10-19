import os
import shutil
import tempfile

import yt_dlp
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask

app = FastAPI()

MAX_HEIGHT = int(os.getenv("MAX_HEIGHT", "720"))
COOKIES_SRC = "/etc/secrets/cookies.txt"  # Render Secret File


class Req(BaseModel):
    url: str


def make_opts(outdir: str) -> dict:
    h = MAX_HEIGHT
    opts = {
        "format": f"b[height<={h}][ext=mp4]/bv*[height<={h}]+ba/b[height<={h}]/b",
        "merge_output_format": "mp4",
        "outtmpl": os.path.join(outdir, "%(title).80s.%(ext)s"),
        "retries": 5,
        "noplaylist": True,
        "quiet": True,
    }
    if os.path.exists(COOKIES_SRC):
        dst = "/tmp/cookies.txt"
        shutil.copy(COOKIES_SRC, dst)
        opts["cookiefile"] = dst
    elif os.path.exists("cookies.txt"):
        opts["cookiefile"] = "cookies.txt"
    if os.getenv("PROXY_URL"):
        opts["proxy"] = os.getenv("PROXY_URL")
    return opts


@app.post("/api/download")
def download(req: Req):
    if not req.url.startswith(("http://", "https://")):
        raise HTTPException(400, "URL មិនត្រឹមត្រូវ (ត្រូវចាប់ផ្តើមដោយ https://)")
    outdir = tempfile.mkdtemp(prefix="dl_")
    try:
        with yt_dlp.YoutubeDL(make_opts(outdir)) as ydl:
            ydl.download([req.url])
        files = os.listdir(outdir)
        if not files:
            raise RuntimeError("មិនមានឯកសារ")
        path = os.path.join(outdir, files[0])
        return FileResponse(
            path,
            filename=files[0],
            background=BackgroundTask(shutil.rmtree, outdir, True),
        )
    except Exception as e:
        shutil.rmtree(outdir, ignore_errors=True)
        raise HTTPException(500, str(e)[-500:])


@app.get("/health")
def health():
    return {"ok": True, "yt_dlp": yt_dlp.version.__version__}


PAGE = """<!doctype html><html lang="km"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Video Downloader</title>
<style>
body{font-family:system-ui,sans-serif;max-width:560px;margin:60px auto;padding:0 16px}
input{width:100%;padding:12px;font-size:16px;box-sizing:border-box}
button{margin-top:12px;padding:12px 20px;font-size:16px;cursor:pointer}
#msg{margin-top:16px;white-space:pre-wrap}
</style></head><body>
<h2>ដោនឡូតវីដេអូ</h2>
<input id="u" placeholder="បិទភ្ជាប់ link YouTube / TikTok / Instagram ...">
<button id="b" onclick="go()">ដោនឡូត</button>
<div id="msg"></div>
<script>
async function go(){
  const m=document.getElementById('msg'), b=document.getElementById('b');
  const url=document.getElementById('u').value.trim();
  if(!url){m.textContent='សូមបញ្ចូល link';return}
  b.disabled=true; m.textContent='កំពុងដោនឡូត... សូមរង់ចាំ';
  try{
    const r=await fetch('/api/download',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url})});
    if(!r.ok){const e=await r.json().catch(()=>({}));throw new Error(e.detail||r.statusText)}
    let name='video.mp4';
    const cd=r.headers.get('content-disposition')||'';
    const mm=cd.match(/filename\\*=utf-8''([^;]+)/i); if(mm) name=decodeURIComponent(mm[1]);
    const blob=await r.blob();
    const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download=name; a.click();
    m.textContent='✅ រួចរាល់';
  }catch(e){m.textContent='❌ '+e.message}
  b.disabled=false;
}
</script></body></html>"""


@app.get("/", response_class=HTMLResponse)
def index():
    return PAGE
