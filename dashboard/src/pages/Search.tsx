// SPDX-License-Identifier: Apache-2.0
// Search: one box over everything this person may see on the hub (files, apps' own items, settings),
// from GET /v1/search. The gateway filters every hit by this person's own grants, so nothing here
// decides who may see what. The words typed are sent to the hub and nowhere else.
import { useMemo, useRef, useState, type FormEvent } from 'react';
import { Link } from 'react-router';
import { OneMind, OneMindError } from '@onemind/sdk';
import { Button, Card, EmptyState, PageHeader } from '@onemind/ui';
import { useSignedIn } from '../session';
import { toRoute } from '../shell/routes';
import { records, str } from './records';

interface Hit { provider: string; type: string; id: string; title: string; subtitle: string; link: string }

function hits(value: unknown): Hit[] {
  return records(value).map((h) => ({ provider: str(h.provider, ''), type: str(h.type, 'other'), id: str(h.id, ''), title: str(h.title, 'Untitled'), subtitle: str(h.subtitle, ''), link: str(h.link, '') }));
}
function why(e: unknown): string {
  if (e instanceof OneMindError) {
    if (e.status === 503) return 'Search is not ready yet. It is building its index; try again in a minute.';
    if (e.status === 422) return 'That search was not understood. Try fewer or different words.';
    if (e.status === 403) return 'You are not allowed to search on this hub.';
    return e.message;
  }
  return e instanceof Error ? e.message : String(e);
}
/** The words a person reads for a hit's kind. Unknown kinds are shown as the hub names them. */
function kindLabel(type: string): string {
  const known: Record<string, string> = { file: 'Files', folder: 'Folders', setting: 'Settings', app: 'Apps', person: 'People', note: 'Notes', task: 'Tasks' };
  return known[type] ?? type.charAt(0).toUpperCase() + type.slice(1).replace(/[_.-]/g, ' ');
}

export function Search() {
  const { token, person, mock } = useSignedIn();
  if (mock) return <><PageHeader title="Search" lede="Find files, apps and settings." /><EmptyState icon="search" title="Search needs a real hub">Demo mode has nothing to search. Connect to your hub to search your files and settings.</EmptyState></>;
  return <LiveSearch key={person} token={token} />;
}

function LiveSearch({ token }: { token: string }) {
  const sdk = useMemo(() => new OneMind({ baseUrl: window.location.origin, token, retries: 1 }), [token]);
  const [q, setQ] = useState('');
  const [asked, setAsked] = useState('');
  const [found, setFound] = useState<Hit[]>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const latest = useRef(0);
  const run = async (e: FormEvent) => {
    e.preventDefault();
    const text = q.trim();
    if (!text) return;
    const mine = ++latest.current;
    setBusy(true); setError('');
    try {
      const out = hits(await sdk.call<unknown>({ method: 'GET', path: `/v1/search?q=${encodeURIComponent(text)}&limit=50` }));
      if (mine !== latest.current) return; // a newer search is on its way
      setFound(out); setAsked(text);
    } catch (err) { if (mine === latest.current) { setError(why(err)); setFound(undefined); } }
    finally { if (mine === latest.current) setBusy(false); }
  };
  const groups = useMemo(() => {
    const out = new Map<string, Hit[]>();
    for (const h of found ?? []) out.set(h.type, [...(out.get(h.type) ?? []), h]);
    return [...out.entries()];
  }, [found]);
  return <div className="dash-stack">
    <PageHeader title="Search" lede="Find files, apps' own items and settings you are allowed to see." />
    <form role="search" aria-label="Search your hub" onSubmit={(e) => void run(e)} className="om-cz-swatches">
      <label htmlFor="search-q" className="om-visually-hidden">What are you looking for?</label>
      <input id="search-q" className="om-input" type="search" value={q} maxLength={200} placeholder="What are you looking for?" onChange={(e) => setQ(e.target.value)} autoComplete="off" />
      <Button type="submit" disabled={busy || !q.trim()}>{busy ? 'Searching…' : 'Search'}</Button>
    </form>
    {error && <p className="om-note om-tone-bad" role="alert">{error}</p>}
    {found && found.length === 0 && <EmptyState icon="search" title={`Nothing found for "${asked}"`}>Every word must match. Try one word, or check the spelling. Items you are not allowed to see are never listed.</EmptyState>}
    {found && found.length > 0 && <p role="status">{found.length} {found.length === 1 ? 'result' : 'results'} for "{asked}".</p>}
    {groups.map(([type, items]) => <Card key={type} title={kindLabel(type)} as="section">
      <ul>{items.map((h) => {
        const to = toRoute(h.link);
        return <li key={`${h.provider}:${h.id}`}>{to ? <Link to={to}>{h.title}</Link> : <strong>{h.title}</strong>}{h.subtitle ? <> · <span>{h.subtitle}</span></> : null}</li>;
      })}</ul>
    </Card>)}
  </div>;
}
