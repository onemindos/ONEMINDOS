// SPDX-License-Identifier: Apache-2.0
// Troubleshoot (UMB-P09, #146): the redacted diagnostic bundle, restart, shutdown and factory reset.
// Every control is a request the owner approves; a factory reset is approved only with a passkey.
// The page says plainly when this box cannot perform a control yet, and never shows a fake success.
import { useMemo, useState } from 'react';
import { OneMind, OneMindError, type components } from '@onemind/sdk';
import { Button, Card, PageHeader, StatusPill, useToast } from '@onemind/ui';
import { Link } from 'react-router';
import { ApiError } from '../api/types';
import { usePoll } from '../lib/hooks';
import { getPasskey, webauthnSupported } from '../lib/webauthn';
import { useSignedIn } from '../session';
import { useShell } from '../shell/Shell';
import { TipsGuide } from './Tips';
import { FixProblem } from './troubleshoot/FixProblem';
import { LogViewer } from './troubleshoot/LogViewer';
import { ReportProblem, saveJson } from './troubleshoot/ReportProblem';
import { href } from '../shell/routes';
import { Load, TextField, useRun } from './parts';

type SystemRequest = components['schemas']['SystemActionRequest'];
type ControlType = SystemRequest['type'];
type Controls = components['schemas']['SystemControls'];
type Bundle = components['schemas']['DiagnosticsBundle'];
type Action = components['schemas']['Action'];

function controls(value: unknown): Controls {
  const v = value as Controls | null;
  if (!v || !Array.isArray(v.controls) || !Array.isArray(v.pending)) throw new Error('The hub returned invalid system controls.');
  return v;
}

async function call<T>(client: OneMind, method: 'GET' | 'POST', path: string, body?: unknown): Promise<T> {
  try { return await client.call<T>({ method, path, body }); }
  catch (e) {
    if (e instanceof OneMindError) throw new ApiError(e.status, e.status === 401 ? 'unauthenticated' : e.status === 403 ? 'permission_denied' : 'unknown', e.message, e.reason);
    throw e;
  }
}

export function Troubleshoot() {
  const { token, person, mock } = useSignedIn();
  return mock ? <><PageHeader title="Troubleshoot" /><p role="status">Connect to a real hub to collect diagnostics or restart it. Demo mode has no box to control.</p></> : <LiveTroubleshoot key={person} token={token} />;
}

function LiveTroubleshoot({ token }: { token: string }) {
  const [tab, setTab] = useState<'help' | 'logs'>('help');
  const client = useMemo(() => new OneMind({ baseUrl: window.location.origin, token, retries: 1 }), [token]);
  const { role } = useShell();
  const status = usePoll(() => client.status.get(), 15_000);
  const currentStatus = status.error ? undefined : status.data;
  const owner = role === 'owner';
  return <div className="dash-stack">
    <PageHeader title="Troubleshoot" lede="Review box health, request a fix, read the system logs or prepare a diagnostic report." />
    {owner && <div role="tablist" aria-label="Troubleshoot sections">
      {([['help', 'Fix and report'], ['logs', 'Logs']] as const).map(([id, label]) =>
        <Button key={id} role="tab" aria-selected={tab === id} variant={tab === id ? 'primary' : 'ghost'} onClick={() => setTab(id)}>{label}</Button>)}
    </div>}
    {owner && tab === 'logs' ? <div role="tabpanel" aria-label="Logs"><LogViewer token={token} /></div> : <>
      <FixProblem client={client} status={currentStatus} owner={owner} />
      <TipsGuide client={client} />
      {owner ? <>
        <ReportProblem client={client} status={currentStatus} />
        <SystemControls client={client} />
      </> : <Card title="Report a problem">
        <p>Ask the owner to collect a report. Your account is not allowed to see this diagnostic bundle.</p>
      </Card>}
    </>}
  </div>;
}

