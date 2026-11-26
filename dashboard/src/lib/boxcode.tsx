// SPDX-License-Identifier: Apache-2.0
// Confirming at the box (D-028; gateway permissions design 3.11, N-1 = b). Before the household's first
// proven key, an L2 approval or change needs a passkey plus the 6-digit code the box's own screen shows
// (onemind-screen on tty1). The hub never sends the code over the network: the person reads it at the box
// and types it here. askBoxCode is called from the API client (no React there), so a host mounted once in
// the app draws the dialog and answers the promise.
import { useEffect, useState } from 'react';
import { Button, Dialog } from '@onemind/ui';
import { ApiError } from '../api/types';

type Ask = { what: string; resolve: (code: string) => void; reject: (e: unknown) => void };
let show: ((a: Ask) => void) | undefined;

/** Plain words for the change a box code confirms (the hub's op, or "approve <type>"). */
export function boxCodeWhat(op: string): string {
  return op.replace(/^confirm /, '').replace(/[._]/g, ' ');
}

/** Ask the person for the code the box's screen shows. Rejects when they cancel or no host is mounted. */
export function askBoxCode(what: string): Promise<string> {
  return new Promise((resolve, reject) => {
    if (!show) {
      reject(new ApiError(409, 'conflict', 'This needs the code on the box\'s own screen. Open the dashboard and try again.', 'box_code_required'));
      return;
    }
    show({ what, resolve, reject });
  });
}

export function BoxCodeHost() {
  const [ask, setAsk] = useState<Ask | undefined>();
  const [code, setCode] = useState('');
  useEffect(() => {
    show = (a) => { setCode(''); setAsk(a); };
    return () => { show = undefined; };
  }, []);
  if (!ask) return null;
  const digits = code.replace(/\s+/g, '');
  const done = (ok: boolean) => {
    setAsk(undefined);
    if (ok) ask.resolve(digits);
    else ask.reject(new ApiError(400, 'unknown', 'Cancelled: nothing was changed.', 'cancelled'));
  };
  return (
    <Dialog open onClose={() => done(false)} title="Confirm at the box" role="alertdialog" size="sm"
      description={<>
        <p>Your box has no proven key yet, so this change ({boxCodeWhat(ask.what)}) is confirmed by someone standing at it. Its own screen now shows a 6-digit code. It works once, for 2 minutes.</p>
        <p>Add a proven key under Settings &gt; Security &gt; Sign-in keys to skip this step.</p>
      </>}
      actions={<>
        <Button onClick={() => done(false)}>Cancel</Button>
        <Button variant="primary" disabled={!/^\d{6}$/.test(digits)} onClick={() => done(true)}>Continue</Button>
      </>}>
      <label>Code on the box's screen <input aria-label="Code on the box's screen" inputMode="numeric" autoComplete="one-time-code"
        value={code} maxLength={7} onChange={(e) => setCode(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter' && /^\d{6}$/.test(digits)) done(true); }} /></label>
    </Dialog>
  );
}
