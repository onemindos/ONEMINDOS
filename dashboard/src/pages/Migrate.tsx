// SPDX-License-Identifier: Apache-2.0
// "Move from a cluster" (CORE-DEPLOY-6 UI): the founder-facing path off an old Kubernetes cluster,
// over /v1/migrate/plans. Plan reads the old cluster (GET only); import, copy, cutover and revert
// each file an approval request and never run from this page. The kubeconfig is a secret input: it
// lives in component state only (never storage, never logged) and is sent only with the step that needs it.
import { useMemo, useRef, useState } from 'react';
import { Link } from 'react-router';
import { OneMind, OneMindError, uuid4, type components, type paths } from '@onemind/sdk';
import { Button, Card, Dialog, PageHeader, StatusPill } from '@onemind/ui';
import { ApiError } from '../api/types';
import { usePoll } from '../lib/hooks';
import { useSignedIn } from '../session';
import { href } from '../shell/routes';
import { Load } from './parts';

type Rec = Record<string, unknown>;
type PlanBody = components['schemas']['PlanBody'];
type Step = 'import' | 'copy' | 'cutover' | 'revert';

// Route templates are keys of the generated `paths`: a renamed route fails to typecheck.
const ROUTE = {
  plans: '/v1/migrate/plans',
  plan: '/v1/migrate/plans/{plan_id}',
  helper: '/v1/migrate/plans/{plan_id}/helper',
  import: '/v1/migrate/plans/{plan_id}/import',
  copy: '/v1/migrate/plans/{plan_id}/copy',
  cutover: '/v1/migrate/plans/{plan_id}/cutover',
  revert: '/v1/migrate/plans/{plan_id}/revert',
} as const satisfies Record<string, keyof paths>;
const fill = (route: (typeof ROUTE)[keyof typeof ROUTE], id: string) => route.replace('{plan_id}', encodeURIComponent(id));

const STEPS: { step: Step; label: string; needsCluster: boolean; blurb: string }[] = [
  { step: 'import', label: 'Import the app', needsCluster: false, blurb: 'Installs the planned app bundle on this box, stopped, with no data yet.' },
  { step: 'copy', label: 'Copy the data', needsCluster: true, blurb: 'Copies volumes from the old cluster while it is still running. It cannot copy from a cluster that is switched off.' },
  { step: 'cutover', label: 'Cut over', needsCluster: true, blurb: 'Starts the app here. Optionally scales the old workloads to zero.' },
  { step: 'revert', label: 'Revert', needsCluster: false, blurb: 'Stops the app here and, if OneMind stopped the old one, needs the old cluster to scale it back up.' },
];

function rec(v: unknown, what: string): Rec {
  if (!v || typeof v !== 'object' || Array.isArray(v)) throw new Error(`The hub returned an invalid ${what}.`);
  return v as Rec;
}
function recs(v: unknown, what: string) {
  if (!Array.isArray(v)) throw new Error(`The hub returned an invalid ${what}.`);
  return v.map((x) => rec(x, what));
}
function text(v: unknown, missing = 'Not reported') { return typeof v === 'string' && v ? v : missing; }
function num(v: unknown) { return typeof v === 'number' ? v : 0; }

/** Say the refusal in words. 409 conflict covers the two verified naming cases and the live-cluster limit. */
export function refusal(e: unknown): string {
  if (!(e instanceof OneMindError)) return e instanceof Error ? e.message : String(e);
  if (e.status === 409 && /Market app id/i.test(e.message)) return 'That name is a Market app. A move cannot take over a Market app id: choose a different app id and plan again.';
  if (e.status === 409 && /already exists on this box/i.test(e.message)) return 'An app with that name is already installed on this box. Choose a different app id and plan again.';
  if (e.status === 409 && /cannot reach the cluster/i.test(e.message)) return `The old cluster did not answer. OneMind copies only from a live old cluster, so switch it back on first. (${e.message})`;
  if (e.status === 409 && /different cluster/i.test(e.message)) return 'That kubeconfig points at a different cluster than this plan was made from.';
  if (e.status === 403) return 'Only the box owner can plan or request a move.';
  return e.message;
}

