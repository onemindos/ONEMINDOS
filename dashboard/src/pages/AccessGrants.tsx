// SPDX-License-Identifier: Apache-2.0
// Settings > Permissions > Data access and Hardware access (UI parity M3, #1232), through @onemind/sdk.
// Data access: GET /v1/data/grants, the data-commons grants an owner approved (an app, agent or person may read,
// write or count one class of data until a date); DELETE /v1/data/grants/{id} revokes one. Hardware access: GET
// /v1/host-grants, the device, GPU, host-network and realtime grants of installed apps; POST
// /v1/host-grants/{id}/revoke revokes one. Both are asked for as approval-queue actions and granted only by an owner.
// Revoking only takes access away, so the gateway does it at once for an owner (and audits it); everyone else
// sees their own data grants and no revoke button. This screen adds no check of its own.
import { useState } from 'react';
import type { components } from '@onemind/sdk';
import { Button, Card, Table } from '@onemind/ui';
import { ApiError } from '../api/types';
import { useGateway, viaSdk } from '../lib/gateway';
import { usePoll } from '../lib/hooks';
import { useSignedIn } from '../session';
import { Load } from './parts';

type DataGrant = components['schemas']['GrantOut'];
type HostGrant = components['schemas']['HostGrant'];
type Sdk = ReturnType<typeof useGateway>;

const CLASS: Record<DataGrant['data_class'], string> = {
  public: 'Public things (names, shared lists)',
  owner: 'How the box is set up',
  private: 'Private things (files, photos, messages)',
  location: 'Where people and things are',
  activity: 'Activity (health, fitness, habits)',
};
const WHO: Record<string, string> = { app: 'App', agent: 'AI agent', person: 'Person' };
const KIND: Record<HostGrant['kind'], string> = { device: 'A device', gpu: 'The graphics card (GPU)', 'host-network': "The box's own network", realtime: 'Real-time scheduling' };

/** What a data grant allows, in words: "read and count". */
export function allows(g: Pick<DataGrant, 'read' | 'write' | 'aggregate'>): string {
  const can = [g.read && 'read', g.write && 'add records', g.aggregate && 'count'].filter(Boolean) as string[];
  return can.length ? can.join(', ').replace(/, ([^,]*)$/, ' and $1') : 'nothing';
}

const day = (iso: string | null | undefined) => (iso ? new Date(iso).toLocaleDateString() : 'unknown');

function revokeError(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 403) return 'Only an owner can revoke access.';
    if (e.status === 404) return 'That grant is already gone. The list is refreshed.';
    if (e.code === 'network') return 'The box did not answer. Nothing was revoked; try again.';
    return e.message;
  }
  return e instanceof Error ? e.message : String(e);
}

export function AccessGrants() {
  const { token, mock, canDecide } = useSignedIn();
  if (mock) return <Card title="Data and hardware access"><p role="status">Connect to a real box to see who may reach your data and hardware. Demo mode lists none.</p></Card>;
  return <LiveGrants token={token} owner={canDecide === 'yes'} />;
}

function LiveGrants({ token, owner }: { token: string; owner: boolean }) {
  const sdk = useGateway(token);
  return (
    <>
      <DataGrants sdk={sdk} owner={owner} />
      {owner && <HostGrants sdk={sdk} />}
    </>
  );
}

/** A revoke button that asks once more; `job` does the call. */
function useRevoke(reload: () => Promise<void>) {
  const [asking, setAsking] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ tone: 'ok' | 'bad'; text: string }>();
  const revoke = async (what: string, job: () => Promise<unknown>) => {
    setBusy(true);
    setMsg(undefined);
    try {
      await job();
      setMsg({ tone: 'ok', text: `Revoked: ${what} has no access any more.` });
    } catch (e) {
      setMsg({ tone: 'bad', text: revokeError(e) });
    } finally {
      setAsking(undefined);
      setBusy(false);
      await reload();
    }
  };
  const button = (id: string, what: string, job: () => Promise<unknown>) =>
    asking === id ? (
      <span className="dash-actions" role="group" aria-label={`Revoke access for ${what}?`}>
        <Button size="sm" variant="danger" disabled={busy} onClick={() => void revoke(what, job)}>{busy ? 'Revoking…' : 'Revoke'}</Button>
        <Button size="sm" variant="ghost" disabled={busy} onClick={() => setAsking(undefined)}>Keep</Button>
      </span>
    ) : (
      <Button size="sm" variant="ghost" disabled={busy} aria-label={`Revoke access for ${what}`} onClick={() => { setMsg(undefined); setAsking(id); }}>Revoke</Button>
    );
  const note = msg && <p className={`om-note om-tone-${msg.tone}`} role={msg.tone === 'bad' ? 'alert' : 'status'}>{msg.text}</p>;
  return { button, note };
}

