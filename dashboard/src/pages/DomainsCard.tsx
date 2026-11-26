// SPDX-License-Identifier: Apache-2.0
// Network > Your own domains (NET-DOM-01, #238): register a domain you own, add the TXT proof record at your DNS
// provider, ask the box to check it, and see the names asked for under it. GET, POST, DELETE /v1/domains* through
// @onemind/sdk, owner only. Off by default on the box; approving a name records a decision only, so nothing is served
// from your domain yet and the card says so. The CLI twin is `onemind domain list`, `add` and `host request|approve|remove`.
import { useState, type FormEvent } from 'react';
import type { DomainView } from '@onemind/sdk';
import { Button, Card, Dialog, StatusPill } from '@onemind/ui';
import { usePoll } from '../lib/hooks';
import { useGateway, viaSdk } from '../lib/gateway';
import { Load, useRun } from './parts';

export function DomainsCard({ token }: { token: string }) {
  const client = useGateway(token);
  const run = useRun();
  const list = usePoll(() => viaSdk(() => client.domains.list()), 60_000);
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [removing, setRemoving] = useState<string>();
  const [note, setNote] = useState<string>();
  const [approving, setApproving] = useState<string>();
  const [typed, setTyped] = useState('');

  async function act(job: () => Promise<unknown>, title: string) {
    setBusy(true);
    const done = await run(async () => {
      await job();
      await list.reload();
      return true;
    }, title);
    setBusy(false);
    return done === true;
  }
  async function add(e: FormEvent) {
    e.preventDefault();
    const domain = name.trim();
    if (!domain) return;
    if (await act(() => viaSdk(() => client.domains.add(domain)), 'Could not add the domain')) {
      setName('');
      setNote(undefined);
    }
  }
  async function check(domain: string) {
    await act(async () => {
      const r = await viaSdk(() => client.domains.check(domain));
      setNote(r.proof_found ? `${domain} is verified.` : `The proof record for ${domain} was not found yet. DNS changes can take a while; try again later.`);
    }, 'Could not check the domain');
  }

  return (
    <Card as="article" title="Your own domains">
      <Load res={list} what="Reading your domains">
        {(d) => (
          <>
            <p>
              Use a name you own, such as <code>home.example.org</code>, for apps on this box. Add the proof record below at your DNS provider, then check it. Approving a name only records your decision: nothing is served from your domain yet and no certificate is issued.
            </p>
            {!d.enabled && (
              <p className="om-note om-tone-warn" role="status">
                Your own domain is off on this box. Turn it on in the box settings (<code>ONEMIND_DOMAINS_ENABLED=1</code>), then come back here.
              </p>
            )}
            <form onSubmit={(e) => void add(e)}>
              <label htmlFor="domain-name">Domain to add</label>
              <input id="domain-name" value={name} disabled={!d.enabled || busy} placeholder="example.org" onChange={(e) => setName(e.target.value)} autoComplete="off" />
              <Button type="submit" disabled={!d.enabled || busy || !name.trim()}>
                Add domain
              </Button>
            </form>
            {note && (
              <p className="om-note" role="status">
                {note}
              </p>
            )}
            {d.domains.length === 0 ? (
              <p className="om-hint">No domains yet.</p>
            ) : (
              d.domains.map((v) => <DomainRow key={v.domain} v={v} busy={busy} enabled={d.enabled} onCheck={() => void check(v.domain)} onRemove={() => setRemoving(v.domain)} onAsk={(app) => void act(() => viaSdk(() => client.domains.requestHost(v.domain, app)), 'Could not ask for the name')} onApprove={(h) => { setTyped(''); setApproving(h); }} onRemoveHost={(h) => void act(() => viaSdk(() => client.domains.removeHost(h)), 'Could not remove the name')} />)
            )}
          </>
        )}
      </Load>
      <Dialog
        open={approving !== undefined}
        onClose={() => setApproving(undefined)}
        title={`Approve ${approving ?? ''}?`}
        description="This records your decision only: nothing is served from the name yet and no certificate is issued. Type the full name to confirm."
        actions={
          <>
            <Button variant="ghost" onClick={() => setApproving(undefined)}>
              Cancel
            </Button>
            <Button
              disabled={typed.trim().toLowerCase() !== (approving ?? '').toLowerCase()}
              onClick={() => {
                const h = approving;
                setApproving(undefined);
                if (h) void act(() => viaSdk(() => client.domains.approveHost(h, typed.trim())), 'Could not approve the name');
              }}
            >
              Approve name
            </Button>
          </>
        }
      >
        <label htmlFor="host-confirm">Type {approving} to confirm</label>
        <input id="host-confirm" value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" />
      </Dialog>
      <Dialog
        open={removing !== undefined}
        onClose={() => setRemoving(undefined)}
        role="alertdialog"
        title={`Remove ${removing ?? ''}?`}
        description="The box forgets this domain and every name asked for under it. Your DNS provider is not touched."
        actions={
          <>
            <Button variant="ghost" onClick={() => setRemoving(undefined)}>
              Keep it
            </Button>
            <Button
              onClick={() => {
                const d = removing;
                setRemoving(undefined);
                if (d) void act(() => viaSdk(() => client.domains.remove(d)), 'Could not remove the domain');
              }}
            >
              Remove domain
            </Button>
          </>
        }
      />
    </Card>
  );
}

