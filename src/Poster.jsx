import React, { useEffect } from 'react';

// Optional profile photo: put src/profile.jpg (or .png / .webp / .jpeg). Without it, an "S" is shown.
const avatars = import.meta.glob('./profile.{jpg,jpeg,png,webp}', { eager: true });
const AVATAR = Object.values(avatars)[0]?.default || null;

const Svg = ({ children }) => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{children}</svg>
);

const CONTACTS = [
  { cls: 'mail', label: 'Email', value: 'fbsamnang097@gmail.com', href: 'mailto:fbsamnang097@gmail.com',
    icon: <Svg><rect x="3" y="5" width="18" height="14" rx="2.5" /><path d="m4 7 8 6 8-6" /></Svg> },
  { cls: 'tg', label: 'Telegram', value: '@helloboyer', href: 'https://t.me/helloboyer',
    icon: <Svg><path d="M21.5 3.5 2.8 10.7l5.6 2.1 2.2 6.2 3.3-3.7 4.9 3.6z" /><path d="m8.4 12.8 9.2-6.2" /></Svg> },
  { cls: 'yt', label: 'YouTube Channel', value: '@GZMoodKH', href: 'https://www.youtube.com/@GZMoodKH',
    icon: <Svg><rect x="2.5" y="5.5" width="19" height="13" rx="4" /><path d="m10 9.5 5 2.5-5 2.5z" /></Svg> },
];

export default function Poster({ onClose }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { window.removeEventListener('keydown', onKey); document.body.style.overflow = prev; };
  }, [onClose]);

  return (
    <div className="poster-back" onClick={onClose} role="dialog" aria-modal="true" aria-label="Mr. Samnang profile">
      <div className="poster" onClick={(e) => e.stopPropagation()}>
        <button type="button" className="poster-close" onClick={onClose} aria-label="Close">&times;</button>
        <div className="poster-avatar">
          <div className="pa-inner">{AVATAR ? <img src={AVATAR} alt="Mr. Samnang" /> : 'S'}</div>
        </div>
        <h2>Mr. Samnang</h2>
        <div className="poster-role">Developer · Video Studio</div>
        <div className="poster-links">
          {CONTACTS.map((c) => (
            <a key={c.cls} className="poster-link" href={c.href} target="_blank" rel="noreferrer">
              <span className={'pl-ico ' + c.cls}>{c.icon}</span>
              <span><small>{c.label}</small><b>{c.value}</b></span>
            </a>
          ))}
        </div>
        <div className="poster-foot">© {new Date().getFullYear()} Video Studio v{__APP_VERSION__}</div>
      </div>
    </div>
  );
}