export function Migrate() {
  const { token, person, mock } = useSignedIn();
  if (mock) return <><PageHeader title="Move from a cluster" /><p role="status">Connect to a real hub to move an app. Demo mode has no migration data.</p></>;
  return <Live key={person} token={token} />;
}

async function get(sdk: OneMind, path: string) {
  try { return await sdk.call<unknown>({ method: 'GET', path }); }
  catch (e) {
    if (e instanceof OneMindError) throw new ApiError(e.status, e.status === 401 ? 'unauthenticated' : e.status === 403 ? 'permission_denied' : 'unknown', e.message, e.reason);
    throw e;
  }
}
/** One POST with a stable Idempotency-Key, so a lost reply is retried as the same request. */
async function post(sdk: OneMind, token: string, key: string, path: string, body: unknown) {
  const client = new OneMind({ baseUrl: sdk.baseUrl, token, retries: 1, fetch: (url, init) => {
    const headers = new Headers(init?.headers);
    headers.set('Idempotency-Key', key);
    return fetch(url, { ...init, headers });
  } });
  return rec(await client.call<unknown>({ method: 'POST', path, body }), 'reply');
}

function Live({ token }: { token: string }) {
  const sdk = useMemo(() => new OneMind({ baseUrl: window.location.origin, token, retries: 1 }), [token]);
  const plans = usePoll(async () => recs(await get(sdk, ROUTE.plans), 'plan list'), 5_000);
  const [selected, setSelected] = useState<string>();
  // The secret: held in memory only, re-typed after a reload.
  const [kubeconfig, setKubeconfig] = useState('');
  return <div className="dash-stack">
    <PageHeader title="Move from a cluster" lede="Bring an app and its data from another Kubernetes cluster onto this box. Every step files a request that the owner approves; nothing here changes anything directly." />
    <p className="om-note om-tone-warn" role="note">Limits: apps whose id is in the Market cannot be moved this way, and data is copied only from an old cluster that is still running.</p>
    <PlanForm sdk={sdk} token={token} kubeconfig={kubeconfig} setKubeconfig={setKubeconfig} onPlanned={(id) => { setSelected(id); void plans.reload(); }} />
    <Load res={plans} what="Loading migration plans">{(items) => <Card title="Plans">
      {items.length === 0 ? <p>No migration planned yet.</p> : <ul aria-label="Migration plans">{items.map((p) => <li key={text(p.id)}>
        <Button variant="ghost" onClick={() => setSelected(text(p.id))}>{text(p.name)} ({text(p.app_id)})</Button> <StatusPill tone="neutral" label={text(p.state)} />
      </li>)}</ul>}
    </Card>}</Load>
    {selected && <PlanDetail key={selected} sdk={sdk} token={token} planId={selected} kubeconfig={kubeconfig} setKubeconfig={setKubeconfig} />}
  </div>;
}

function KubeconfigField({ id, value, onChange }: { id: string; value: string; onChange: (v: string) => void }) {
  return <>
    <label htmlFor={id}>Kubeconfig of the old cluster (secret)</label>
    <textarea id={id} rows={5} value={value} autoComplete="off" spellCheck={false} onChange={(e) => onChange(e.target.value)} />
    <small>Kept in this tab only while the page is open. The hub holds it in memory until the request is decided or expires.</small>
  </>;
}

