// SPDX-License-Identifier: Apache-2.0
// The Firewall section of the Network screen (P-09): what the box lets in and from where, one plain sentence per
// rule, from GET /v1/network/firewall; and (part 2) the ports the owner opened. "Ask to open a port" files a request
// (home network or mesh only, never the internet); an owner approves it with a passkey in Approvals, and the rule is
// then pending: the box takes it away again unless it is confirmed here. Removing a rule needs no approval.
import { useState } from 'react';
import { OneMind, OneMindError, type AllowRule, type FirewallView } from '@onemind/sdk';
import { Button, Card, StatusPill, Table, formatIn, type Tone } from '@onemind/ui';
import { ApiError } from '../api/types';
import { usePoll } from '../lib/hooks';
import { Load } from './parts';

type Rule = FirewallView['rules'] extends (infer R)[] | undefined ? R : never;
type Audience = Rule['audience'];

const FROM: Record<Audience, string> = {
  this_machine: 'This box itself',
  mesh: 'Your mesh',
  pod_network: 'Apps on this box',
  lan: 'Home network (LAN)',
  specific_address: 'One address',
  one_interface: 'One connection',
  any_network: 'Any address',
};
const ACTION: Record<Rule['action'], string> = { accept: 'Allow', drop: 'Block', reject: 'Block', jump: 'Check list', goto: 'Check list', return: 'Back', none: 'No effect' };

function exposureTone(e: FirewallView['exposure']): Tone {
  return e === 'lan_and_mesh_only' ? 'ok' : e === 'open_to_internet' || e === 'not_fully_understood' ? 'warn' : 'bad';
}
function exposureLabel(e: FirewallView['exposure']): string {
  return e === 'lan_and_mesh_only' ? 'Never the internet' : e === 'open_to_internet' ? 'Open to the internet' : e === 'no_firewall' ? 'Not protected' : e === 'not_fully_understood' ? 'Not fully checked' : 'Unknown';
}

function problem(e: unknown): string {
  return e instanceof OneMindError ? e.message : 'The box could not be reached. Nothing was changed that you can rely on; refresh the firewall.';
}

/** The ports the owner opened, and the form to ask for another. The box takes a pending rule away at its deadline. */
function AllowPanel({ client, view, reload }: { client: OneMind; view: FirewallView; reload: () => void }) {
  const [proto, setProto] = useState<'tcp' | 'udp'>('tcp');
  const [port, setPort] = useState('');
  const [scope, setScope] = useState<'lan' | 'mesh'>('lan');
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<{ tone: 'ok' | 'bad'; text: string }>();
  const allow = view.allow;
  const rules = allow?.rules ?? [];
  const portOk = /^\d{1,5}$/.test(port) && Number(port) >= 1 && Number(port) <= 65535;
  const ttlMin = Math.max(1, Math.round((allow?.ttl_seconds ?? 300) / 60));
  const act = async (job: () => Promise<string>) => {
    setBusy(true);
    try {
      setNote({ tone: 'ok', text: await job() });
    } catch (e) {
      setNote({ tone: 'bad', text: problem(e) });
    } finally {
      setBusy(false);
      reload();
    }
  };
  if (!allow) return null;
  return (
    <section aria-label="Ports you opened">
      <h3>Ports you opened</h3>
      <Table<AllowRule>
        caption="Ports you opened"
        hideCaption
        rows={rules}
        rowKey={(r) => r.id}
        empty="You have not opened any extra ports."
        columns={[
          { key: 'what', header: 'Open', render: (r) => `${r.proto.toUpperCase()} ${r.port} for ${r.scope === 'lan' ? 'home network' : 'mesh'}` },
          {
            key: 'state',
            header: 'State',
            render: (r) =>
              r.state === 'pending' ? (
                <StatusPill tone="warn" label={`Closes ${r.expires_at ? formatIn(r.expires_at, Date.now()) : 'soon'} unless you confirm`} />
              ) : r.state === 'revert_failed' ? (
                <StatusPill tone="bad" label="Could not close yet, retrying. Close it again below." />
              ) : (
                <StatusPill tone="ok" label="Kept" />
              ),
          },
          {
            key: 'do',
            header: '',
            render: (r) => (
              <>
                {r.state === 'pending' && (
                  <Button size="sm" variant="primary" disabled={busy} onClick={() => void act(async () => { await client.network.confirmAllow(r.id); return 'Kept. It stays open until you remove it.'; })}>
                    Keep it open
                  </Button>
                )}{' '}
                <Button size="sm" variant="ghost" disabled={busy} onClick={() => void act(async () => { await client.network.removeAllow(r.id); return 'Closed.'; })}>
                  Close it
                </Button>
              </>
            ),
          },
        ]}
      />
      {allow.supported && view.editable ? (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!portOk || busy) return;
            void act(async () => {
              await client.network.allow({ proto, port: Number(port), scope });
              setPort('');
              return `Request filed. Approve it with your passkey on the Approvals screen, then keep it open here within ${ttlMin} min or it closes again by itself.`;
            });
          }}
        >
          <h4>Ask to open a port</h4>
          <label htmlFor="fw-proto">Type</label>
          <select id="fw-proto" value={proto} onChange={(e) => setProto(e.target.value === 'udp' ? 'udp' : 'tcp')}>
            <option value="tcp">TCP</option>
            <option value="udp">UDP</option>
          </select>
          <label htmlFor="fw-port">Port (1 to 65535)</label>
          <input id="fw-port" inputMode="numeric" value={port} autoComplete="off" onChange={(e) => setPort(e.target.value.trim())} />
          <label htmlFor="fw-scope">Who can connect</label>
          <select id="fw-scope" value={scope} onChange={(e) => setScope(e.target.value === 'mesh' ? 'mesh' : 'lan')}>
            <option value="lan">Devices on my home network (LAN)</option>
            <option value="mesh">My other OneMind machines (mesh)</option>
          </select>
          <p className="om-hint">The internet is never an option here. A home network (LAN) rule is also reachable from your mesh peers and from apps running on this box, because the box's LAN list covers those too. Nothing opens until you approve the request with your passkey, and an unconfirmed port closes again after {ttlMin} min.</p>
          <Button type="submit" variant="primary" disabled={!portOk || busy}>
            Ask to open this port
          </Button>
        </form>
      ) : (
        <p className="om-note om-tone-warn" role="status">
          {allow.reason ?? 'This box cannot take new firewall rules yet.'}
        </p>
      )}
      {note && (
        <p className={`om-note om-tone-${note.tone}`} role="status">
          {note.text}
        </p>
      )}
    </section>
  );
}

