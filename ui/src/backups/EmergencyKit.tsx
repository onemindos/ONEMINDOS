// SPDX-License-Identifier: Apache-2.0
// The emergency kit (BACKUPS.md §5.2): the owner recovery key, shown once, saved by the owner,
// then two groups typed back. There is no "skip": onDone is called only after the hub confirmed
// the typed groups (ONB-B2). The key lives in this component's memory only while it is shown.
import { useId, useState } from 'react';
import { Button } from '../components/Button';
import { Card } from '../components/Card';
import { Icon } from '../components/Icon';
import { StatusPill } from '../components/StatusPill';
import { kitFileName, normaliseAnswers, typeBackReady } from './logic';
import './backups.css';
import type { KitOneTime, KitState } from './types';

export interface EmergencyKitProps {
  kit: KitState;
  boxName: string;
  /** POST /v1/backups/kit; resolves with the one-time part, which is never fetched again. */
  onIssue: () => Promise<{ kit: KitState; one_time: KitOneTime }>;
  /** POST /v1/backups/kit/confirm; resolves with the new state, rejects with a message. */
  onConfirm: (answers: Record<string, string>) => Promise<KitState>;
  onDone: () => void;
  /** Turns the kit text into a downloadable link (URL.createObjectURL in the browser). */
  makeDownload?: (text: string) => string;
}

type Phase = 'start' | 'show' | 'check' | 'done';

export function EmergencyKit(p: EmergencyKitProps) {
  const id = useId();
  const [phase, setPhase] = useState<Phase>(p.kit.state === 'confirmed' ? 'done' : p.kit.state === 'issued' ? 'check' : 'start');
  const [kit, setKit] = useState(p.kit);
  const [one, setOne] = useState<KitOneTime | null>(null);
  const [saved, setSaved] = useState(false);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  async function issue() {
    setBusy(true);
    setError(undefined);
    try {
      const r = await p.onIssue();
      setKit(r.kit);
      setOne(r.one_time);
      setPhase('show');
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function confirm() {
    setBusy(true);
    setError(undefined);
    try {
      const k = await p.onConfirm(normaliseAnswers(answers));
      setKit(k);
      if (k.state === 'confirmed') {
        setOne(null); // forget the key as soon as it is proven saved
        setPhase('done');
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (phase === 'done') {
    return (
      <Card title="Emergency kit saved" level={2} aside={<StatusPill tone="ok" label="Confirmed" />}>
        <p>Keep it offline. With it and a backup disk, your data can be restored on any computer, with or without OneMind.</p>
        <Button variant="primary" onClick={p.onDone}>Continue</Button>
      </Card>
    );
  }

  if (phase === 'start') {
    return (
      <Card title="Make your emergency kit" level={2} aside={<StatusPill tone="warn" label="Required" />}>
        <p>
          Your backups are encrypted. The kit holds a recovery key that only you will have. If this box is lost or broken, the
          kit and a backup disk bring everything back. OneMind does not keep a copy, so nobody else can open your backups.
        </p>
        <Button variant="primary" icon="lock" busy={busy} onClick={issue}>Show my recovery key</Button>
        {error && <p className="omb-error" role="alert">{error}</p>}
      </Card>
    );
  }

  if (phase === 'show' && one) {
    const href = p.makeDownload?.(one.text);
    return (
      <Card title="Your recovery key" level={2} subtitle="Shown once. Write it down or print it, then keep it somewhere safe and offline.">
        <ol className="omb-key" aria-label="Recovery key, 13 groups of four characters">
          {one.groups.map((g, i) => (
            <li key={i}><span className="om-hint">{i + 1}</span> <code>{g}</code></li>
          ))}
        </ol>
        <p className="om-hint">Check group: <code>{one.check}</code> · fingerprint {kit.fingerprint}</p>
        <div className="omb-actions">
          {href && (
            <a className="omb-link" href={href} download={kitFileName(p.boxName, kit.issued_at ?? '')}>
              <Icon name="external" /> Download the kit (.txt)
            </a>
          )}
          <Button onClick={() => window.print()}>Print</Button>
        </div>
        <label className="omb-check" htmlFor={`${id}-saved`}>
          <input id={`${id}-saved`} type="checkbox" checked={saved} onChange={(e) => setSaved(e.target.checked)} />
          I have written down, printed or saved this key outside this box.
        </label>
        <Button variant="primary" disabled={!saved} onClick={() => setPhase('check')}>Next: prove it</Button>
      </Card>
    );
  }

  // check: type two groups back. Also reached after a reload, when the key is no longer shown.
  return (
    <Card title="Type back two groups" level={2} subtitle="From your saved kit, not from memory. This proves the kit was saved, not just seen.">
      <div className="omb-typeback">
        {kit.positions.map((pos) => (
          <label key={pos} className="omb-field" htmlFor={`${id}-g${pos}`}>
            <span>Group {pos}</span>
            <input
              id={`${id}-g${pos}`}
              value={answers[String(pos)] ?? ''}
              maxLength={4}
              autoComplete="off"
              spellCheck={false}
              onChange={(e) => setAnswers((a) => ({ ...a, [String(pos)]: e.target.value }))}
            />
          </label>
        ))}
      </div>
      {error && <p className="omb-error" role="alert">{error}</p>}
      <div className="omb-actions">
        <Button variant="primary" busy={busy} disabled={!typeBackReady(kit.positions, answers)} onClick={confirm}>Confirm</Button>
        {one === null && (
          <Button variant="ghost" onClick={issue} busy={busy}>I lost it: make a new kit</Button>
        )}
      </div>
    </Card>
  );
}