function PlanForm({ sdk, token, kubeconfig, setKubeconfig, onPlanned }: { sdk: OneMind; token: string; kubeconfig: string; setKubeconfig: (v: string) => void; onPlanned: (id: string) => void }) {
  const [namespace, setNamespace] = useState('');
  const [context, setContext] = useState('');
  const [appId, setAppId] = useState('');
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const key = useRef(uuid4());
  const submit = async () => {
    setBusy(true); setError('');
    const body: PlanBody = { kubeconfig, namespace: namespace.trim(), ...(context.trim() && { context: context.trim() }), ...(appId.trim() && { app_id: appId.trim() }), ...(name.trim() && { name: name.trim() }) };
    try {
      const plan = await post(sdk, token, key.current, ROUTE.plans, body);
      key.current = uuid4();
      onPlanned(text(plan.id));
    } catch (e) { setError(refusal(e)); } finally { setBusy(false); }
  };
  const bad = !kubeconfig.trim() || !namespace.trim();
  return <Card title="1. Plan">
    <p>Reads the namespace of the old cluster (read-only) and writes a private bundle and a dry-run report here.</p>
    <KubeconfigField id="mig-kubeconfig" value={kubeconfig} onChange={setKubeconfig} />
    <label htmlFor="mig-ns">Namespace</label><input id="mig-ns" value={namespace} onChange={(e) => setNamespace(e.target.value)} />
    <label htmlFor="mig-ctx">Kube context (optional)</label><input id="mig-ctx" value={context} onChange={(e) => setContext(e.target.value)} />
    <label htmlFor="mig-app">App id here (optional, defaults to the namespace)</label><input id="mig-app" value={appId} onChange={(e) => setAppId(e.target.value)} />
    <label htmlFor="mig-name">Display name (optional)</label><input id="mig-name" value={name} onChange={(e) => setName(e.target.value)} />
    {error && <p className="om-note om-tone-bad" role="alert">{error}</p>}
    <Button disabled={busy || bad} onClick={() => void submit()}>{busy ? 'Reading the old cluster…' : 'Make a plan'}</Button>
  </Card>;
}

function PlanDetail({ sdk, token, planId, kubeconfig, setKubeconfig }: { sdk: OneMind; token: string; planId: string; kubeconfig: string; setKubeconfig: (v: string) => void }) {
  const plan = usePoll(async () => rec(await get(sdk, fill(ROUTE.plan, planId)), 'plan'), 3_000);
  const [filed, setFiled] = useState<Partial<Record<Step, string>>>({});
  const [asking, setAsking] = useState<Step>();
  const [helper, setHelper] = useState<string>();
  const showHelper = async (pvc: string) => {
    try { setHelper(JSON.stringify(await get(sdk, `${fill(ROUTE.helper, planId)}?pvc=${encodeURIComponent(pvc)}`), null, 2)); }
    catch (e) { setHelper(`Could not load the helper preview: ${e instanceof Error ? e.message : String(e)}`); }
  };
  return <Load res={plan} what="Loading plan">{(p) => {
    const report = rec(p.report ?? {}, 'plan report');
    const counts = rec(report.counts ?? {}, 'plan report');
    const findings = Array.isArray(report.findings) ? recs(report.findings, 'plan report') : [];
    const volumes = Array.isArray(report.volumes) ? report.volumes : [];
    const copies = Array.isArray(p.copies) ? recs(p.copies, 'plan copies') : [];
    const blocking = Array.isArray(report.blocking) ? report.blocking.length : num(report.blocking);
    return <Card as="article" title={`${text(p.name)} (${text(p.app_id)})`}>
      <p>State: <StatusPill tone="neutral" label={text(p.state)} /> · next step: {text(p.next, 'none')}</p>
      {typeof p.last_error === 'string' && p.last_error && <p className="om-note om-tone-bad" role="status">Last error: {p.last_error}</p>}
      <dl className="om-facts">
        <div><dt>Old cluster</dt><dd>{text(rec(p.source ?? {}, 'plan').server_host)}</dd></div>
        <div><dt>Namespace</dt><dd>{text(p.namespace)}</dd></div>
        <div><dt>Blocking problems</dt><dd>{blocking}</dd></div>
        <div><dt>Objects found</dt><dd>{Object.entries(counts).map(([k, v]) => `${k} ${num(v)}`).join(', ') || 'None'}</dd></div>
      </dl>
      {findings.length > 0 && <ul aria-label="Findings">{findings.map((f, i) => <li key={i}>{text(f.severity, '')} {text(f.message, text(f.kind))}</li>)}</ul>}
      {volumes.length > 0 && <ul aria-label="Volumes">{volumes.map((v, i) => {
        const name = typeof v === 'string' ? v : text((v as Rec | null)?.name ?? (v as Rec | null)?.pvc, `volume ${i + 1}`);
        return <li key={i}>{name} <Button size="sm" variant="ghost" onClick={() => void showHelper(name)}>Preview helper pod for {name}</Button></li>;
      })}</ul>}
      {helper && <pre aria-label="Helper pod preview">{helper}</pre>}
      {copies.length > 0 && <ul aria-label="Copy progress">{copies.map((c) => <li key={text(c.id)}>{text(c.pvc)}: {text(c.state)}{c.phase ? ` (${text(c.phase)})` : ''} · {num(c.files)} files · {num(c.bytes)} bytes{c.error ? ` · ${text(c.error)}` : ''}</li>)}</ul>}
      {STEPS.map((s) => <div key={s.step}>
        <p><strong>{s.label}.</strong> {s.blurb}</p>
        <Button disabled={blocking > 0 && s.step === 'import' || typeof p.busy_action_id === 'string' && p.busy_action_id !== ''} onClick={() => setAsking(s.step)}>Request: {s.label}</Button>
        {filed[s.step] && <ActionProgress sdk={sdk} actionId={filed[s.step]!} />}
      </div>)}
      {asking && <StepDialog sdk={sdk} token={token} planId={planId} bundle={text(p.bundle_sha256, '')} oldReplicas={p.old_replicas} step={asking} kubeconfig={kubeconfig} setKubeconfig={setKubeconfig}
        onClose={() => setAsking(undefined)} onFiled={(id) => { setFiled((f) => ({ ...f, [asking]: id })); setAsking(undefined); void plan.reload(); }} />}
    </Card>;
  }}</Load>;
}

