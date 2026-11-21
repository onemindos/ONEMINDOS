// SPDX-License-Identifier: Apache-2.0
// The built-in Photos window (UMB-P12, #430): your own phone-backup library on this box, a timeline by
// day, one photo large, and how safe each one is. Read only: GET /v1/photos/library and
// GET /v1/photos/assets/{id}/content. There is no delete here yet (it waits for Trash, UMB-PHOTO-5).
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { OneMind, OneMindError } from '@onemind/sdk';
import { Button, Dialog, PageHeader } from '@onemind/ui';
import { useSignedIn } from '../session';

type Level = 'on_box' | 'in_backup' | 'in_verified_backup';
interface Photo { id: string; file_name: string; taken_at: string; size: number; level: Level }
interface Page { items: Photo[]; next_cursor: string | null }

const SAFETY: Record<Level, { label: string; tone: string }> = {
  in_verified_backup: { label: 'Safe in a checked backup', tone: 'good' },
  in_backup: { label: 'In a backup, not checked yet', tone: 'warn' },
  on_box: { label: 'Only on this box', tone: 'warn' },
};

function parsePage(value: unknown): Page {
  const v = value as { items?: unknown; next_cursor?: unknown } | null;
  if (!v || !Array.isArray(v.items) || (v.next_cursor !== null && typeof v.next_cursor !== 'string')) throw new Error('The hub returned an invalid photo list.');
  for (const p of v.items as Partial<Photo>[]) {
    if (typeof p?.id !== 'string' || typeof p.file_name !== 'string' || typeof p.taken_at !== 'string' || typeof p.size !== 'number' || !(p.level && p.level in SAFETY)) throw new Error('The hub returned an invalid photo.');
  }
  return v as Page;
}

/** The day heading: the photo's own calendar day in this browser's time zone. */
export function dayOf(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? 'Unknown day' : d.toLocaleDateString(undefined, { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
}
function size(bytes: number) { return bytes >= 1e6 ? `${(bytes / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1e3))} kB`; }

/** The photo's bytes, fetched with the bearer token (an <img src> cannot send one), as an object URL. */
function usePhotoUrl(token: string, id: string, enabled = true) {
  const [state, setState] = useState<{ url?: string; failed?: boolean }>({});
  useEffect(() => {
    if (!enabled) return;
    let url: string | undefined;
    let live = true;
    fetch(`/v1/photos/assets/${id}/content`, { headers: { Authorization: `Bearer ${token}` } })
      .then(async (r) => { if (!r.ok) throw new Error(String(r.status)); return r.blob(); })
      .then((b) => { if (live && b.type.startsWith('image/')) { url = URL.createObjectURL(b); setState({ url }); } else if (live) setState({ failed: true }); })
      .catch(() => { if (live) setState({ failed: true }); });
    return () => { live = false; if (url) URL.revokeObjectURL(url); };
  }, [token, id, enabled]);
  return state;
}

function Tile({ token, photo, onOpen }: { token: string; photo: Photo; onOpen: () => void }) {
  const ref = useRef<HTMLButtonElement>(null);
  const [seen, setSeen] = useState(typeof IntersectionObserver === 'undefined');
  useEffect(() => {
    if (seen || !ref.current) return;
    const io = new IntersectionObserver((e) => { if (e.some((x) => x.isIntersecting)) setSeen(true); });
    io.observe(ref.current);
    return () => io.disconnect();
  }, [seen]);
  const { url, failed } = usePhotoUrl(token, photo.id, seen);
  return <button ref={ref} type="button" className="dash-photo" aria-label={`Open ${photo.file_name}`} onClick={onOpen}>
    {url ? <img src={url} alt="" loading="lazy" /> : <span className="dash-photo-empty">{failed ? 'No preview' : ''}</span>}
    {photo.level === 'in_verified_backup' && <span className="dash-photo-safe" aria-hidden="true">✓</span>}
  </button>;
}

function Viewer({ token, photo, onClose }: { token: string; photo: Photo; onClose: () => void }) {
  const { url, failed } = usePhotoUrl(token, photo.id);
  const safety = SAFETY[photo.level];
  return <Dialog open onClose={onClose} title={photo.file_name} size="lg" description={`${dayOf(photo.taken_at)} · ${size(photo.size)}`} actions={<Button onClick={onClose}>Close</Button>}>
    {url ? <img className="dash-photo-large" src={url} alt={photo.file_name} /> : <p role="status">{failed ? 'This browser cannot show this file (for example a HEIC original). It is safe on the box; open it from the Files app.' : 'Loading the photo'}</p>}
    <p className={`om-note om-tone-${safety.tone}`} role="status">{safety.label}</p>
  </Dialog>;
}

export function Photos() {
  const { token, person, mock } = useSignedIn();
  return mock
    ? <><PageHeader title="Photos" /><p role="status">Connect to a real hub to see your photos. Demo mode has no photo library.</p></>
    : <Library key={person} token={token} />;
}

function Library({ token }: { token: string }) {
  const client = useMemo(() => new OneMind({ baseUrl: window.location.origin, token, retries: 1 }), [token]);
  const [photos, setPhotos] = useState<Photo[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [state, setState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [error, setError] = useState('');
  const [open, setOpen] = useState<Photo>();
  const load = useCallback(async (after: string | null) => {
    setState('loading');
    try {
      const path = `/v1/photos/library?limit=48${after ? `&cursor=${encodeURIComponent(after)}` : ''}`;
      const page = parsePage(await client.call<unknown>({ method: 'GET', path }));
      setPhotos((prev) => (after ? [...prev, ...page.items] : page.items));
      setCursor(page.next_cursor);
      setState('ready');
    } catch (e) {
      setError(e instanceof OneMindError ? (e.status === 404 ? 'Photos is not turned on on this box.' : e.status === 403 ? 'Your account does not have a photo library.' : e.message) : e instanceof Error ? e.message : 'The hub did not answer.');
      setState('error');
    }
  }, [client]);
  useEffect(() => { void load(null); }, [load]);

  const days = useMemo(() => {
    const out: { day: string; items: Photo[] }[] = [];
    for (const p of photos) {
      const day = dayOf(p.taken_at);
      const last = out[out.length - 1];
      if (last && last.day === day) last.items.push(p); else out.push({ day, items: [p] });
    }
    return out;
  }, [photos]);

  return <div className="dash-stack">
    <PageHeader title="Photos" lede="Your photos from your phone's backup, on this box. Everyone has their own library; you only see yours. This window only looks: it cannot delete." />
    {state === 'error' && <p className="om-note om-tone-bad" role="status">{error} <Button size="sm" variant="ghost" onClick={() => void load(null)}>Retry</Button></p>}
    {state === 'loading' && photos.length === 0 && <p role="status">Loading your photos</p>}
    {state === 'ready' && photos.length === 0 && <p>No photos yet. Turn on photo backup in the OneMind phone app and they appear here.</p>}
    {days.map((d) => <section key={d.day} aria-label={d.day}>
      <h2 className="dash-photo-day">{d.day}</h2>
      <div className="dash-photo-grid">{d.items.map((p) => <Tile key={p.id} token={token} photo={p} onOpen={() => setOpen(p)} />)}</div>
    </section>)}
    {cursor && <Button onClick={() => void load(cursor)} disabled={state === 'loading'}>Show older photos</Button>}
    {open && <Viewer token={token} photo={open} onClose={() => setOpen(undefined)} />}
  </div>;
}