function SystemControls({ client }: { client: OneMind }) {
  const res = usePoll(async () => controls(await call(client, 'GET', '/v1/system/controls')), 15_000);
  const run = useRun();
  const toast = useToast();
  const [phrase, setPhrase] = useState('');
  const [found, setFound] = useState<Record<string, number>>();

  const diagnostics = () => void run(async () => {
    const bundle = await call<Bundle>(client, 'GET', '/v1/system/diagnostics');
    setFound(bundle.redaction.found);
    saveJson('onemind-diagnostics.json', bundle);
  }, 'Could not collect diagnostics');

  const request = (type: ControlType, confirm?: string) => void run(async () => {
    const body: SystemRequest = { type, ...(confirm ? { confirm } : {}) };
    await call<Action>(client, 'POST', '/v1/system/actions', body);
    toast.show({ tone: 'ok', title: 'Request filed', body: 'It waits for an owner approval before anything happens.' });
    setPhrase('');
    await res.reload();
  }, 'Could not file the request');

  const approveWithPasskey = (id: string) => void run(async () => {
    const opts = await call<{ publicKey: Record<string, unknown> }>(client, 'POST', `/v1/actions/${encodeURIComponent(id)}/approve-options`);
    const webauthn = await getPasskey(opts.publicKey);
    const done = await call<Action>(client, 'POST', `/v1/actions/${encodeURIComponent(id)}/approve`, { webauthn });
    const message = done.result?.message;
    toast.show({ tone: done.state === 'succeeded' ? 'ok' : 'warn', title: `Factory reset ${done.state}`, body: typeof message === 'string' ? message : undefined });
    await res.reload();
  }, 'Could not approve the factory reset');

  return <>
    <Card title="Diagnostic bundle">
      <p>Versions, node health, recent actions and audit event names. Home folders, IP addresses, e-mail addresses, network names and secrets are removed before it leaves the box.</p>
      <Button onClick={diagnostics}>Download diagnostics</Button>
      {found && <p role="status">{Object.keys(found).length ? `Removed: ${Object.entries(found).map(([k, n]) => `${n} ${k}`).join(', ')}.` : 'Nothing personal was found to remove.'}</p>}
    </Card>
    <Load res={res} what="Loading system controls">{(s) => <>
      <Card title="Power">
        {s.controls.filter((c) => c.type !== 'system.factory_reset').map((c) => <div key={c.type}>
          <Button disabled={!c.available} onClick={() => request(c.type)}>{c.label}</Button>{' '}
          {!c.available && <StatusPill tone="warn" label="Not available on this box yet" />}
        </div>)}
        {s.controls.some((c) => !c.available) && <p className="om-hint">{s.controls.find((c) => !c.available)?.unavailable_reason}</p>}
      </Card>
      {s.controls.filter((c) => c.type === 'system.factory_reset').map((c) => <Card key={c.type} title="Factory reset">
        <p>Erases this box and returns it to its first-boot state. It needs your passkey to approve.</p>
        <TextField id="reset-confirm" label={`Type "${c.confirm_phrase ?? ''}" to ask for it`} value={phrase} onChange={setPhrase} />
        <Button variant="danger" disabled={!c.available || phrase !== c.confirm_phrase} onClick={() => request(c.type, phrase)}>Request factory reset</Button>
        {!c.available && <p className="om-hint">{c.unavailable_reason}</p>}
      </Card>)}
      <Card title="Waiting for approval">
        {s.pending.length === 0 ? <p>No system request is waiting.</p> : <ul>{s.pending.map((p) => <li key={p.id}>
          {p.type} · {p.state}{' '}
          {p.type === 'system.factory_reset'
            ? webauthnSupported() ? <Button size="sm" variant="danger" onClick={() => approveWithPasskey(p.id)}>Approve with passkey</Button> : <span className="om-hint">This browser cannot use a passkey.</span>
            : <Link to={href.approval(p.id)}>Review in Approvals</Link>}
        </li>)}</ul>}
      </Card>
    </>}</Load>
  </>;
}