function ActionProgress({ sdk, actionId }: { sdk: OneMind; actionId: string }) {
  const action = usePoll(async () => rec(await sdk.actions.get(actionId), 'action'), 2_000);
  const state = text(action.data?.state, 'checking');
  return <p role="status">Request {actionId}: {state}.{state === 'awaiting_approval' && ' Waiting for the owner. '}<Link to={href.approval(actionId)}>Open request in Approvals</Link></p>;
}

function StepDialog({ sdk, token, planId, bundle, oldReplicas, step, kubeconfig, setKubeconfig, onClose, onFiled }: {
  sdk: OneMind; token: string; planId: string; bundle: string; oldReplicas: unknown; step: Step; kubeconfig: string; setKubeconfig: (v: string) => void; onClose: () => void; onFiled: (id: string) => void;
}) {
  const meta = STEPS.find((s) => s.step === step)!;
  const [stopOld, setStopOld] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const key = useRef(uuid4());
  const wantsCluster = meta.needsCluster || (step === 'revert' && !!oldReplicas);
  const send = async () => {
    setBusy(true); setError('');
    const expires_at = new Date(sdk.hubNow() + 24 * 3600_000).toISOString();
    const body: Rec = { expires_at, ...(step === 'import' && bundle && { bundle_sha256: bundle }), ...(wantsCluster && { kubeconfig }), ...(step === 'cutover' && { stop_old: stopOld }) };
    try {
      const a = await post(sdk, token, key.current, fill(ROUTE[step], planId), body);
      if (typeof a.id !== 'string' || !a.id) throw new Error('The hub returned an incomplete reply');
      onFiled(a.id);
    } catch (e) { setError(refusal(e)); } finally { setBusy(false); }
  };
  return <Dialog role="alertdialog" open onClose={() => { if (!busy) onClose(); }} title={`Request: ${meta.label}`}
    description="This files a request. Nothing happens until the owner approves it, and the approval is bound to these exact choices."
    actions={<Button disabled={busy || (wantsCluster && !kubeconfig.trim())} onClick={() => void send()}>{busy ? 'Sending request…' : 'Send request'}</Button>}>
    <p>{meta.blurb}</p>
    {step === 'import' && <p>Bundle bound to this approval: {bundle || 'not reported'}</p>}
    {wantsCluster && <KubeconfigField id="mig-step-kubeconfig" value={kubeconfig} onChange={setKubeconfig} />}
    {step === 'cutover' && <label><input type="checkbox" checked={stopOld} onChange={(e) => setStopOld(e.target.checked)} /> Let OneMind scale the old workloads to 0</label>}
    {error && <p className="om-note om-tone-bad" role="alert">{error}</p>}
  </Dialog>;
}
