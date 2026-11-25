// SPDX-License-Identifier: Apache-2.0
// Settings > About, Power and UPS (IMG-06, #244): the UPS plugged into the box by USB, from GET /v1/system/ups
// (the gateway reads NUT's upsd on the box). Read only: on a low battery the box shuts itself down in order
// (apps, then Kubernetes, then the data disk), so there is nothing to press here.
import { Card, StatusPill, type Tone } from '@onemind/ui';
import type { UpsStatus } from '../api/client';
import { usePoll } from '../lib/hooks';
import { useSignedIn } from '../session';

const STATE: Record<UpsStatus['state'], { tone: Tone; label: string; hint: string }> = {
  none: { tone: 'neutral', label: 'No UPS', hint: 'No UPS is connected. Plug one in by USB and restart the box: it is found and watched by itself.' },
  online: { tone: 'ok', label: 'On mains power', hint: 'If the power goes out, the box keeps running on the UPS battery.' },
  on_battery: { tone: 'warn', label: 'On battery', hint: 'The power is out. When the battery runs low the box shuts down cleanly by itself.' },
  low_battery: { tone: 'bad', label: 'Battery low', hint: 'The box is shutting down cleanly now: apps first, then Kubernetes, then the data disk.' },
  unknown: { tone: 'warn', label: 'No fresh data', hint: 'A UPS is set up but is not answering. Check its USB cable, then restart the box.' },
};

function minutes(s: number) {
  const m = Math.round(s / 60);
  return m >= 60 ? `${Math.floor(m / 60)} h ${m % 60} min` : `${m} min`;
}

export function UpsCard() {
  const { api } = useSignedIn();
  const ups = usePoll(async () => (api.ups ? api.ups() : Promise.reject(new Error('unsupported'))), 10_000);

  let body;
  if (!api.ups) body = <p className="om-hint">Demo mode has no UPS. A real hub shows the UPS plugged into it here.</p>;
  else if (ups.error?.status === 403) body = <p className="om-hint">Power details are not available for your account.</p>;
  else if (!ups.data) body = <p className="om-hint">{ups.error ? `Could not read the UPS: ${ups.error.message}` : 'Loading the UPS…'}</p>;
  else {
    const d = ups.data;
    const s = STATE[d.state];
    const facts: [string, string][] = [];
    if (d.model) facts.push(['Model', d.model]);
    if (d.battery_percent != null) facts.push(['Battery', `${d.battery_percent}%`]);
    if (d.runtime_seconds != null) facts.push(['Time on battery', minutes(d.runtime_seconds)]);
    if (d.load_percent != null) facts.push(['Load', `${d.load_percent}%`]);
    body = (
      <>
        <p role="status"><StatusPill tone={s.tone} label={s.label} /></p>
        <p className="om-hint">{s.hint}</p>
        {facts.length > 0 && (
          <dl className="om-facts">
            {facts.map(([k, v]) => (
              <div key={k}>
                <dt>{k}</dt>
                <dd>{v}</dd>
              </div>
            ))}
          </dl>
        )}
      </>
    );
  }
  return <Card title="Power and UPS">{body}</Card>;
}
