// SPDX-License-Identifier: Apache-2.0
import { useMemo } from 'react';
import { OneMind, type components } from '@onemind/sdk';
import { Card, StatusPill, type Tone } from '@onemind/ui';
import { useHub } from '../data/hub';
import { usePoll } from '../lib/hooks';
import { useSignedIn } from '../session';

type Report = components['schemas']['MachineFitReport'];
type Machine = components['schemas']['MachineFit'];
const verdicts: Record<Machine['verdict'], { label: string; tone: Tone }> = {
  yes: { label: 'Runs here', tone: 'ok' },
  'yes-but-slow': { label: 'Runs with limits', tone: 'warn' },
  'not-on-this-machine': { label: 'Does not fit', tone: 'bad' },
  'not-checked': { label: 'Not checked', tone: 'neutral' },
};

export function MachineFitDetails({ report, hubID, nameFor }: {
  report?: Report; hubID?: string; nameFor: (id: string) => string;
}) {
  const local = report?.nodes.find((node) => node.node_id === hubID);
  const others = (report?.nodes ?? []).filter((node) => node.node_id !== hubID);
  const row = (machine: Machine) => {
    const verdict = verdicts[machine.verdict] ?? verdicts['not-checked'];
    return <li key={machine.node_id}>
      <strong>{nameFor(machine.node_id)}</strong>{' '}
      <StatusPill label={verdict.label} tone={verdict.tone} />
      {machine.reasons.length > 0 && <ul>{machine.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>}
    </li>;
  };
  return <>
    <h3>This machine</h3>
    {local ? <ul>{row(local)}</ul> : <p>Not checked</p>}
    <h3>Other machines</h3>
    {others.length ? <ul>{others.map(row)}</ul> : <p>No other machines reported fit.</p>}
  </>;
}

export function AppMachineFit({ appId }: { appId: string }) {
  const { token, mock } = useSignedIn();
  const hub = useHub();
  const sdk = useMemo(() => new OneMind({ baseUrl: window.location.origin, token, retries: 1 }), [token]);
  const response = usePoll(() => mock ? Promise.resolve(undefined) : sdk.call<components['schemas']['AppPlacement']>({
    method: 'GET', path: `/v1/apps/${encodeURIComponent(appId)}/placement`,
  }), 0);
  return <Card title="Machine fit">
    {response.loading ? <p role="status">Checking machine fit…</p> :
      <MachineFitDetails report={response.error ? undefined : response.data?.fit ?? undefined}
        hubID={hub.instance.data?.hub_node_id} nameFor={(id) => hub.nodes.data?.find((node) => node.node_id === id)?.hostname ?? id} />}
  </Card>;
}