function DataGrants({ sdk, owner }: { sdk: Sdk; owner: boolean }) {
  const res = usePoll(() => viaSdk(() => sdk.call<DataGrant[]>({ method: 'GET', path: '/v1/data/grants' })), 60_000);
  const { button, note } = useRevoke(res.reload);
  return (
    <Card title="Data access" subtitle={owner ? 'Apps, agents and people you let reach a kind of data' : 'What you were given access to'}>
      <p>
        Each line is something an owner approved: who may read, add to or count one kind of data, and until when. It ends by itself on that date.
        {owner ? ' Revoke a line to stop it now.' : ' Only an owner can revoke a line.'}
      </p>
      {note}
      <Load res={res} what="Loading data access">
        {(all) => {
          const live = all.filter((g) => g.active);
          const ended = all.length - live.length;
          return (
            <>
              {live.length === 0 ? (
                <p className="om-hint">Nobody has been given access to data beyond what everyone sees.</p>
              ) : (
                <Table
                  caption="Data access"
                  hideCaption
                  rows={live}
                  rowKey={(g) => g.id}
                  columns={[
                    { key: 'who', header: 'Who', render: (g) => `${WHO[g.grantee.kind] ?? g.grantee.kind}: ${g.grantee.id}` },
                    { key: 'what', header: 'Data', render: (g) => CLASS[g.data_class] ?? g.data_class },
                    { key: 'can', header: 'May', render: (g) => allows(g), secondary: true },
                    { key: 'until', header: 'Until', render: (g) => day(g.expires_at), secondary: true },
                    ...(owner ? [{ key: 'x', header: 'Actions', render: (g: DataGrant) => button(g.id, `${g.grantee.id} (${g.data_class})`, () => viaSdk(() => sdk.call({ method: 'DELETE', path: `/v1/data/grants/${encodeURIComponent(g.id)}` }))) }] : []),
                  ]}
                />
              )}
              {ended > 0 && <p className="om-hint">{ended === 1 ? '1 earlier grant has' : `${ended} earlier grants have`} ended or been revoked.</p>}
            </>
          );
        }}
      </Load>
    </Card>
  );
}

function HostGrants({ sdk }: { sdk: Sdk }) {
  const res = usePoll(async () => (await viaSdk(() => sdk.call<components['schemas']['HostGrants']>({ method: 'GET', path: '/v1/host-grants' }))).grants, 60_000);
  const { button, note } = useRevoke(res.reload);
  return (
    <Card title="Hardware access" subtitle="Apps you let reach a device, the GPU or the box's network">
      <p>An app normally runs sealed off from the box. These apps were given one piece of hardware each, after you approved it. Revoke one and the app loses it.</p>
      {note}
      <Load res={res} what="Loading hardware access">
        {(all) => {
          const live = all.filter((g) => g.active);
          return live.length === 0 ? (
            <p className="om-hint">No app has hardware access.</p>
          ) : (
            <Table
              caption="Hardware access"
              hideCaption
              rows={live}
              rowKey={(g) => g.id}
              columns={[
                { key: 'app', header: 'App', render: (g) => g.app_id },
                { key: 'what', header: 'Reaches', render: (g) => [KIND[g.kind] ?? g.kind, g.device_class, g.path].filter(Boolean).join(': ') },
                { key: 'why', header: 'Why', render: (g) => g.reason, secondary: true },
                { key: 'since', header: 'Since', render: (g) => day(g.granted_at), secondary: true },
                { key: 'x', header: 'Actions', render: (g) => button(g.id, g.app_id, () => viaSdk(() => sdk.call({ method: 'POST', path: `/v1/host-grants/${encodeURIComponent(g.id)}/revoke` }))) },
              ]}
            />
          );
        }}
      </Load>
    </Card>
  );
}
