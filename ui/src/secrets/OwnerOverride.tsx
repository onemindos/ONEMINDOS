// SPDX-License-Identifier: Apache-2.0
// F-7 owner override (core/onemind_core/override.py): approve an install whose security scan
// failed. Off unless the box runs with ONEMIND_ALLOW_OWNER_OVERRIDE=1; then owner-only, for an
// install the owner requested, never over malware, with a reason, the app id typed as
// confirmation and, once passkeys exist, a passkey. The dialog explains each refusal instead of
// hiding the option, and the mark shows wherever an overridden install appears.
import { useEffect, useId, useState } from 'react';
import { Button } from '../components/Button';
import { Dialog } from '../components/Dialog';
import { Icon } from '../components/Icon';
import { StatusPill } from '../components/StatusPill';
import { overrideProblems } from './logic';
import type { OwnerOverrideInfo, OwnerOverrideInput } from './types';
import './secrets.css';

export interface OwnerOverrideDialogProps {
  open: boolean;
  app: { id: string; name: string };
  info: OwnerOverrideInfo;
  /** Who asked for the install. An agent's request can never be overridden. */
  requestedBy?: { id: string; kind: 'person' | 'agent' };
  busy?: boolean;
  error?: string;
  onClose: () => void;
  /** The caller adds it to the approve body (approveBody) with the passkey assertion when step_up is passkey. */
  onConfirm: (input: OwnerOverrideInput) => void;
}

export function OwnerOverrideDialog({ open, app, info, requestedBy, busy = false, error, onClose, onConfirm }: OwnerOverrideDialogProps) {
  const [reason, setReason] = useState('');
  const [confirm, setConfirm] = useState('');
  const [touched, setTouched] = useState(false);
  const reasonId = useId();
  const confirmId = useId();
  useEffect(() => {
    if (!open) {
      setReason('');
      setConfirm('');
      setTouched(false);
    }
  }, [open]);

  const close = (
    <Button variant="secondary" onClick={onClose}>
      Close
    </Button>
  );
  if (!info.enabled) {
    return (
      <Dialog open={open} onClose={onClose} title="Owner override is off" size="sm" actions={close}>
        <p>
          {app.name} failed its security scan, and this box does not let anyone install an app that failed (founder decision F-7: not in v0).
        </p>
        <p className="om-hint">
          The box owner can allow it by starting the gateway with <code>ONEMIND_ALLOW_OWNER_OVERRIDE=1</code>. Every use is then marked in red in the activity log.
        </p>
      </Dialog>
    );
  }
  const agentAsked = requestedBy?.kind === 'agent';
  if (!info.eligible || agentAsked) {
    return (
      <Dialog open={open} onClose={onClose} title="This install cannot be overridden" size="sm" actions={close}>
        <p className="om-note om-tone-bad">
          {agentAsked
            ? `${requestedBy?.id} asked for this install. An override is only for installs you request yourself, so an AI cannot talk anyone into skipping a failed scan.`
            : (info.refusal ?? 'The scan does not block this install.')}
        </p>
      </Dialog>
    );
  }

  const found = overrideProblems(info, reason, confirm);
  const valid = !found.reason && !found.confirm;
  const [min, max] = info.reason_length;
  return (
    <Dialog
      open={open}
      onClose={onClose}
      role="alertdialog"
      title={`Install ${app.name} despite its scan?`}
      description={<p className="om-note om-tone-bad">{info.scan_problem}</p>}
      actions={
        <>
          <Button variant="secondary" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button
            variant="danger"
            busy={busy}
            disabled={!valid}
            onClick={() => {
              setTouched(true);
              if (valid) onConfirm({ reason: reason.split(/\s+/).filter(Boolean).join(' '), confirm });
            }}
          >
            {info.step_up === 'passkey' ? 'Override with passkey' : 'Override and install'}
          </Button>
        </>
      }
    >
      <ul className="om-sec-facts">
        <li>It accepts every finding of this scan, for this install only. Malware is never overridden.</li>
        <li>
          Your reason is written to the activity log as a red <strong>owner override</strong> mark that every owner sees.
        </li>
        {info.step_up === 'passkey' && <li>You confirm with your passkey.</li>}
      </ul>
      <div className="om-sec-field">
        <label htmlFor={reasonId}>Why you accept the findings</label>
        <textarea
          id={reasonId}
          rows={3}
          maxLength={max}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          onBlur={() => setTouched(true)}
          aria-invalid={touched && found.reason ? true : undefined}
          aria-describedby={`${reasonId}-hint`}
        />
        <p className="om-hint" id={`${reasonId}-hint`}>
          {touched && found.reason ? found.reason : `${min} to ${max} characters.`}
        </p>
      </div>
      <div className="om-sec-field">
        <label htmlFor={confirmId}>
          Type <code>{info.confirm}</code> to confirm
        </label>
        <input
          id={confirmId}
          type="text"
          autoComplete="off"
          autoCapitalize="off"
          spellCheck={false}
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          aria-invalid={touched && found.confirm ? true : undefined}
        />
      </div>
      {error && (
        <p className="om-note om-tone-bad" role="alert">
          {error}
        </p>
      )}
    </Dialog>
  );
}

/** The red mark on an install that was approved through the override. */
export function OwnerOverrideMark({ mark }: { mark: string }) {
  const reason = mark.replace(/^owner override:\s*/i, '');
  return (
    <span className="om-sec-mark">
      <Icon name="alert" size={16} />
      <StatusPill tone="bad" label="Owner override" detail={reason} dot={false} />
    </span>
  );
}
