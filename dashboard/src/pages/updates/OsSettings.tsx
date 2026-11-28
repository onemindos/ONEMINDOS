// SPDX-License-Identifier: Apache-2.0
// REL-02 (#154): the OS update policy and maintenance window of one machine, from GET /v1/os/updates.
// Security updates install by themselves inside the window by default (BD-09). "Request change" only
// files an os.update.settings request (PUT /v1/os/settings); nothing changes until the owner approves it,
// with a passkey when it turns automatic updates off or moves the window (D-027, D-028).
import { useState, type FormEvent } from 'react';
import { OneMind, OneMindError } from '@onemind/sdk';
import { Button } from '@onemind/ui';
import { uuidv4 } from '../../lib/uuid';

type Rec = Record<string, unknown>;
type Policy = 'auto' | 'notify' | 'off';
const POLICY: Record<Policy, string> = {
  auto: 'Install by themselves inside the window (recommended)',
  notify: 'Wait for my approval',
  off: 'Off: never install by themselves',
};
const isPolicy = (v: unknown): v is Policy => v === 'auto' || v === 'notify' || v === 'off';

export function OsSettings({ client, node, available, message, owner, onFiled }: {
  client: OneMind; node: Rec; available: boolean; message: string; owner: boolean;
  onFiled: (id: string, state: string) => void;
}) {
  const nodeId = typeof node.node_id === 'string' ? node.node_id : '';
  const policy = isPolicy(node.policy) ? node.policy : undefined;
  const win = typeof node.window === 'string' ? node.window : undefined;
  const [start, end] = win && win !== 'any' ? win.split('-') : ['02:00', '05:00'];
  const [draft, setDraft] = useState({ policy: policy ?? 'auto', any: win === 'any', start, end });
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState<string>();
  const wanted = draft.any ? 'any' : `${draft.start}-${draft.end}`;
  const changed = draft.policy !== policy || wanted !== win;
  const loosens = draft.policy !== 'auto' || wanted !== win;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true); setFailed(undefined);
    try {
      const a = await client.call<Rec>({ method: 'PUT', path: '/v1/os/settings', headers: { 'Idempotency-Key': uuidv4() },
        body: { node_id: nodeId, policy: draft.policy, window: wanted } });
      if (typeof a.id !== 'string' || typeof a.state !== 'string') throw new Error('The hub returned an invalid action.');
      onFiled(a.id, a.state);
    } catch (err) {
      setFailed(err instanceof OneMindError || err instanceof Error ? err.message : String(err));
    } finally { setBusy(false); }
  };

  const id = `os-set-${nodeId}`;
  return <section aria-label={`Update settings of ${nodeId}`}>
    <h3>Automatic security updates</h3>
    <dl className="om-facts">
      <div><dt>Policy</dt><dd>{policy ? POLICY[policy] : 'Not reported'}</dd></div>
      <div><dt>Maintenance window</dt><dd>{win === 'any' ? 'Any time' : win ?? 'Not reported'}</dd></div>
      <div><dt>Set by</dt><dd>{node.settings_source === 'owner' ? 'The owner' : node.settings_source === 'image' ? 'OneMind default' : 'Not reported'}</dd></div>
    </dl>
    {policy && policy !== 'auto' && <p className="om-note om-tone-warn" role="note">Security fixes do not install by themselves on this machine. Check this page for updates on offer.</p>}
    {!available && owner && <p className="om-hint">Changing these settings from the hub is not available yet. {message}</p>}
    {!owner ? <p className="om-hint">Only the owner can change these settings.</p> : <form className="dash-form" onSubmit={(e) => void submit(e)} aria-label={`Change update settings of ${nodeId}`}>
      <label htmlFor={`${id}-policy`}>Security updates</label>
      <select id={`${id}-policy`} value={draft.policy} onChange={(e) => setDraft({ ...draft, policy: e.target.value as Policy })}>
        {(Object.keys(POLICY) as Policy[]).map((p) => <option key={p} value={p}>{POLICY[p]}</option>)}
      </select>
      <label htmlFor={`${id}-any`}>
        <input id={`${id}-any`} type="checkbox" checked={draft.any} onChange={(e) => setDraft({ ...draft, any: e.target.checked })} /> Any time of day
      </label>
      {!draft.any && <>
        <label htmlFor={`${id}-start`}>Window starts</label>
        <input id={`${id}-start`} type="time" required value={draft.start} onChange={(e) => setDraft({ ...draft, start: e.target.value })} />
        <label htmlFor={`${id}-end`}>Window ends</label>
        <input id={`${id}-end`} type="time" required value={draft.end} onChange={(e) => setDraft({ ...draft, end: e.target.value })} />
      </>}
      {changed && loosens && <p className="om-hint">You approve this change with your passkey in Approvals.</p>}
      <Button type="submit" disabled={busy || !changed || !available}>Request change</Button>
      {failed && <p className="om-note om-tone-bad" role="status">Could not file the request: {failed}</p>}
    </form>}
  </section>;
}