function DomainRow({ v, busy, enabled, onCheck, onRemove, onAsk, onApprove, onRemoveHost }: { v: DomainView; busy: boolean; enabled: boolean; onCheck: () => void; onRemove: () => void; onAsk: (app: string) => void; onApprove: (hostname: string) => void; onRemoveHost: (hostname: string) => void }) {
  const [app, setApp] = useState('');
  return (
    <section aria-label={v.domain} className="dash-stack">
      <h3>
        <code>{v.domain}</code> <StatusPill tone={v.verified ? 'ok' : 'warn'} label={v.verified ? 'Verified' : 'Not verified yet'} />
      </h3>
      {!v.verified && (
        <dl className="om-facts">
          <div>
            <dt>Add this {v.proof.type} record</dt>
            <dd>
              <code>{v.proof.name}</code> with the value <code>{v.proof.value}</code>
            </dd>
          </div>
        </dl>
      )}
      {v.hosts.length > 0 && (
        <ul aria-label={`Names under ${v.domain}`}>
          {v.hosts.map((h) => (
            <li key={h.hostname}>
              <code>{h.hostname}</code> for {h.app_id}: {h.state === 'approved' ? 'approved (not served yet)' : 'waiting for your approval'}{' '}
              {h.state !== 'approved' && (
                <Button size="sm" disabled={!enabled || busy} onClick={() => onApprove(h.hostname)} aria-label={`Approve ${h.hostname}`}>
                  Approve
                </Button>
              )}{' '}
              <Button size="sm" variant="ghost" disabled={!enabled || busy} onClick={() => onRemoveHost(h.hostname)} aria-label={`Remove the name ${h.hostname}`}>
                Remove name
              </Button>
            </li>
          ))}
        </ul>
      )}
      {v.verified && (
        <form
          aria-label={`Ask for a name under ${v.domain}`}
          onSubmit={(e) => {
            e.preventDefault();
            if (app.trim()) {
              onAsk(app.trim());
              setApp('');
            }
          }}
        >
          <label htmlFor={`ask-${v.domain}`}>App to give a name under {v.domain}</label>
          <input id={`ask-${v.domain}`} value={app} placeholder="ntfy" disabled={!enabled || busy} onChange={(e) => setApp(e.target.value)} autoComplete="off" />
          <Button type="submit" size="sm" disabled={!enabled || busy || !app.trim()}>
            Ask for this name
          </Button>
        </form>
      )}
      <Button size="sm" disabled={!enabled || busy} onClick={onCheck}>
        Check {v.domain}
      </Button>{' '}
      <Button size="sm" variant="ghost" disabled={!enabled || busy} onClick={onRemove}>
        Remove {v.domain}
      </Button>
    </section>
  );
}
