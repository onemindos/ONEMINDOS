// SPDX-License-Identifier: Apache-2.0
// Two backup views that had an API and no screen. (1) Downloadable content: some apps hold large data
// that can be downloaded again (a media library's artwork, a model cache). Backing it up is optional;
// the size is shown BEFORE it is switched on, and the request carries that size so the gateway refuses
// it if the content grew since (409). (2) Verification history: every restore test and repository check
// and what it found, with a button to request a new one. Both writes only FILE a request in Approvals.
import { useState } from 'react';
import { Link } from 'react-router';
import type { OneMind } from '@onemind/sdk';
import { Button, Card, Dialog, StatusPill } from '@onemind/ui';
import { usePoll } from '../../lib/hooks';
import { href } from '../../shell/routes';
import { Load } from '../parts';
import { read, rows, strings, text, useFiling } from './shared';

export function size(bytes: unknown): string {
  if (typeof bytes !== 'number' || !Number.isFinite(bytes) || bytes < 0) return 'size not measured yet';
  const units = ['bytes', 'KB', 'MB', 'GB', 'TB'];
  let n = bytes, i = 0;
  while (n >= 1000 && i < units.length - 1) { n /= 1000; i++; }
  return `${i === 0 ? n : n.toFixed(n < 10 ? 1 : 0)} ${units[i]}`;
}

interface Item { id: string; name: string; patterns: string[]; enabled: boolean; bytes: number | undefined; files: number | undefined; enabledBytes: number | undefined; missing: string[] }
function item(r: Record<string, unknown>): Item {
  if (typeof r.app_id !== 'string' || !r.app_id) throw new Error('The hub returned an invalid backup content entry.');
  const n = (v: unknown) => (typeof v === 'number' ? v : undefined);
  return { id: r.app_id, name: text(r.name, r.app_id), patterns: strings(r.patterns), enabled: r.enabled === true, bytes: n(r.size_bytes), files: n(r.files), enabledBytes: n(r.enabled_size_bytes), missing: strings(r.missing_volumes) };
}
const RESULT: Record<string, { tone: 'ok' | 'bad' | 'warn'; word: string }> = { pass: { tone: 'ok', word: 'Passed' }, fail: { tone: 'bad', word: 'Failed' }, error: { tone: 'warn', word: 'Could not finish' } };

export function ContentSection({ sdk, token }: { sdk: OneMind; token: string }) {
  const items = usePoll(async () => rows(await read(sdk, '/v1/backups/content')).map(item), 60_000);
  const { file, busy, error } = useFiling(sdk, token);
  const [ask, setAsk] = useState<Item>();
  const [filed, setFiled] = useState<{ id: string; what: string }>();
  const send = async (i: Item, enabled: boolean) => {
    const r = await file('/v1/backups/content', 'backup.content.set', enabled ? { app_id: i.id, enabled, seen_size_bytes: i.bytes } : { app_id: i.id, enabled });
    if (r) { setFiled({ id: r.id, what: `${enabled ? 'Back up' : 'Leave out'} ${i.name}'s downloadable content` }); setAsk(undefined); }
  };
  return <>
    <Load res={items} what="Loading downloadable content">{(list) => <Card title="Downloadable content">
      <p className="om-note">Some apps keep big files that can be downloaded again. They are left out of backups unless you choose to include them. The size is shown before you decide, and an owner approves the change.</p>
      {list.length === 0 ? <p>No installed app marks any content as downloadable again.</p> : <ul>{list.map((i) => <li key={i.id}>
        <strong>{i.name}</strong> · {i.enabled ? <StatusPill tone="ok" label="Included in backups" dot={false} /> : <StatusPill tone="neutral" label="Left out" dot={false} />}
        <dl className="om-facts">
          <div><dt>Size now</dt><dd>{size(i.bytes)}{i.files !== undefined ? ` in ${i.files} files` : ''}</dd></div>
          {i.enabled && i.enabledBytes !== undefined && <div><dt>Size when you included it</dt><dd>{size(i.enabledBytes)}</dd></div>}
          {i.missing.length > 0 && <div><dt>Not found</dt><dd>{i.missing.join(', ')}</dd></div>}
        </dl>
        {i.enabled
          ? <Button size="sm" variant="secondary" disabled={busy} onClick={() => void send(i, false)} aria-label={`Leave out ${i.name}'s content`}>Leave out</Button>
          : <Button size="sm" variant="secondary" disabled={busy || i.bytes === undefined} onClick={() => setAsk(i)} aria-label={`Include ${i.name}'s content`}>Include in backups…</Button>}
      </li>)}</ul>}
      {filed && <p role="status">{filed.what}: waiting for an owner. <Link to={href.approval(filed.id)}>Open it in Approvals</Link></p>}
      {error && !ask && <p role="alert" className="om-note om-tone-bad">{error}</p>}
    </Card>}</Load>
    <Dialog open={!!ask} role="alertdialog" title={`Back up ${ask?.name}'s downloadable content?`} onClose={() => { if (!busy) setAsk(undefined); }}
      actions={<Button disabled={busy} onClick={() => ask && void send(ask, true)}>{busy ? 'Sending request…' : 'Send request'}</Button>}>
      <p>This adds about <strong>{size(ask?.bytes)}</strong> to every backup of {ask?.name}. Nothing changes until an owner approves it in Approvals.</p>
      {error && <p role="alert">{error}</p>}
    </Dialog>
  </>;
}

export function VerificationsSection({ sdk, token }: { sdk: OneMind; token: string }) {
  const list = usePoll(async () => rows(await read(sdk, '/v1/backups/verifications')), 60_000);
  const { file, busy, error } = useFiling(sdk, token);
  const [mode, setMode] = useState<'scratch_restore' | 'check'>('scratch_restore');
  const [filed, setFiled] = useState<string>();
  const send = async () => { const r = await file('/v1/backups/verify', 'backup.verify', { mode, latest: true }); if (r) setFiled(r.id); };
  return <Card title="Backup checks">
    <p className="om-note">A backup only counts once it has been tested. A restore test restores the latest backup into a scratch area and looks inside; a repository check only checks the files are intact.</p>
    <p>
      <label htmlFor="verify-mode">Kind of check</label>{' '}
      <select id="verify-mode" className="om-input" value={mode} onChange={(e) => setMode(e.target.value as typeof mode)}>
        <option value="scratch_restore">Restore test (recommended)</option>
        <option value="check">Repository check only</option>
      </select>{' '}
      <Button disabled={busy} onClick={() => void send()}>{busy ? 'Sending request…' : 'Ask for a check'}</Button>
    </p>
    {filed && <p role="status">Check requested; nothing runs until an owner approves it. <Link to={href.approval(filed)}>Open it in Approvals</Link></p>}
    {error && <p role="alert" className="om-note om-tone-bad">{error}</p>}
    <Load res={list} what="Loading backup checks">{(items) => items.length === 0 ? <p>No checks yet. A backup is not proven until one passes.</p> : <ul aria-label="Check history">{items.map((v, i) => {
      const r = RESULT[text(v.result, 'error')] ?? RESULT.error!;
      return <li key={text(v.id, String(i))}>
        <StatusPill tone={r.tone} label={r.word} /> {v.mode === 'scratch_restore' ? 'Restore test' : 'Repository check'} of {text(v.unit, 'a backup')}{typeof v.finished_at === 'string' ? ` · finished ${v.finished_at}` : ''}
        {typeof v.snapshot_id === 'string' && <> · backup <code>{v.snapshot_id.slice(0, 8)}</code></>}
      </li>;
    })}</ul>}</Load>
  </Card>;
}
