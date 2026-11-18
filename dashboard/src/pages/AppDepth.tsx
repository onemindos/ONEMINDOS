// SPDX-License-Identifier: Apache-2.0
// App store depth on an app's page (contract §12.22, #57): what the app needs (dependencies and
// their alternatives), what needs it, and which host ports it binds. Reads only; installing a
// missing dependency is an ordinary app.install request that waits for the owner in Approvals.
import { Button } from '@onemind/ui';
import { useSignedIn } from '../session';
import { useHub } from '../data/hub';
import { usePoll } from '../lib/hooks';
import { href } from '../shell/routes';
import { useShell } from '../shell/Shell';

export function AppDepth({ appId }: { appId: string }) {
  const { api } = useSignedIn();
  const hub = useHub();
  const shell = useShell();
  const deps = usePoll(async () => {
    if (!api.appDependencies) throw new Error('Dependencies cannot be read by this gateway client.');
    return api.appDependencies(appId);
  }, 0);
  const ports = usePoll(async () => {
    if (!api.appHostPorts) throw new Error('Host ports cannot be read by this gateway client.');
    return api.appHostPorts(appId);
  }, 0);
  const canAsk = hub.canRequest !== 'no' && hub.freshness === 'live';
  return <>
    <section aria-label="Dependencies">
      <h2>Dependencies</h2>
      {deps.error ? <p role="alert">{deps.error.message}</p> : !deps.data ? <p role="status">Loading dependencies…</p> : <>
        {deps.data.requires.length === 0 ? <p>This app needs no other app.</p> : <ul>
          {deps.data.requires.map((r) => <li key={r.id}>
            <p><strong>Needs {r.choices.map((c) => c.name || c.id).join(' or ')}</strong>{r.reason ? ` — ${r.reason}` : ''}</p>
            <p role="status">{r.satisfied_by ? `Satisfied by ${hub.appName(r.satisfied_by)}.` : 'Missing: install one of these first. The install request is refused until one is running.'}</p>
            {!r.satisfied_by && <ul aria-label={`Choices for ${r.id}`}>
              {r.choices.map((c) => <li key={c.id}>
                {c.in_catalog ? <a href={href.app(c.id)}>{c.name || c.id}</a> : <span>{c.id} (not in the catalog)</span>}
                {c.id !== r.id && ' (alternative)'}
                {c.in_catalog && !c.installed && <Button disabled={!canAsk} onClick={() => void shell.requestApp('app.install', c.id)}>Request install of {c.name || c.id}</Button>}
              </li>)}
            </ul>}
          </li>)}
        </ul>}
        {deps.data.dependents.length > 0 && <p>Installed apps that depend on this one: {deps.data.dependents.map((d) => d.name || d.id).join(', ')}. Remove them first before removing this app.</p>}
      </>}
    </section>
    <section aria-label="Host ports">
      <h2>Host ports</h2>
      {ports.error ? <p role="alert">{ports.error.message}</p> : !ports.data ? <p role="status">Loading host ports…</p> : ports.data.declared.length === 0 ? <p>This app binds no port on the host; it is reached through OneMind.</p> : <>
        <table>
          <caption>Ports this app binds on node {ports.data.node_id}</caption>
          <thead><tr><th scope="col">Port</th><th scope="col">Protocol</th><th scope="col">Used for</th></tr></thead>
          <tbody>{ports.data.declared.map((p) => <tr key={`${p.port}/${p.protocol}`}><td>{p.port}</td><td>{p.protocol}</td><td>{p.description ?? '—'}</td></tr>)}</tbody>
        </table>
        {ports.data.conflicts.length > 0
          ? <div role="alert"><p>Port conflict: the install request is refused until these are free.</p><ul>{ports.data.conflicts.map((c) => <li key={`${c.port}/${c.protocol}/${c.with}`}>{c.port}/{c.protocol} is held by {c.with.startsWith('onemind:') ? `OneMind (${c.with.slice(8)})` : hub.appName(c.with)}</li>)}</ul></div>
          : <p>No conflicts: no other app or OneMind service holds these ports.</p>}
      </>}
    </section>
  </>;
}
