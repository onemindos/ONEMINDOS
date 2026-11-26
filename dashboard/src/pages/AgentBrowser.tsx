// SPDX-License-Identifier: Apache-2.0
// Settings > AI & Agents > Agent browser (#694): the sites an AI agent may open and the browsing sessions it has running.
// GET and DELETE /v1/agent-browser/sites and /sessions, and POST /v1/agent-browser/sites, through @onemind/sdk (owner only).
// Adding a site only FILES a request: it waits in Approvals for an owner, so an agent can never widen its own reach.
// Taking a site away or ending a session is immediate. The CLI twin is `onemind agent-browser`.
import { useRef, useState, type FormEvent } from 'react';
import { uuid4 } from '@onemind/sdk';
import { Link } from 'react-router';
import { Button, Card, Dialog, StatusPill } from '@onemind/ui';
import { usePoll } from '../lib/hooks';
import { useGateway, viaSdk } from '../lib/gateway';
import { useSignedIn } from '../session';
import { Load, TextField, useRun } from './parts';

export function AgentBrowser() {
  const { token, mock, principal } = useSignedIn();
  if (mock || principal?.role !== 'owner') return null; // the gateway answers owners and agents only
  return <LiveAgentBrowser token={token} />;
}

function LiveAgentBrowser({ token }: { token: string }) {
  const client = useGateway(token);
  const run = useRun();
  const sites = usePoll(() => viaSdk(() => client.agentBrowser.sites()), 30_000);
  const sessions = usePoll(() => viaSdk(() => client.agentBrowser.sessions()), 15_000);
  const [entry, setEntry] = useState('');
  const [agent, setAgent] = useState('');
  const [note, setNote] = useState('');
  const [filed, setFiled] = useState<string>();
  const [removing, setRemoving] = useState<{ id: string; entry: string }>();
  const [busy, setBusy] = useState(false);
  // One key per request: pressing the button again after a failure or a lost reply replays the same request in
  // Approvals instead of filing a second one. A changed form gets a new key.
  const key = useRef<{ sig: string; id: string } | undefined>(undefined);

  async function act(job: () => Promise<unknown>, title: string) {
    setBusy(true);
    const ok = await run(async () => {
      await job();
      return true;
    }, title);
    setBusy(false);
    return ok === true;
  }
  async function request(e: FormEvent) {
    e.preventDefault();
    if (!entry.trim() || !agent.trim()) return;
    const body = { entry: entry.trim(), agent: agent.trim(), ...(note.trim() ? { note: note.trim() } : {}) };
    const sig = JSON.stringify(body);
    if (key.current?.sig !== sig) key.current = { sig, id: uuid4() };
    const id = key.current.id;
    const ok = await act(async () => {
      const a = await viaSdk(() => client.agentBrowser.requestSite(body, id));
      setFiled(a.id);
    }, 'Could not file the request');
    if (ok) {
      key.current = undefined;
      setEntry('');
      setNote('');
    }
  }

  return (
    <Card as="article" title="Agent browser">
      <p>
        An AI agent can browse the web only on sites you have approved, inside a locked-down browser on this box. Anything it wants to sign in to, pay for, submit or download waits for you in Approvals.
      </p>
      {filed && (
        <p role="status" className="om-note">
          Request {filed} was filed. <Link to="/approvals">Review it in Approvals</Link>: the site is not allowed until you approve it.
        </p>
      )}
      <h3>Sites agents may visit</h3>
      <Load res={sites} what="Reading the allowed sites">
        {(list) =>
          list.length === 0 ? (
            <p className="om-hint">No site is approved. Agents cannot browse anywhere yet.</p>
          ) : (
            <ul aria-label="Approved sites">
              {list.map((s) => (
                <li key={s.id}>
                  <code>{s.entry}</code> for <code>{s.agent}</code>
                  <Button size="sm" variant="ghost" disabled={busy} onClick={() => setRemoving({ id: s.id, entry: s.entry })} aria-label={`Take away ${s.entry} from ${s.agent}`}>
                    Take away
                  </Button>
                </li>
              ))}
            </ul>
          )
        }
      </Load>
      <form onSubmit={(e) => void request(e)} className="dash-form" aria-label="Ask to allow a site">
        <TextField id="ab-entry" label="Site (example.org, or *.example.org for every page under it)" value={entry} onChange={setEntry} />
        <TextField id="ab-agent" label="Agent it is for" value={agent} onChange={setAgent} />
        <TextField id="ab-note" label="Why (shown on the approval, optional)" value={note} onChange={setNote} />
        <Button type="submit" disabled={busy || !entry.trim() || !agent.trim()}>
          Ask to allow this site
        </Button>
      </form>
      <h3>Browsing sessions</h3>
      <Load res={sessions} what="Reading the browser sessions">
        {(list) =>
          list.length === 0 ? (
            <p className="om-hint">No agent is browsing right now.</p>
          ) : (
            <ul aria-label="Browser sessions">
              {list.map((s) => (
                <li key={s.id}>
                  <code>{s.agent}</code> <StatusPill tone={s.state === 'running' ? 'ok' : s.state === 'starting' ? 'warn' : 'neutral'} label={s.state} /> {s.pages} of {s.max_pages} pages used
                  {s.state !== 'ended' && (
                    <Button size="sm" variant="ghost" disabled={busy} aria-label={`End the session of ${s.agent}`} onClick={() => void act(async () => { await viaSdk(() => client.agentBrowser.endSession(s.id)); await sessions.reload(); }, 'Could not end the session')}>
                      End now
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          )
        }
      </Load>
      <Dialog
        open={removing !== undefined}
        onClose={() => setRemoving(undefined)}
        role="alertdialog"
        title={`Take away ${removing?.entry ?? ''}?`}
        description="The agent can no longer open this site, starting now. You can ask to allow it again later."
        actions={
          <>
            <Button variant="ghost" onClick={() => setRemoving(undefined)}>
              Keep it
            </Button>
            <Button
              onClick={() => {
                const r = removing;
                setRemoving(undefined);
                if (r) void act(async () => { await viaSdk(() => client.agentBrowser.removeSite(r.id)); await sites.reload(); }, 'Could not take the site away');
              }}
            >
              Take it away
            </Button>
          </>
        }
      />
    </Card>
  );
}
