// SPDX-License-Identifier: Apache-2.0
// Logs tab of Troubleshoot (P-07): the whole box's system journal through GET /v1/system/journal.
// Read only, so nothing waits for an approval, but the hub audits each read. The hub redacts every line
// (tokens, passwords, keys, e-mail, IP and MAC addresses) and limits size and rate; this page shows what it
// sends as plain text and strips terminal control characters. The SDK client speaks JSON, so this one
// text endpoint is read with fetch and the same bearer token and protocol header.
import { useEffect, useId, useRef, useState } from 'react';
import { PROTOCOL_HEADER, PROTOCOL_VERSION } from '@onemind/sdk';
import { Button, Card } from '@onemind/ui';

const PRIORITIES = [
  ['', 'Everything'], ['err', 'Errors and worse'], ['warning', 'Warnings and worse'], ['notice', 'Notices and worse'], ['info', 'Info and worse'],
] as const;
const BOOTS = [['0', 'This boot'], ['-1', 'Previous boot'], ['-2', 'Two boots ago']] as const;
const TAILS = ['100', '200', '500', '1000', '2000'] as const;
const UNIT = /^[A-Za-z0-9][A-Za-z0-9_.@-]{0,90}\.(service|socket|timer|path)$/;
const KEEP = 2000;

// eslint-disable-next-line no-control-regex
const CONTROL = /[\u0000-\u0008\u000b-\u001f\u007f-\u009f]/g;
const clean = (s: string) => s.replace(CONTROL, '');

async function failure(res: Response): Promise<string> {
  const body = (await res.json().catch(() => ({}))) as { message?: string; reason?: string };
  if (res.status === 429) return 'Too many log reads in a short time. Wait a minute and try again.';
  if (res.status === 403) return 'Only the owner can read the system logs.';
  if (body.reason === 'host_unavailable') return 'The box cannot read its journal right now: the host service is not reachable.';
  return clean(body.message ?? `The hub answered ${res.status}.`);
}

export function LogViewer({ token }: { token: string }) {
  const id = useId();
  const [unit, setUnit] = useState('');
  const [priority, setPriority] = useState('');
  const [boot, setBoot] = useState('0');
  const [tail, setTail] = useState('200');
  const [lines, setLines] = useState<string[]>();
  const [busy, setBusy] = useState(false);
  const [following, setFollowing] = useState(false);
  const [error, setError] = useState<string>();
  const abort = useRef<AbortController | undefined>(undefined);
  useEffect(() => () => abort.current?.abort(), []);

  const unitBad = unit.trim() !== '' && !UNIT.test(unit.trim());
  const query = (follow: boolean) => {
    const q = new URLSearchParams({ tail, boot: follow ? '0' : boot });
    if (unit.trim()) q.set('unit', unit.trim());
    if (priority) q.set('priority', priority);
    if (follow) q.set('follow', 'true');
    return `/v1/system/journal?${q}`;
  };
  const open = async (follow: boolean, signal: AbortSignal) => {
    const res = await fetch(window.location.origin + query(follow), {
      headers: { Authorization: `Bearer ${token}`, [PROTOCOL_HEADER]: String(PROTOCOL_VERSION) }, signal, cache: 'no-store',
    });
    if (!res.ok) throw new Error(await failure(res));
    return res;
  };

  const show = async () => {
    abort.current?.abort();
    const ctrl = (abort.current = new AbortController());
    setBusy(true); setError(undefined); setFollowing(false);
    try {
      const res = await open(false, ctrl.signal);
      const text = await res.text();
      setLines(text.split('\n').filter((_, i, all) => i < all.length - 1 || all[i] !== '').map(clean));
    } catch (e) {
      if (!ctrl.signal.aborted) setError(e instanceof Error ? e.message : 'Could not read the logs.');
    } finally { setBusy(false); }
  };

  const follow = async () => {
    abort.current?.abort();
    const ctrl = (abort.current = new AbortController());
    setError(undefined); setFollowing(true); setLines([]);
    try {
      const res = await open(true, ctrl.signal);
      const reader = res.body?.getReader();
      if (!reader) throw new Error('This browser cannot stream the logs.');
      const decoder = new TextDecoder();
      let pending = '';
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        pending += decoder.decode(value, { stream: true });
        const events = pending.split('\n\n');
        pending = events.pop() ?? '';
        const added = events.flatMap((ev) => ev.split('\n').filter((l) => l.startsWith('data: ')).map((l) => clean(l.slice(6))));
        const ended = events.some((ev) => ev.startsWith('event: end'));
        if (added.length) setLines((old) => [...(old ?? []), ...added.filter((l) => !l.startsWith('stream '))].slice(-KEEP));
        if (ended) break;
      }
    } catch (e) {
      if (!ctrl.signal.aborted) setError(e instanceof Error ? e.message : 'The log stream broke off.');
    } finally { if (abort.current === ctrl) setFollowing(false); }
  };
  const stop = () => { abort.current?.abort(); setFollowing(false); };

  return <Card title="System logs">
    <p>The systemd journal of this whole box: the system itself, the network, SSH and every service. Lines are redacted by the box before they reach you (tokens, passwords, keys, e-mail, IP and MAC addresses are removed), and each read is recorded in the audit log. Reading never changes anything.</p>
    <label htmlFor={`${id}-unit`}>Service (optional, such as sshd.service)</label>
    <input id={`${id}-unit`} value={unit} onChange={(e) => setUnit(e.target.value)} autoComplete="off" aria-invalid={unitBad} />
    {unitBad && <p className="om-hint" role="alert">A unit name ends in .service, .socket, .timer or .path.</p>}
    <label htmlFor={`${id}-priority`}>Level</label>
    <select id={`${id}-priority`} value={priority} onChange={(e) => setPriority(e.target.value)}>
      {PRIORITIES.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
    </select>
    <label htmlFor={`${id}-boot`}>Start</label>
    <select id={`${id}-boot`} value={boot} onChange={(e) => setBoot(e.target.value)} disabled={following}>
      {BOOTS.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
    </select>
    <label htmlFor={`${id}-tail`}>Lines</label>
    <select id={`${id}-tail`} value={tail} onChange={(e) => setTail(e.target.value)}>
      {TAILS.map((v) => <option key={v} value={v}>{v}</option>)}
    </select>
    <p>
      <Button busy={busy} disabled={unitBad || following} onClick={() => void show()}>Show logs</Button>{' '}
      {following
        ? <Button variant="ghost" onClick={stop}>Stop following</Button>
        : <Button variant="ghost" disabled={unitBad || busy || boot !== '0'} onClick={() => void follow()}>Follow new lines</Button>}
    </p>
    {boot !== '0' && <p className="om-hint">Only this boot can be followed.</p>}
    {error && <p className="om-note om-tone-bad" role="alert">{error}</p>}
    {lines && (lines.length === 0
      ? <p role="status">{following ? 'Waiting for new lines.' : 'The journal has no lines for this filter.'}</p>
      : <pre aria-label="System log" tabIndex={0} style={{ maxHeight: '28rem', overflow: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{lines.join('\n')}</pre>)}
  </Card>;
}
