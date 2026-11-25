// SPDX-License-Identifier: Apache-2.0
// PLG-GIT-01 (D-026): custom apps. An owner links a Git repository; the gateway fetches it at a ref in a
// sandbox, checks it like a Market app and records a revision. Nothing is installed here: the install or
// update is the ordinary request an owner approves in Approvals. Rollback points the catalog at the
// previous deployed revision; the update that applies it also waits for an owner.
import { useState } from 'react';
import { Button, PageHeader, useToast } from '@onemind/ui';
import type { CustomPlan, CustomRollbackPlan } from '../api/types';
import { errorText } from '../data/hub';
import { usePoll } from '../lib/hooks';
import { useSignedIn } from '../session';
import { href } from '../shell/routes';
import { StoreTabs } from './Market';

export function CustomApps() {
  const { api, canDecide } = useSignedIn();
  const notOwner = canDecide === 'no';
  const toast = useToast();
  const list = usePoll(async () => {
    if (!api.customApps) throw new Error('Custom apps cannot be read by this gateway client.');
    return api.customApps();
  }, 30_000);
  const [url, setUrl] = useState('');
  const [ref, setRef] = useState('main');
  const [plan, setPlan] = useState<CustomPlan>();
  const [rollback, setRollback] = useState<CustomRollbackPlan>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();

  const check = async () => {
    if (!api.planCustomApp || notOwner) return;
    setBusy(true);
    setError(undefined);
    setRollback(undefined);
    try {
      setPlan(await api.planCustomApp({ url: url.trim(), ref: ref.trim() }));
      list.reload?.();
    } catch (e) {
      setPlan(undefined);
      setError(errorText(e).message);
    } finally {
      setBusy(false);
    }
  };
  const goBack = async (appId: string) => {
    if (!api.rollbackCustomApp || notOwner) return;
    setBusy(true);
    setError(undefined);
    setPlan(undefined);
    try {
      setRollback(await api.rollbackCustomApp(appId));
      toast.show({ tone: 'info', title: 'Rollback prepared', body: 'Nothing changes until an owner approves the update.' });
      list.reload?.();
    } catch (e) {
      setError(errorText(e).message);
    } finally {
      setBusy(false);
    }
  };

  return <>
    <PageHeader title="Custom apps" lede="Link a Git repository that holds an onemind.app.yaml. It is checked like a Market app, and an owner approves every install and update." />
    <StoreTabs current="custom" />
    {notOwner && <p role="note">Only an owner can link a repository or roll an app back. This account is not an owner, so the form cannot be sent.</p>}
    <section aria-label="Add a custom app">
      <h2>Add custom app</h2>
      <form onSubmit={(e) => { e.preventDefault(); void check(); }}>
        <p><label>Git URL<input required type="url" pattern="https://.+" maxLength={500} value={url} onChange={(e) => setUrl(e.target.value)} /></label><small>https only, no user name, password or query. Private repositories are not supported yet.</small></p>
        <p><label>Ref<input required maxLength={100} value={ref} onChange={(e) => setRef(e.target.value.trim())} /></label><small>A branch, a tag or a full commit id.</small></p>
        <Button type="submit" disabled={busy || notOwner}>Check repository</Button>
      </form>
      <p className="om-hint">Checking fetches the repository in a sandbox and records a revision. It installs nothing.</p>
      {error && <p role="alert">{error}</p>}
    </section>
    {plan && <section aria-label="Plan">
      <h2>{plan.verdict === 'ready' ? `${plan.name || plan.app_id} ${plan.version ?? ''}`.trim() : 'Not ready'}</h2>
      <p>Commit <code>{plan.commit.slice(0, 12)}</code>{plan.revision ? <>, revision {plan.revision}</> : null}. Scan: {plan.scan ? plan.scan.result : 'not run'}.</p>
      {plan.problems.length > 0 && <ul aria-label="Problems">{plan.problems.map((p) => <li key={p}>{p}</li>)}</ul>}
      {plan.notes.map((n) => <p key={n} role="note">{n}</p>)}
      {plan.signature && <p>Signature: {plan.signature.status.replace(/_/g, ' ')} ({plan.signature.policy}). {plan.signature.detail}</p>}
      {plan.verdict === 'ready' && plan.app_id
        ? <p><a href={plan.action_type === 'app.update' ? href.manage(plan.app_id) : href.app(plan.app_id)}>{plan.action_type === 'app.update' ? 'Request the update' : 'Request the install'}</a> — an owner approves it in Approvals.</p>
        : <p>Nothing was installed.</p>}
    </section>}
    {rollback && <section aria-label="Rollback plan">
      <h2>Rollback prepared</h2>
      <p>{rollback.app_id} goes from revision {rollback.from_revision} back to revision {rollback.to_revision}{rollback.version ? ` (${rollback.version})` : ''}, commit <code>{rollback.commit.slice(0, 12)}</code>.</p>
      <p><a href={href.manage(rollback.app_id)}>Request the update</a> — an owner approves it in Approvals, and it is undone if the app is not healthy.</p>
    </section>}
    <section aria-label="Linked repositories">
      <h2>Linked repositories</h2>
      {list.error ? <p role="alert">{list.error.message}</p> : !list.data ? <p role="status">Loading custom apps…</p> : list.data.length === 0 ? <p>No custom app is linked yet.</p> : <ul>
        {list.data.map((a) => <li key={a.app_id}>
          <p><a href={href.app(a.app_id)}><strong>{a.app_id}</strong></a> — {a.url} ({a.status.replace(/_/g, ' ')})</p>
          <table aria-label={`Revisions of ${a.app_id}`}>
            <thead><tr><th>Revision</th><th>Commit</th><th>Version</th><th>Scan</th><th>Deployed</th><th>Now</th></tr></thead>
            <tbody>{a.revisions.map((r) => <tr key={r.revision}>
              <td>{r.revision}</td><td><code>{r.commit.slice(0, 12)}</code></td><td>{r.version ?? '-'}</td><td>{r.scan.result}</td>
              <td>{r.deployed_at ? new Date(r.deployed_at).toLocaleString() : '-'}</td><td>{r.deployed ? 'running' : r.current ? 'next' : ''}</td>
            </tr>)}</tbody>
          </table>
          {a.rollback_to !== null && a.status === 'installed' && <Button disabled={busy || notOwner} onClick={() => void goBack(a.app_id)}>{`Roll back ${a.app_id} to revision ${a.rollback_to}`}</Button>}
        </li>)}
      </ul>}
    </section>
  </>;
}
