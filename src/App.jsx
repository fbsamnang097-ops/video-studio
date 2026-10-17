import React, { useEffect, useRef, useState } from 'react';
import { IS_DESKTOP, getConfig, getInfo, startDownload, startTranscribe, startTranslate, pollJob, mediaUrl, fileUrl, setKey } from './api.js';

// Change this to Mr. Samnang's real Telegram username, e.g. https://t.me/username
const TELEGRAM_URL = 'https://t.me/helloboyer';

const fmtDur = (s) => (s ? `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}` : '');

const Icon = ({ d, size = 16 }) => (
  <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={d} /></svg>
);
const I = {
  link: 'M6.5 9.5a3 3 0 0 0 4.2 0l2-2a3 3 0 0 0-4.2-4.2l-.8.8M9.5 6.5a3 3 0 0 0-4.2 0l-2 2a3 3 0 0 0 4.2 4.2l.8-.8',
  down: 'M8 2v8m0 0L4.5 6.5M8 10l3.5-3.5M2.5 13.5h11',
  play: 'M5 3l8 5-8 5z',
  mic: 'M8 1.5a2 2 0 0 0-2 2V8a2 2 0 0 0 4 0V3.5a2 2 0 0 0-2-2zM3.5 7.5a4.5 4.5 0 0 0 9 0M8 12v2.5',
  check: 'M3 8.5l3.2 3L13 4.5',
  sun: 'M8 4.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7zM8 1v1.5M8 13.5V15M1 8h1.5M13.5 8H15M3 3l1 1M12 12l1 1M3 13l1-1M12 4l1-1',
  moon: 'M13.5 9.5A5.5 5.5 0 0 1 6.5 2.5a5.5 5.5 0 1 0 7 7z',
  globe: 'M8 1.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13zM1.5 8h13M8 1.5c2 2 2 11 0 13M8 1.5c-2 2-2 11 0 13',
  folder: 'M1.5 3.5h4l1.5 1.5h7.5v8h-13z',
  file: 'M4 1.5h5l3.5 3.5v9.5H4zM9 1.5V5h3.5',
};

function Clock() {
  const [t, setT] = useState(new Date());
  useEffect(() => { const id = setInterval(() => setT(new Date()), 1000); return () => clearInterval(id); }, []);
  return (
    <div className="clock" aria-label="Current date and time">
      <span className="clock-time">{t.toLocaleTimeString('en-GB', { hour12: false })}</span>
      <span className="clock-date">{t.toLocaleDateString('en-GB', { weekday: 'short', day: '2-digit', month: 'short', year: 'numeric' })}</span>
    </div>
  );
}

function Progress({ job, color = 'accent' }) {
  if (!job) return null;
  return (
    <div className="progress" role="status">
      <div className="progress-head">
        <span>{job.stage || job.status}</span>
        <span>{job.percent}%{job.speed ? ` · ${job.speed}` : ''}{job.eta ? ` · ETA ${job.eta}` : ''}</span>
      </div>
      <div className="bar"><div className={`fill ${color}`} style={{ width: `${job.percent}%` }} /></div>
    </div>
  );
}

function Box({ tone, icon, title, right, children, wide }) {
  return (
    <section className={`box ${tone} ${wide ? 'wide' : ''}`}>
      <div className="box-header">
        <span className="box-icon"><Icon d={icon} /></span>
        <h2>{title}</h2>
        <span className="spacer" />{right}
      </div>
      <div className="box-body">{children}</div>
    </section>
  );
}

