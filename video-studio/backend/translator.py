"""Translate transcript lines (default: Khmer).

Engines:
  run_nllb  - offline Meta NLLB-200 (free, unlimited, no rate limits; downloads the model once)
  run       - Google Translate via deep-translator (free, online, may rate-limit)

Google limits free requests, so this sends few, large requests, pauses between them,
retries with a growing delay when it is told "too many requests", and splits a chunk
in half (instead of sending cue-by-cue) if the line count comes back different.
"""
import time
from jobs import update

MAX_CHARS = 3000     # per request (Google allows ~5000)
PAUSE = 0.8          # seconds between requests (limit is 5/second; we stay far below)
RETRIES = 6

def _call(tr, text, job_id):
    delay = 3.0
    for attempt in range(RETRIES):
        time.sleep(PAUSE)
        try:
            return tr.translate(text) or ""
        except Exception as e:
            msg = str(e).lower()
            limited = "too many requests" in msg or "429" in msg
            if limited and attempt < RETRIES - 1:
                update(job_id, stage=f"Google asked us to slow down. Waiting {int(delay)}s…")
                time.sleep(delay)
                delay = min(delay * 2, 60)
                continue
            raise

def _lines(tr, lines, job_id):
    """Translate non-empty single-line strings; always returns the same number of lines."""
    res = _call(tr, "\n".join(lines), job_id).split("\n")
    if len(res) == len(lines):
        return [r.strip() or l for r, l in zip(res, lines)]
    if len(lines) == 1:
        return [" ".join(res).strip() or lines[0]]
    mid = len(lines) // 2
    return _lines(tr, lines[:mid], job_id) + _lines(tr, lines[mid:], job_id)

def _chunks(items):
    cur, size = [], 0
    for i, t in items:
        if cur and size + len(t) + 1 > MAX_CHARS:
            yield cur
            cur, size = [], 0
        cur.append((i, t))
        size += len(t) + 1
    if cur:
        yield cur

def run(job_id: str, texts: list[str], target: str = "km"):
    try:
        from deep_translator import GoogleTranslator
        tr = GoogleTranslator(source="auto", target=target)
        clean = [" ".join(t.split()) for t in texts]
        out = list(clean)
        todo = [(i, t) for i, t in enumerate(clean) if t]
        done = 0
        for chunk in _chunks(todo):
            update(job_id, status="running", stage="Translating")
            res = _lines(tr, [t for _, t in chunk], job_id)
            for (i, _), r in zip(chunk, res):
                out[i] = r
            done += len(chunk)
            update(job_id, stage="Translating", percent=int(100 * done / max(len(todo), 1)))
        update(job_id, status="done", stage="Finished", percent=100,
               result={"translations": out, "target": target})
    except Exception as e:
        update(job_id, status="error", error=str(e))


# ---------------------------------------------------------------- offline NLLB-200
NLLB_REPO = "entai2965/nllb-200-distilled-600M-ctranslate2"   # CTranslate2 build of Meta NLLB-200 (600M)
TARGETS = {"km": "khm_Khmr", "en": "eng_Latn", "th": "tha_Thai", "vi": "vie_Latn", "zh-CN": "zho_Hans"}
SOURCES = {"zh": "zho_Hans", "en": "eng_Latn", "th": "tha_Thai", "vi": "vie_Latn", "km": "khm_Khmr",
           "ja": "jpn_Jpan", "ko": "kor_Hang", "fr": "fra_Latn", "es": "spa_Latn", "de": "deu_Latn",
           "id": "ind_Latn", "ru": "rus_Cyrl", "hi": "hin_Deva", "ar": "arb_Arab", "pt": "por_Latn",
           "it": "ita_Latn", "tr": "tur_Latn", "ms": "zsm_Latn"}

def _guess_source(texts):
    """Used when the transcript has no stored language (older transcripts)."""
    sample = "".join(texts[:50])
    for lo, hi, code in [(0x4E00, 0x9FFF, "zho_Hans"), (0x1780, 0x17FF, "khm_Khmr"), (0x0E00, 0x0E7F, "tha_Thai"),
                         (0xAC00, 0xD7AF, "kor_Hang"), (0x3040, 0x30FF, "jpn_Jpan")]:
        if any(lo <= ord(c) <= hi for c in sample):
            return code
    return "eng_Latn"

def run_nllb(job_id: str, texts: list[str], target: str = "km", src_lang: str | None = None):
    try:
        import os
        import ctranslate2, transformers
        from huggingface_hub import snapshot_download

        update(job_id, status="running", stage="Preparing offline model (first run downloads it once)", percent=1)
        model_dir = snapshot_download(NLLB_REPO)
        translator = ctranslate2.Translator(model_dir, device="auto", intra_threads=os.cpu_count() or 4)

        src = SOURCES.get(src_lang or "", None) or _guess_source(texts)
        tgt = TARGETS.get(target, "khm_Khmr")
        tok = transformers.AutoTokenizer.from_pretrained(model_dir, src_lang=src, clean_up_tokenization_spaces=True)

        clean = [" ".join(t.split()) for t in texts]
        out = list(clean)
        todo = [(i, t) for i, t in enumerate(clean) if t]
        B = 16
        for start in range(0, len(todo), B):
            batch = todo[start:start + B]
            tokens = [tok.convert_ids_to_tokens(tok.encode(t)) for _, t in batch]
            res = translator.translate_batch(tokens, target_prefix=[[tgt]] * len(tokens),
                                             beam_size=2, max_decoding_length=256)
            for (i, _), r in zip(batch, res):
                ids = tok.convert_tokens_to_ids(r.hypotheses[0][1:])
                out[i] = tok.decode(ids, skip_special_tokens=True).strip() or clean[i]
            update(job_id, stage="Translating (offline)", percent=int(100 * min(start + B, len(todo)) / max(len(todo), 1)))
        update(job_id, status="done", stage="Finished", percent=100,
               result={"translations": out, "target": target})
    except Exception as e:
        update(job_id, status="error", error=str(e))