export function FirewallCard({ client }: { client: OneMind }) {
  const view = usePoll(async () => {
    try {
      return await client.network.firewall();
    } catch (e) {
      if (e instanceof OneMindError) throw new ApiError(e.status, e.status === 401 ? 'unauthenticated' : e.status === 403 ? 'permission_denied' : 'unknown', e.message, e.reason);
      throw e;
    }
  }, 30_000);
  return (
    <Card as="article" title="Firewall">
      <Load res={view} what="Loading the firewall">
        {(v) => {
          if (!v.available) {
            return (
              <p className="om-note om-tone-warn" role="status">
                {v.message ?? 'The firewall could not be read.'} An unreadable firewall is not a safe one: it is simply not known.
              </p>
            );
          }
          const rules = v.rules ?? [];
          const lists = (v.chains ?? []).filter((c) => !c.base);
          const lan = (v.sets ?? []).filter((s) => s.name === 'lan4' || s.name === 'lan6').flatMap((s) => s.elements);
          return (
            <>
              <p>
                <StatusPill tone={exposureTone(v.exposure)} label={exposureLabel(v.exposure)} /> {v.headline}
              </p>
              {(v.open_to_anywhere ?? []).length > 0 && (
                <p className="om-note om-tone-warn" role="status">
                  Open to any address: {(v.open_to_anywhere ?? []).join(', ')}. If you did not choose this, check the rules below marked &quot;Any address&quot;.
                </p>
              )}
              <p className="om-hint">
                Rules are tried top to bottom. {v.default_action === 'drop' ? 'Anything no rule allows is dropped.' : 'Anything no rule blocks is let in.'}
                {lan.length > 0 ? ` "Home network" means ${lan.join(', ')}.` : ''}
                {lists.length > 0 ? ` Lists: ${lists.map((c) => c.name).join(', ')}.` : ''}
              </p>
              <Table<Rule>
                caption="Firewall rules"
                hideCaption
                rows={rules}
                rowKey={(r) => `${r.chain}/${r.position}`}
                empty="No rules are loaded."
                columns={[
                  { key: 'from', header: 'From', render: (r) => FROM[r.audience] ?? r.audience },
                  { key: 'action', header: 'What happens', render: (r) => <StatusPill tone={r.action === 'accept' && (r.audience === 'any_network' || r.audience === 'one_interface') && r.kind === 'open_port' ? 'warn' : r.action === 'accept' ? 'ok' : 'neutral'} label={ACTION[r.action] ?? r.action} /> },
                  { key: 'summary', header: 'In plain words', render: (r) => r.summary },
                  { key: 'chain', header: 'List', secondary: true, render: (r) => `${r.chain} #${r.position}` },
                ]}
              />
              {(v.other_tables ?? []).length > 0 && (
                <p className="om-hint">
                  Other services keep their own rules ({(v.other_tables ?? []).map((t) => `${t.name}: ${t.rules}`).join(', ')}). They are not listed here.
                </p>
              )}
              {(v.truncated ?? 0) > 0 && (
                <p className="om-note om-tone-warn" role="status">
                  Part of the rules ({v.truncated}) were left out because the list is too long, so this view is not complete.
                </p>
              )}
              {(v.dropped ?? 0) > 0 && (
                <p className="om-note om-tone-warn">
                  {v.dropped} firewall {v.dropped === 1 ? 'entry was' : 'entries were'} left out because the box reported something that did not check out.
                </p>
              )}
              <AllowPanel client={client} view={v} reload={() => void view.reload()} />
              <Button size="sm" variant="ghost" onClick={() => void view.reload()}>
                Refresh firewall
              </Button>
            </>
          );
        }}
      </Load>
    </Card>
  );
}
