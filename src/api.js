export const API = 'http://127.0.0.1:8765';

async function post(path, body) {
  const r = await fetch(API + path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const data = await r.json();
  if (!r.ok) throw new Error(data.detail || 'Request failed');
  return data;
}

export const getInfo = (url) => post('/info', { url });
export const startDownload = (url, quality) => post('/download', { url, quality });
export const startTranslate = (job_id, target, engine) => post('/translate', { job_id, target, engine });
export const startTranscribe = (opts) => post('/transcribe', opts);

/** Poll a job every 600 ms, calling onUpdate each time; resolves when done, rejects on error. */
export function pollJob(id, onUpdate) {
  return new Promise((resolve, reject) => {
    const tick = async () => {
      try {
        const j = await (await fetch(`${API}/jobs/${id}`)).json();
        onUpdate(j);
        if (j.status === 'done') return resolve(j);
        if (j.status === 'error') return reject(new Error(j.error));
        setTimeout(tick, 600);
      } catch (e) { reject(e); }
    };
    tick();
  });
}
