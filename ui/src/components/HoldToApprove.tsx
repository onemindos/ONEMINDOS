// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState, type CSSProperties } from 'react';
import { Button } from './Button';
import { VerificationBadge, type VerificationLevel } from './VerificationBadge';

type Mode = 'pointer' | 'keyboard' | 'confirm';

export function HoldToApprove({ label, duration = 2000, disabled = false, requiredLevel, onApprove }: {
  label: string;
  duration?: number;
  disabled?: boolean;
  /** The key level this approval needs (approve-options' required_level), shown beside the button. */
  requiredLevel?: VerificationLevel;
  onApprove: (elapsedMs: number) => void;
}) {
  const pending = useRef<{ mode: Mode; started: number; timer: ReturnType<typeof setTimeout>; key?: string }>(null);
  const [mode, setMode] = useState<Mode>();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const blur = () => {
      if (pending.current) clearTimeout(pending.current.timer);
      pending.current = null;
      setMode(undefined);
      setReady(false);
    };
    window.addEventListener('blur', blur);
    return () => {
      window.removeEventListener('blur', blur);
      if (pending.current) clearTimeout(pending.current.timer);
      pending.current = null;
    };
  }, []);

  function cancel() {
    if (pending.current) clearTimeout(pending.current.timer);
    pending.current = null;
    setMode(undefined);
    setReady(false);
  }

  function complete() {
    const wait = pending.current;
    if (!wait) return;
    const elapsed = Math.floor(performance.now() - wait.started);
    cancel();
    if (!disabled && elapsed >= duration) onApprove(elapsed);
  }

  function start(next: Mode, key?: string) {
    if (pending.current || disabled) return;
    const started = performance.now();
    const timer = setTimeout(() => {
      if (next === 'pointer') complete();
      else if (next === 'confirm') setReady(true);
    }, duration);
    pending.current = { mode: next, started, timer, key };
    setMode(next);
  }

  return (
    <div className="om-hold" onKeyDown={(e) => {
      if (e.key === 'Escape' && pending.current) {
        e.stopPropagation();
        cancel();
      }
    }}>
      <Button
        variant="primary"
        aria-label={label}
        className="om-hold-button"
        data-holding={mode === 'pointer' || mode === 'keyboard' ? 'true' : undefined}
        style={{ '--hold-duration': `${duration}ms` } as CSSProperties}
        disabled={disabled || mode === 'confirm'}
        onPointerDown={(e) => {
          if (e.button !== 0 || pending.current) return;
          e.currentTarget.setPointerCapture?.(e.pointerId);
          start('pointer');
        }}
        onPointerUp={() => { if (pending.current?.mode === 'pointer') cancel(); }}
        onPointerCancel={cancel}
        onLostPointerCapture={() => { if (pending.current?.mode === 'pointer') cancel(); }}
        onBlur={() => { if (pending.current?.mode !== 'confirm') cancel(); }}
        onKeyDown={(e) => {
          if (e.key !== ' ' && e.key !== 'Enter') return;
          e.preventDefault();
          if (!e.repeat) start('keyboard', e.key);
        }}
        onKeyUp={(e) => {
          if (e.key !== ' ' && e.key !== 'Enter') return;
          e.preventDefault();
          if (pending.current?.mode === 'keyboard' && pending.current.key === e.key) complete();
        }}
      >
        <span className="om-hold-fill" aria-hidden="true" /><span className="om-hold-label">Hold to approve</span>
      </Button>
      <Button disabled={disabled || mode === 'confirm'} onClick={() => start('confirm')}>Use confirmation instead</Button>
      {requiredLevel && <VerificationBadge level={requiredLevel} required />}
      {mode === 'confirm' && <>
        <Button variant="primary" disabled={!ready || disabled} onClick={complete}>Confirm approval</Button>
        <Button onClick={cancel}>Cancel</Button>
      </>}
    </div>
  );
}
