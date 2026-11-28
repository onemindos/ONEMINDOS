// SPDX-License-Identifier: Apache-2.0
// Settings > About > Message subjects: the rules for the message bus every app, agent and machine talks over
// (GET /v1/subjects): which kinds of message exist, who may send each, and how long each is kept. The "Can they send
// this?" check (GET /v1/subjects/check) only answers; it never sends anything. Read only. CLI twin: `onemind subjects`.
import { useState, type FormEvent } from 'react';
import { Button, Card } from '@onemind/ui';
import { usePoll } from '../lib/hooks';
import { useGateway, viaSdk } from '../lib/gateway';
import { useSignedIn } from '../session';
import { Load, TextField, useRun } from './parts';

type Publisher = 'gateway' | 'node' | 'app' | 'agent';
/** How long a kind is kept, in the largest whole unit that does not round to 0 (30 minutes, not "0 h"). */
const keptFor = (s: number) => (s < 60 ? `${s} s` : s < 3600 ? `${Math.round(s / 60)} min` : s < 2 * 86400 ? `${Math.round(s / 3600)} h` : `${Math.round(s / 86400)} days`);
const PUBLISHERS: Publisher[] = ['app', 'agent', 'node', 'gateway'];

export function SettingsSubjects() {
  const { token, mock } = useSignedIn();
  if (mock) return null;
  return <LiveSubjects token={token} />;
}

function LiveSubjects({ token }: { token: string }) {
  const client = useGateway(token);
  const run = useRun();
  const tree = usePoll(() => viaSdk(() => client.subjects.tree()), 0);
  const [subject, setSubject] = useState('');
  const [publisher, setPublisher] = useState<Publisher>('app');
  const [owner, setOwner] = useState('');
  const [verdict, setVerdict] = useState<{ ok: boolean; reason: string }>();
  async function check(e: FormEvent) {
    e.preventDefault();
    setVerdict(undefined);
    const r = await run(() => viaSdk(() => client.subjects.check(subject.trim(), publisher, owner.trim() || undefined)), 'Could not check the subject');
    if (r) setVerdict({ ok: r.ok, reason: r.reason });
  }
  return (
    <Card as="article" title="Message subjects">
      <details>
        <summary>Who may send which messages (technical)</summary>
        <Load res={tree} what="Reading the message rules">
          {(t) => (
            <>
              <p>
                Message grammar {t.grammar}, version {t.version}. Each kind says who may send it, which stream keeps it and for how long.
              </p>
              <ul aria-label="Message kinds">
                {t.kinds.map((k) => (
                  <li key={k.kind}>
                    <strong>{k.kind}</strong>{k.core ? ' (core)' : ''}: {k.description} Kept: {k.retention.policy}{k.retention.max_age_s ? `, up to ${keptFor(k.retention.max_age_s)}` : ''}.
                    {k.subjects.length > 0 && <> May send: {[...new Set(k.subjects.flatMap((s) => s.publishers))].join(', ')}.</>}
                  </li>
                ))}
              </ul>
              {t.reserved.length > 0 && <p className="om-hint">Reserved: {t.reserved.map((r) => r.kind).join(', ')}.</p>}
            </>
          )}
        </Load>
        <form onSubmit={(e) => void check(e)} aria-label="Check who may send a subject">
          <TextField id="subj-subject" label="Subject to check" value={subject} onChange={setSubject} />
          <label htmlFor="subj-publisher">Sender</label>
          <select id="subj-publisher" value={publisher} onChange={(e) => setPublisher(e.target.value as Publisher)}>
            {PUBLISHERS.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
          <TextField id="subj-owner" label="The sender’s own id (optional)" value={owner} onChange={setOwner} />
          <Button type="submit" disabled={!subject.trim()}>Check</Button>
        </form>
        {verdict && <p role="status" className={verdict.ok ? 'om-note' : 'om-note om-tone-warn'}>{verdict.ok ? 'Allowed' : 'Not allowed'}: {verdict.reason}</p>}
      </details>
    </Card>
  );
}