export default function App() {
  const [theme, setTheme] = useState(() => localStorage.theme ||
    (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'));
  const [url, setUrl] = useState('');
  const [info, setInfo] = useState(null);
  const [quality, setQuality] = useState('720');
  const [dl, setDl] = useState(null);
  const [dlId, setDlId] = useState(null);
  const [toast, setToast] = useState(null);
  const [busy, setBusy] = useState('');
  const [token, setToken] = useState(localStorage.hfToken || '');
  const [model, setModel] = useState('small');
  const [speakers, setSpeakers] = useState('');
  const [tr, setTr] = useState(null);
  const [result, setResult] = useState(null);
  const [trId, setTrId] = useState(null);            // finished transcript job id
  const [saveDir, setSaveDir] = useState(localStorage.saveDir || '');
  const [lang, setLang] = useState('km');
  const [engine, setEngine] = useState(window.api ? 'nllb' : 'google');      // nllb = offline & unlimited, google = online
  const [tl, setTl] = useState(null);                // translation job state
  const [translations, setTranslations] = useState(null);
  const [subMode, setSubMode] = useState('both');    // orig | tl | both  (on the video)
  const [exportMode, setExportMode] = useState('orig');
  const videoRef = useRef(null);
  const [now, setNow] = useState(0);
  const [showSubs, setShowSubs] = useState(true);
  const active = result ? result.segments.findIndex((c) => now >= c.start && now < c.end) : -1;

  useEffect(() => { document.documentElement.dataset.theme = theme; localStorage.theme = theme; }, [theme]);
  useEffect(() => { localStorage.hfToken = token; }, [token]);
  useEffect(() => { localStorage.saveDir = saveDir; }, [saveDir]);
  const [needAuth, setNeedAuth] = useState(false);
  const [pw, setPw] = useState('');
  const [authErr, setAuthErr] = useState('');
  useEffect(() => {
    getConfig().then((c) => { if (!saveDir) setSaveDir(c.out_dir); })
      .catch((e) => { if (e.status === 401) setNeedAuth(true); });
  }, []);

  async function browse() {
    const dir = await window.api?.chooseFolder(saveDir);
    if (dir) setSaveDir(dir);
  }

  // Transcript -> native subtitles on the video (works in fullscreen too)
  useEffect(() => {
    const v = videoRef.current;
    if (!v || !result) return;
    const t = [...v.textTracks].find((x) => x.label === 'Transcript') || v.addTextTrack('subtitles', 'Transcript', 'zh');
    while (t.cues && t.cues.length) t.removeCue(t.cues[0]);
    result.segments.forEach((c, i) => {
      const tr = translations?.[i];
      const body = tr && subMode === 'tl' ? tr : tr && subMode === 'both' ? `${c.text}\n${tr}` : c.text;
      t.addCue(new VTTCue(c.start, Math.max(c.end, c.start + 0.5), (c.speaker ? c.speaker + ': ' : '') + body));
    });
    t.mode = showSubs ? 'showing' : 'hidden';
  }, [result, showSubs, dlId, translations, subMode]);
  useEffect(() => { document.querySelector('.transcript p.active')?.scrollIntoView({ block: 'nearest' }); }, [active]);

  const seekTo = (t) => { const v = videoRef.current; if (v) { v.currentTime = t; v.play(); } };
  const notify = (msg, type = 'info') => { setToast({ msg, type }); setTimeout(() => setToast(null), 5000); };

  async function fetchInfo() {
    setBusy('info'); setInfo(null); setDlId(null); setDl(null); setResult(null); setTr(null); setTranslations(null);
    try { setInfo(await getInfo(url.trim())); } catch (e) { notify(e.message, 'error'); }
    setBusy('');
  }
  async function download() {
    setBusy('download'); setDlId(null); setResult(null);
    try {
      const { job_id } = await startDownload(url.trim(), quality, saveDir);
      await pollJob(job_id, setDl);
      setDlId(job_id); notify('Download complete', 'success');
    } catch (e) { notify(e.message, 'error'); }
    setBusy('');
  }
  async function transcribe() {
    setBusy('transcribe'); setResult(null); setTranslations(null);
    try {
      const { job_id } = await startTranscribe({ job_id: dlId, hf_token: token || null, model, num_speakers: speakers ? Number(speakers) : null });
      const j = await pollJob(job_id, setTr);
      setTrId(job_id);
      setResult(j.result);
      notify(j.result.diarized ? 'Transcript ready' : 'Transcript ready without speaker labels. Add a Hugging Face token to detect speakers.', 'success');
    } catch (e) { notify(e.message, 'error'); }
    setBusy('');
  }
  async function translate() {
    setBusy('translate'); setTl(null);
    try {
      const { job_id } = await startTranslate(trId, lang, engine);
      const j = await pollJob(job_id, setTl);
      setTranslations(j.result.translations);
      setSubMode('both'); setExportMode('both');
      notify('Translation ready', 'success');
    } catch (e) { notify(e.message, 'error'); }
    setBusy('');
  }
  function exportTxt() {
    const lines = result.segments.map((l, i) => {
      const head = `[${l.time}] ${l.speaker ? l.speaker + ': ' : ''}`;
      const t = translations?.[i];
      if (t && exportMode === 'tl') return head + t;
      if (t && exportMode === 'both') return `${head}${l.text}\n${t}`;
      return head + l.text;
    });
    const suffix = translations && exportMode !== 'orig' ? `_${lang}` : '';
    const blob = new Blob(['\ufeff' + lines.join('\n')], { type: 'text/plain;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `${(info?.title || 'transcript').replace(/[\\/:*?"<>|]/g, '_')}${suffix}.txt`;
    a.click(); URL.revokeObjectURL(a.href);
  }

  if (needAuth) {
    const login = async () => {
      setKey(pw);
      try { await getConfig(); setNeedAuth(false); setAuthErr(''); }
      catch { setAuthErr('Wrong password'); }
    };
    return (
      <div className="app login">
        <div className="box blue login-box">
          <div className="box-header"><h2>Video Studio</h2></div>
          <div className="box-body">
            <label>Password
              <input className="input" type="password" autoFocus value={pw}
                onChange={(e) => setPw(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && login()} />
            </label>
            {authErr && <div className="flash error" style={{ marginTop: 10 }}>{authErr}</div>}
            <button className="btn primary-blue" style={{ marginTop: 12 }} onClick={login}>Sign in</button>
          </div>
        </div>
      </div>
    );
  }

  const previewSrc = dlId ? mediaUrl(dlId) : info?.preview_url;
  const isAudio = quality === 'audio' && dlId;
  const heights = info?.heights?.length ? info.heights : [1080, 720, 480, 360];
  const steps = [
    { n: 'Fetch', done: !!info, on: !info },
    { n: 'Download', done: !!dlId, on: !!info && !dlId },
    { n: 'Transcribe', done: !!result, on: !!dlId && !result },
  ];

  return (
    <div className="app">
      <header className="topbar">
        <span className="logo"><Icon d={I.play} size={14} /></span>
        <strong>Video Studio</strong>
        <ol className="steps">
          {steps.map((s, i) => (
            <li key={s.n} className={s.done ? 'done' : s.on ? 'on' : ''}>
              <span className="dot">{s.done ? <Icon d={I.check} size={12} /> : i + 1}</span>{s.n}
            </li>
          ))}
        </ol>
        <Clock />
        <button className="btn topbtn" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')} aria-label="Toggle theme">
          <Icon d={theme === 'dark' ? I.sun : I.moon} />{theme === 'dark' ? 'Light' : 'Dark'}
        </button>
      </header>

      <main>
        <Box tone="blue" icon={I.link} title="Download video"
          right={dlId ? <span className="label green">Saved</span> : info ? <span className="label blue">{heights[0]}p max</span> : null}>
          <div className="row">
            <input className="input grow" type="url" value={url} placeholder="Paste a link: YouTube, TikTok, Facebook, Instagram…"
              onChange={(e) => setUrl(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && url && fetchInfo()} />
            <button className="btn primary-blue" onClick={fetchInfo} disabled={!url || !!busy}>{busy === 'info' ? 'Fetching…' : 'Fetch video'}</button>
          </div>
          <div className="row" hidden={!IS_DESKTOP}>
            <label className="grow">Save to
              <input className="input" value={saveDir} onChange={(e) => setSaveDir(e.target.value)} placeholder="Choose a folder…" />
            </label>
            {window.api && <button className="btn" onClick={browse}><Icon d={I.folder} />Browse…</button>}
            {window.api && saveDir && <button className="btn" onClick={() => window.api.openFolder(saveDir)}>Open folder</button>}
          </div>
          {info ? (
            <>
              <div className="meta">
                {info.thumbnail && <img src={info.thumbnail} alt="" />}
                <div>
                  <strong>{info.title}</strong>
                  <div className="muted">{info.uploader} {info.duration ? `· ${fmtDur(info.duration)}` : ''}</div>
                  <div className="chips">{heights.slice(0, 5).map((h) => <span key={h} className="label gray">{h}p</span>)}</div>
                </div>
              </div>
              <div className="row">
                <label className="grow">Quality
                  <select className="input" value={quality} onChange={(e) => setQuality(e.target.value)}>
                    {heights.map((h) => <option key={h} value={h}>{h}p</option>)}
                    <option value="audio">Audio only (MP3)</option>
                  </select>
                </label>
                <button className="btn primary" onClick={download} disabled={!!busy}><Icon d={I.down} />{busy === 'download' ? 'Downloading…' : 'Download'}</button>
              </div>
              <Progress job={dl} color="green" />
              {dlId && <div className="flash success">
                {IS_DESKTOP ? `Saved to ${dl?.file || saveDir}` : (
                  <>Ready. <a className="btn primary" href={fileUrl(dlId)} download>Download file</a></>
                )}
              </div>}
            </>
          ) : <p className="muted">Fetch a video to choose its quality and start the download.</p>}
        </Box>

        <Box tone="orange" icon={I.play} title="Preview" right={result && <span className="label purple">Subtitles on</span>}>
          {previewSrc ? (
            isAudio ? <audio controls src={previewSrc} style={{ width: '100%' }} />
              : <video ref={videoRef} onTimeUpdate={(e) => setNow(e.currentTarget.currentTime)} key={previewSrc} controls src={previewSrc} poster={info?.thumbnail}
                  onError={() => notify('This site doesn’t allow a streamed preview. Download the video to play it here.', 'error')} />
          ) : <div className="empty">{info ? 'No streamable preview for this link. Download the video to play it here.' : 'The player appears here once you fetch a video.'}</div>}
        </Box>

        <Box wide tone="purple" icon={I.mic} title="Transcript with speakers"
          right={result && <span className={`label ${result.diarized ? 'green' : 'yellow'}`}>{result.diarized ? 'Speakers detected' : 'No speaker labels'}</span>}>
          <div className="row">
            <label className="grow">Hugging Face token (for speaker detection)
              <input className="input" type="password" value={token} onChange={(e) => setToken(e.target.value)} placeholder="hf_…" />
            </label>
            <label>Model
              <select className="input" value={model} onChange={(e) => setModel(e.target.value)}>
                {['tiny', 'base', 'small', 'medium', 'large-v3'].map((m) => <option key={m}>{m}</option>)}
              </select>
            </label>
            <label>Speakers
              <input className="input" type="number" min="1" max="12" value={speakers} placeholder="Auto" onChange={(e) => setSpeakers(e.target.value)} style={{ width: 90 }} />
            </label>
            <button className="btn primary-purple" onClick={transcribe} disabled={!dlId || !!busy}><Icon d={I.mic} />{busy === 'transcribe' ? 'Working…' : 'Generate transcript'}</button>
          </div>
          {!dlId && <p className="muted">Download the video first. Transcription runs on the downloaded file.</p>}
          <Progress job={tr && tr.status !== 'done' ? tr : null} color="purple" />
          <div className="row">
            <label>Translate to
              <select className="input" value={lang} onChange={(e) => setLang(e.target.value)}>
                <option value="km">Khmer (ខ្មែរ)</option><option value="en">English</option>
                <option value="th">Thai</option><option value="vi">Vietnamese</option>
              </select>
            </label>
            <label>Engine
              <select className="input" value={engine} onChange={(e) => setEngine(e.target.value)}>
                <option value="nllb">Offline NLLB (free, no limit)</option>
                <option value="google">Google (online, may rate-limit)</option>
              </select>
            </label>
            <button className="btn primary-blue" onClick={translate} disabled={!result || !!busy}>
              <Icon d={I.globe} />{busy === 'translate' ? 'Translating…' : translations ? 'Translate again' : 'Translate'}
            </button>
            {translations && (
              <label>Subtitles on video
                <select className="input" value={subMode} onChange={(e) => setSubMode(e.target.value)}>
                  <option value="both">Original + translation</option><option value="tl">Translation only</option><option value="orig">Original only</option>
                </select>
              </label>
            )}
          </div>
          <Progress job={tl && tl.status !== 'done' ? tl : null} />
          {!result && <p className="muted">Translate becomes available after the transcript is generated.</p>}
          {result && (
            <>
              <div className="row between">
                <label className="check"><input type="checkbox" checked={showSubs} onChange={(e) => setShowSubs(e.target.checked)} />Show subtitles on video</label>
                <div className="row" style={{ margin: 0 }}>
                  {translations && (
                    <select className="input" value={exportMode} onChange={(e) => setExportMode(e.target.value)} aria-label="Export content">
                      <option value="orig">Original</option><option value="tl">Translation only</option><option value="both">Original + translation</option>
                    </select>
                  )}
                  <button className="btn primary" onClick={exportTxt}><Icon d={I.file} />Export as TXT</button>
                </div>
              </div>
              <div className="transcript">
                {result.segments.map((l, i) => (
                  <p key={i} className={i === active ? 'active' : ''} onClick={() => seekTo(l.start)}>
                    <span className="time">{l.time}</span>
                    {l.speaker && <b className={`spk spk${(parseInt(l.speaker.split(' ')[1]) || 1) % 6}`}>{l.speaker}</b>}
                    {l.text}
                    {translations?.[i] && <span className="tl">{translations[i]}</span>}
                  </p>
                ))}
              </div>
            </>
          )}
        </Box>
      </main>

      <footer className="footer">
        <span>© {new Date().getFullYear()} Video Studio v1.8 · រក្សាសិទ្ធិគ្រប់យ៉ាង (All rights reserved)</span>
        <span>Developed by <a className="dev-link" href={TELEGRAM_URL} target="_blank" rel="noreferrer" title="Contact on Telegram">Mr. Samnang</a></span>
      </footer>

      {toast && <div className={`flash toast ${toast.type}`} role="alert">{toast.msg}</div>}
    </div>
  );
}
