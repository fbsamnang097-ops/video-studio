"""Tiny in-memory job store shared by the downloader and the transcriber."""
import threading, uuid

JOBS: dict[str, dict] = {}
_lock = threading.Lock()

def new_job(kind: str) -> str:
    job_id = uuid.uuid4().hex[:12]
    with _lock:
        JOBS[job_id] = {"id": job_id, "kind": kind, "status": "queued",
                        "stage": "", "percent": 0, "speed": "", "eta": "",
                        "file": None, "result": None, "error": None}
    return job_id

def update(job_id: str, **fields):
    with _lock:
        JOBS[job_id].update(fields)
