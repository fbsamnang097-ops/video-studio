"""Speech-to-text (faster-whisper) + speaker diarization (pyannote) -> speaker-labelled transcript."""
import subprocess, tempfile, os
from jobs import update

def _device():
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"

def _ts(sec: float) -> str:
    sec = int(sec)
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"

def _extract_audio(src: str, dst: str):
    subprocess.run(["ffmpeg", "-y", "-i", src, "-ac", "1", "-ar", "16000", "-vn", dst],
                   check=True, capture_output=True)

def _diarize(wav: str, hf_token: str, num_speakers: int | None):
    try:
        from pyannote.audio import Pipeline
    except ImportError:
        return []
    import torch
    pipe = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", use_auth_token=hf_token)
    if _device() == "cuda":
        pipe.to(torch.device("cuda"))
    diar = pipe(wav, num_speakers=num_speakers) if num_speakers else pipe(wav)
    turns = [(t.start, t.end, spk) for t, _, spk in diar.itertracks(yield_label=True)]
    # Rename SPEAKER_00 -> Speaker 1 in order of first appearance
    names = {}
    for _, _, spk in sorted(turns):
        names.setdefault(spk, f"Speaker {len(names) + 1}")
    return [(s, e, names[spk]) for s, e, spk in turns]

def _speaker_at(turns, start, end):
    """Speaker whose turns overlap the [start, end] window the most."""
    best, best_ov = None, 0.0
    for s, e, spk in turns:
        ov = min(e, end) - max(s, start)
        if ov > best_ov:
            best, best_ov = spk, ov
    return best

def _load_wav(path):
    """Read the 16 kHz mono WAV directly so faster-whisper does not need PyAV."""
    import wave
    import numpy as np
    with wave.open(path, "rb") as w:
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    return data.astype(np.float32) / 32768.0

def run(job_id: str, media_path: str, hf_token: str | None,
        model_size: str = "small", num_speakers: int | None = None, language: str | None = None):
    try:
        with tempfile.TemporaryDirectory() as tmp:
            wav = os.path.join(tmp, "audio.wav")
            update(job_id, status="running", stage="Extracting audio", percent=5)
            _extract_audio(media_path, wav)

            # 1) Speech-to-text with word timestamps
            update(job_id, stage="Transcribing speech", percent=10)
            from faster_whisper import WhisperModel
            model_size = os.environ.get('FORCE_MODEL_SIZE', model_size)
            dev = _device()
            model = WhisperModel(model_size, device=dev,
                                 compute_type="float16" if dev == "cuda" else "int8")
            segs, info = model.transcribe(_load_wav(wav), language=language,
                                          vad_filter=True, word_timestamps=True)
            raw = []   # one list of words per Whisper segment
            for seg in segs:
                raw.append([(w.start, w.end, w.word) for w in (seg.words or [])])
                if info.duration:
                    update(job_id, percent=10 + int(60 * seg.end / info.duration))

            # 2) Speaker diarization (needs a Hugging Face token)
            turns = []
            if hf_token:
                update(job_id, stage="Detecting speakers", percent=75)
                turns = _diarize(wav, hf_token, num_speakers)

            # 3) Short subtitle cues: split each segment where the speaker changes
            update(job_id, stage="Formatting transcript", percent=95)
            cues = []
            for ws in raw:
                cur = None
                for s_, e_, t_ in ws:
                    spk = _speaker_at(turns, s_, e_) if turns else None
                    if cur and spk == cur["speaker"]:
                        cur["text"] += t_
                        cur["end"] = e_
                    else:
                        cur = {"start": s_, "end": e_, "speaker": spk, "text": t_}
                        cues.append(cur)
            for c in cues:
                c["text"] = c["text"].strip()
                c["time"] = _ts(c["start"])

            txt = "\n".join(
                f"[{c['time']}] {c['speaker'] + ': ' if c['speaker'] else ''}{c['text']}"
                for c in cues)
        update(job_id, status="done", stage="Finished", percent=100,
               result={"segments": cues, "text": txt, "diarized": bool(turns), "language": info.language})
    except Exception as e:
        update(job_id, status="error", error=str(e))
