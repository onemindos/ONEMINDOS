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
  /** The disk (LUKS) recovery key, when /data is encrypted and its key was still waiting (D-028). Shown once. */
  disk_recovery_key?: string;
  /** Non-secret: the earlier kit page that holds the disk key, when this kit does not (D-028). */
  disk_key_kit?: { fingerprint: string; issued_at: string } | null;
  /** The printable kit page, produced by the gateway. */
  text: string;
  /** 1-based positions of the two groups to type back. */
  positions: number[];
  fingerprint?: string;
}
export interface OnboardingKit {
  state: 'missing' | 'issued' | 'confirmed';
  /** Positions to type back when a kit was already issued (the key itself cannot be shown again). */
  positions: number[];
  fingerprint?: string;
  issue: () => Promise<IssuedKit>;
  confirm: (answers: Record<string, string>, fingerprint?: string) => Promise<void>;
}

const message = (e: unknown) => (e instanceof Error ? e.message : 'That did not work. Try again.');

export function RecoveryKit({ kit, onConfirmed, onSkip, allowReplacement }: {
  kit: OnboardingKit; onConfirmed: () => void; onSkip?: () => void; allowReplacement?: boolean;
}) {
  const id = useId();
  const [issued, setIssued] = useState<IssuedKit>();
  const [saved, setSaved] = useState(false);
  const [confirmed, setConfirmed] = useState(kit.state === 'confirmed');
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const positions = issued?.positions ?? kit.positions;
  const fingerprint = issued?.fingerprint ?? kit.fingerprint;
  const needsTypeBack = !confirmed && (!!issued || kit.state === 'issued');

  const run = async (fn: () => Promise<void>) => {
    if (busy) return;
    setBusy(true);
    setError(undefined);
    try { await fn(); } catch (e) { setError(message(e)); } finally { setBusy(false); }
  };
  const issue = () => void run(async () => {
    setIssued(await kit.issue());
    setAnswers({});
    setSaved(false);
    setConfirmed(false);
  });
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
        <h2 id={`${id}-t`} className="oms-kit-title">Emergency kit {!allowReplacement && <span className="oms-req">Required</span>}</h2>
        {confirmed ? (
          <p className="om-hint" role="status"><ShellIcon name="check" size={16} /> Your kit is confirmed. The gateway keeps no copy of the key.</p>
        ) : (
          <p className="om-hint">
            One page with your <strong>owner recovery key</strong>. If this box dies or you lose every device, it is the way back in. It is shown once and OneMind cannot recover it for you.
          </p>
        )}
        {confirmed && allowReplacement && (
          <div className="oms-kit-actions">
            <button type="button" className="om-btn om-btn-secondary" disabled={busy} onClick={issue}>Replace emergency kit</button>
            <p className="om-hint">Your current kit opens the rescue console until you confirm its replacement.</p>
          </div>
        )}
        {!confirmed && !issued && kit.state === 'missing' && (
          <div className="oms-kit-actions">
            <button type="button" className="om-btn om-btn-primary" disabled={busy} onClick={issue}>
              <ShellIcon name="key" size={18} /> Create my emergency kit
            </button>
          </div>
        )}
        {!confirmed && !issued && kit.state === 'issued' && (
          <>
            <p className="om-hint">Type the groups from the latest kit you saved. If you lost that copy, make a new kit. An earlier confirmed kit still opens the rescue console until you confirm a replacement. Older keys still open the backups they cover.</p>
            <div className="oms-kit-actions">
              <button type="button" className="om-btn om-btn-secondary" disabled={busy} onClick={issue}>
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
            {issued.disk_recovery_key && (
              <>
                <p className="om-hint">
                  <strong>Disk recovery key.</strong> If this box cannot unlock its encrypted data disk by itself, type this at the box's own console. It is shown once, here only, and it is on the page you download.
                </p>
                <pre className="om-code" aria-label="Disk recovery key"><code>{issued.disk_recovery_key}</code></pre>
              </>
            )}
            {!issued.disk_recovery_key && issued.disk_key_kit && (
              <p className="om-hint" role="note">
                <strong>The disk recovery key is not on this page.</strong> It was printed once, on the kit issued {issued.disk_key_kit.issued_at} (fingerprint {issued.disk_key_kit.fingerprint}). Keep that page: this box cannot show it again.
              </p>
            )}
            <p className="om-hint">Lost every passkey? Stand at the box, open its rescue console and type the owner recovery key. Nothing is deleted and the disk stays encrypted.</p>
            <div className="oms-kit-actions">
              <button type="button" className={cx('om-btn', saved ? 'om-btn-secondary' : 'om-btn-primary')} onClick={download}>
                <ShellIcon name={saved ? 'check' : 'download'} size={18} /> {saved ? 'Saved · download again' : 'Download emergency kit'}
              </button>
              <button type="button" className="om-btn om-btn-secondary" onClick={() => { window.print(); setSaved(true); }}>Print</button>
            </div>
          </>
        )}
        {needsTypeBack && positions.length > 0 && (issued ? saved : true) && (
          <form onSubmit={(e) => { e.preventDefault(); e.stopPropagation(); void run(async () => {
            if (fingerprint) await kit.confirm(answers, fingerprint);
            else await kit.confirm(answers);
            setIssued(undefined); setAnswers({}); setConfirmed(true); onConfirmed();
          }); }}>
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
