// Desktop (Electron) talks to the local backend; the hosted web version uses the same origin.
export const IS_DESKTOP = typeof window !== 'undefined' && !!window.api;
export const API = IS_DESKTOP ? 'http://127.0.0.1:8765' : '';

let KEY = localStorage.appKey || '';
export const setKey = (k) => { KEY = k; localStorage.appKey = k; };
const q = () => (KEY ? `?key=${encodeURIComponent(KEY)}` : '');
export const mediaUrl = (id) => `${API}/media/${id}${q()}`;   // inline playback
export const fileUrl = (id) => `${API}/files/${id}${q()}`;    // browser download

async function req(path, opts = {}) {
  const headers = { ...(opts.body ? { 'Content-Type': 'application/json' } : {}), ...(KEY ? { 'X-App-Key': KEY } : {}) };
  const r = await fetch(API + path, { ...opts, headers });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) { const e = new Error(data.detail || 'Request failed'); e.status = r.status; throw e; }
  return data;
}
const post = (path, body) => req(path, { method: 'POST', body: JSON.stringify(body) });

export const getConfig = () => req('/config');
export const getInfo = (url) => post('/info', { url });
export const startDownload = (url, quality, out_dir) => post('/download', { url, quality, out_dir: out_dir || null });
export const startTranslate = (job_id, target, engine) => post('/translate', { job_id, target, engine });
export const startTranscribe = (opts) => post('/transcribe', opts);

/** Poll a job every 600 ms, calling onUpdate each time; resolves when done, rejects on error. */
export function pollJob(id, onUpdate) {
  return new Promise((resolve, reject) => {
    const tick = async () => {
      try {
        const j = await req(`/jobs/${id}`);
        onUpdate(j);
        if (j.status === 'done') return resolve(j);
        if (j.status === 'error') return reject(new Error(j.error));
        setTimeout(tick, 600);
      } catch (e) { reject(e); }
    };
    tick();
  });
}
