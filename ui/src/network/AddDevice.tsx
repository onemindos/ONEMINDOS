// SPDX-License-Identifier: Apache-2.0
// "Add a device" (CORE-NET-13; contract §12.11; FABRIC.md §3.1). A OneMind machine joins with a
// one-time code shown as a QR: the owner makes the code here, the new machine shows a short match
// code, and the request lands in Approvals with that same code. Nothing joins without approval.
// Phones and laptops (the Tailscale app pointed at this box) need a relay or public name first
// (NETWORKING.md §9.4: in home-network mode the app cannot check the box's certificate), so that
// choice explains itself instead of making a code.
import { useEffect, useMemo, useState } from 'react';
import { Button } from '../components/Button';
import { Dialog } from '../components/Dialog';
import { StatusPill } from '../components/StatusPill';
import { formatCountdown, joinCommands, pendingJoins, qrModules, ROLE_HELP, secondsLeft } from './logic';
import type { FabricSummary, JoinTicket, ReachMode } from './types';
import './network.css';

export interface AddDeviceProps {
  open: boolean;
  onClose: () => void;
  mode: ReachMode;
  /** POST /v1/fabric/join-tickets {role}. */
  createTicket: (role: 'worker' | 'leaf') => Promise<JoinTicket>;
  /** Live list from GET /v1/fabric, so a request appears while the dialog is open. */
  fabric: FabricSummary | null;
  /** Opens the approval card (passkey step-up when set up); the dialog never approves by itself. */
  onReview: (actionId: string) => void;
  now: number;
}

type Step = { kind: 'choose' } | { kind: 'phone' } | { kind: 'busy'; role: 'worker' | 'leaf' } | { kind: 'ticket'; ticket: JoinTicket } | { kind: 'error'; message: string };

export function QrSvg({ text, label }: { text: string; label: string }) {
  const modules = useMemo(() => qrModules(text), [text]);
  const n = modules.length;
  const path = modules.flatMap((row, y) => row.map((on, x) => (on ? `M${x} ${y}h1v1h-1z` : ''))).join('');
  return (
    <svg className="om-net-qr" viewBox={`-4 -4 ${n + 8} ${n + 8}`} role="img" aria-label={label} shapeRendering="crispEdges">
      <rect x={-4} y={-4} width={n + 8} height={n + 8} className="om-net-qr-bg" />
      <path d={path} className="om-net-qr-on" />
    </svg>
  );
}

export function AddDevice({ open, onClose, mode, createTicket, fabric, onReview, now }: AddDeviceProps) {
  const [step, setStep] = useState<Step>({ kind: 'choose' });
  useEffect(() => {
    if (!open) setStep({ kind: 'choose' }); // a code is shown once; closing forgets it
  }, [open]);

  const make = async (role: 'worker' | 'leaf') => {
    setStep({ kind: 'busy', role });
    try {
      setStep({ kind: 'ticket', ticket: await createTicket(role) });
    } catch (e) {
      setStep({ kind: 'error', message: e instanceof Error ? e.message : String(e) });
    }
  };

  const waiting = fabric ? pendingJoins(fabric) : [];
  const left = step.kind === 'ticket' ? secondsLeft(step.ticket.expires_at, now) : 0;

  return (
    <Dialog open={open} onClose={onClose} title="Add a device" size="lg"
      description="Every machine and phone joins your private network only after you approve it."
      actions={<Button onClick={onClose}>{step.kind === 'ticket' ? 'Done' : 'Cancel'}</Button>}>
      {step.kind === 'choose' && (
        <div className="om-net-choices">
          <button type="button" className="om-net-choice" onClick={() => make('worker')}>
            <strong>A OneMind machine that runs apps</strong>
            <span>{ROLE_HELP.worker}</span>
          </button>
          <button type="button" className="om-net-choice" onClick={() => make('leaf')}>
            <strong>A small or remote OneMind machine</strong>
            <span>{ROLE_HELP.leaf}</span>
          </button>
          <button type="button" className="om-net-choice" onClick={() => setStep({ kind: 'phone' })}>
            <strong>A phone or laptop</strong>
            <span>Reach the box away from home with the Tailscale app.</span>
          </button>
        </div>
      )}

      {step.kind === 'busy' && <p aria-live="polite">Making a one-time code…</p>}
      {step.kind === 'error' && (
        <div role="alert">
          <p>The hub could not make a code: {step.message}</p>
          <Button onClick={() => setStep({ kind: 'choose' })}>Back</Button>
        </div>
      )}

      {step.kind === 'phone' && (
        <div>
          {mode === 'lan' ? (
            <p>
              Phones and laptops connect through the Tailscale app pointed at this box. In home-network mode the app
              cannot check this box’s own certificate, so this needs a relay or a public name for the box first
              (Network → Reach). On your home network you can already open <code>onemind.local</code> in a browser.
            </p>
          ) : (
            <p>Approve the device request that appears after you sign in from the Tailscale app.</p>
          )}
          <Button onClick={() => setStep({ kind: 'choose' })}>Back</Button>
        </div>
      )}

      {step.kind === 'ticket' && (
        <div className="om-net-ticket">
          <QrSvg text={step.ticket.qr_payload} label={`Join code ${step.ticket.one_time.join_code} for a ${step.ticket.role}`} />
          <div className="om-net-ticket-body">
            <p className="om-net-bigcode" aria-label="Join code"><code>{step.ticket.one_time.join_code}</code></p>
            <p>
              {left > 0 ? <StatusPill tone="info" label={`Valid ${formatCountdown(left)}`} detail="one use" /> : <StatusPill tone="bad" label="Expired" />}
            </p>
            <p>On the new machine, from a copy of the OneMind repository:</p>
            <pre className="om-net-cmd">{joinCommands(step.ticket).install}</pre>
            <p className="om-net-muted">If OneMind is already installed there: <code>{joinCommands(step.ticket).joinOnly}</code></p>
            <p className="om-net-muted">It pins this box by its certificate <code>{step.ticket.hub_ca_sha256.slice(0, 16)}…</code>, so another machine on your network cannot pretend to be the hub.</p>
          </div>
          <div className="om-net-waiting" aria-live="polite">
            <h3>Requests to join</h3>
            {waiting.length === 0 ? (
              <p className="om-net-muted">Waiting for the machine to ask. It will show a short code; the request here shows the same code.</p>
            ) : (
              <ul className="om-net-list">
                {waiting.map((j) => (
                  <li key={j.join_request_id}>
                    <span><strong>{j.hostname}</strong> · code <code className="om-net-code">{j.match_code}</code></span>
                    <Button size="sm" variant="primary" onClick={() => onReview(j.action_id)}>Check code and approve</Button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </Dialog>
  );
}
