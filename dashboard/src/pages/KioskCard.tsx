// SPDX-License-Identifier: Apache-2.0
// Settings > Appearance, "This box's screen" (UX-07, #242): turns the monitor plugged into the box from the text
// screen into the full-screen dashboard. GET and PUT /v1/instance/kiosk through @onemind/sdk, owner only. The same
// switch is `onemind kiosk` on the box. The kiosk browser keeps no token: a keyboard on the box can still sign in.
import { useState } from 'react';
import { Button, Card } from '@onemind/ui';
import { usePoll } from '../lib/hooks';
import { useGateway, viaSdk } from '../lib/gateway';
import { useSignedIn } from '../session';
import { Load, useRun } from './parts';

export function KioskCard() {
  const { token, mock, canDecide } = useSignedIn();
  // Demo mode has no box screen; a person who is known not to be an owner never sees a switch that would be refused.
  if (mock || canDecide === 'no') return null;
  return <LiveKiosk token={token} />;
}

function LiveKiosk({ token }: { token: string }) {
  const client = useGateway(token);
  const run = useRun();
  const state = usePoll(() => viaSdk(() => client.instance.kiosk.get()), 30_000);
  const [busy, setBusy] = useState(false);
  // A viewer the gateway says is not an owner (403) sees nothing here, not an error.
  if (state.error?.status === 403 && state.data === undefined) return null;
  async function set(enabled: boolean) {
    setBusy(true);
    await run(async () => {
      await viaSdk(() => client.instance.kiosk.set(enabled));
      await state.reload();
    }, enabled ? 'Could not turn the box screen on' : 'Could not turn the box screen off');
    setBusy(false);
  }
  return (
    <Card as="section" title="This box's screen">
      <Load res={state} what="Reading the box screen">
        {(k) => (
          <>
            <p>
              {k.enabled
                ? 'On: the monitor plugged into this box shows the dashboard full screen.'
                : 'Off: the monitor plugged into this box shows the plain text screen.'}
            </p>
            <Button disabled={busy} onClick={() => void set(!k.enabled)}>
              {k.enabled ? 'Turn the box screen off' : 'Turn the box screen on'}
            </Button>
            <p className="om-hint">
              The screen switches within a few seconds. The screen keeps no sign-in: someone at the box still signs in with a keyboard. On the box the same switch is <code>onemind kiosk enable</code> and <code>onemind kiosk disable</code>.
            </p>
          </>
        )}
      </Load>
    </Card>
  );
}
