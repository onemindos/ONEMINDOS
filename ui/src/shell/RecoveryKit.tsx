// SPDX-License-Identifier: Apache-2.0
// The connected emergency-kit step (ONB-B2, BACKUPS.md section 5). The gateway issues the owner recovery key once;
// it lives only in this component's memory (never storage, never a log, never a URL) and is dropped the moment the
// owner types two groups back and the gateway confirms them.
import { useId, useState } from 'react';
import { cx } from '../lib/cx';
import { ShellIcon } from './icons';

export interface IssuedKit {
  groups: string[];
  check: string;
  /** The printable kit page, produced by the gateway. */
  text: string;
  /** 1-based positions of the two groups to type back. */
  positions: number[];
  /** The data disk's recovery key (D-020), when this kit carries it. Shown once, like the owner key. */
  disk_key?: string | null;
}
export interface OnboardingKit {
  state: 'missing' | 'issued' | 'confirmed';
  /** Positions to type back when a kit was already issued (the key itself cannot be shown again). */
  positions: number[];
  issue: () => Promise<IssuedKit>;
  confirm: (answers: Record<string, string>) => Promise<void>;
}

const message = (e: unknown) => (e instanceof Error ? e.message : 'That did not work. Try again.');

export function RecoveryKit({ kit, onConfirmed, onSkip }: { kit: OnboardingKit; onConfirmed: () => void; onSkip?: () => void }) {
  const id = useId();
  const [issued, setIssued] = useState<IssuedKit>();
  const [saved, setSaved] = useState(false);
  const [confirmed, setConfirmed] = useState(kit.state === 'confirmed');
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const positions = issued?.positions ?? kit.positions;
  const needsTypeBack = !confirmed && (!!issued || kit.state === 'issued');

  const run = async (fn: () => Promise<void>) => {
    if (busy) return;
    setBusy(true);
    setError(undefined);
    try { await fn(); } catch (e) { setError(message(e)); } finally { setBusy(false); }
  };
  const download = () => {
    if (!issued) return;
    const url = URL.createObjectURL(new Blob([issued.text], { type: 'text/plain' }));
    const a = document.createElement('a');
    a.href = url;
    a.download = 'onemind-emergency-kit.txt';
    a.click();
    URL.revokeObjectURL(url);
    setSaved(true);
  };

  return (
    <section className="oms-kit" aria-labelledby={`${id}-t`}>
      <div className="oms-kit-art" aria-hidden="true"><ShellIcon name="key" size={30} /></div>
      <div className="oms-kit-text">
        <h2 id={`${id}-t`} className="oms-kit-title">Emergency kit <span className="oms-req">Required</span></h2>
        {confirmed ? (
          <p className="om-hint" role="status"><ShellIcon name="check" size={16} /> Your kit is confirmed. The gateway keeps no copy of the key.</p>
        ) : (
          <p className="om-hint">
            One page with your <strong>owner recovery key</strong>. If this box dies or you lose every device, it is the only way back in. It is shown once and OneMind cannot recover it for you.
          </p>
        )}
        {!confirmed && !issued && kit.state === 'missing' && (
          <div className="oms-kit-actions">
            <button type="button" className="om-btn om-btn-primary" disabled={busy} onClick={() => void run(async () => setIssued(await kit.issue()))}>
              <ShellIcon name="key" size={18} /> Create my emergency kit
            </button>
          </div>
        )}
        {!confirmed && !issued && kit.state === 'issued' && (
          <>
            <p className="om-hint">A kit was already created on this box. The key cannot be shown again, so type the groups below from the copy you saved. Lost it? Make a new kit. The old key keeps working until it is removed (backup.key.rotate), so treat a lost copy as still valid.</p>
            <div className="oms-kit-actions">
              <button type="button" className="om-btn om-btn-secondary" disabled={busy} onClick={() => void run(async () => { setAnswers({}); setIssued(await kit.issue()); })}>
                <ShellIcon name="key" size={18} /> I lost my copy: make a new kit
              </button>
            </div>
          </>
        )}
        {!confirmed && onSkip && (
          <div className="oms-kit-actions">
            <button type="button" className="om-btn om-btn-secondary" disabled={busy} onClick={onSkip}>Skip for now</button>
            <p className="om-hint">Without a confirmed kit nobody can recover this box. Create it later from Backups.</p>
          </div>
        )}
        {issued && (
          <>
            <pre className="om-code" aria-label="Owner recovery key"><code>{issued.groups.join('-')}</code></pre>
            <p className="om-hint">Check group: <strong>{issued.check}</strong>. Save this page offline, away from this box.</p>
            {issued.disk_key && (
              <>
                <p className="om-hint">Disk recovery key. It unlocks this box's data disk if the security chip cannot (a moved disk, a new motherboard). It is on the kit page too.</p>
                <pre className="om-code" aria-label="Disk recovery key"><code>{issued.disk_key}</code></pre>
              </>
            )}
            <div className="oms-kit-actions">
              <button type="button" className={cx('om-btn', saved ? 'om-btn-secondary' : 'om-btn-primary')} onClick={download}>
                <ShellIcon name={saved ? 'check' : 'download'} size={18} /> {saved ? 'Saved · download again' : 'Download emergency kit'}
              </button>
              <button type="button" className="om-btn om-btn-secondary" onClick={() => window.print()}>Print</button>
            </div>
          </>
        )}
        {needsTypeBack && positions.length > 0 && (issued ? saved : true) && (
          <form onSubmit={(e) => { e.preventDefault(); e.stopPropagation(); void run(async () => { await kit.confirm(answers); setIssued(undefined); setAnswers({}); setConfirmed(true); onConfirmed(); }); }}>
            <p className="om-hint">Prove you saved it: type these groups from your copy.</p>
            {positions.map((p) => (
              <label key={p} className="oms-label">
                Group {p}
                <input className="oms-input" value={answers[String(p)] ?? ''} maxLength={4} autoComplete="off" spellCheck={false}
                  onChange={(e) => setAnswers((a) => ({ ...a, [String(p)]: e.target.value.toUpperCase() }))} />
              </label>
            ))}
            <button type="submit" className="om-btn om-btn-primary" disabled={busy || positions.some((p) => (answers[String(p)] ?? '').length !== 4)}>Confirm my kit</button>
          </form>
        )}
        {error && <p className="oms-field-msg" role="alert"><ShellIcon name="alert" size={14} /> {error}</p>}
      </div>
    </section>
  );
}
