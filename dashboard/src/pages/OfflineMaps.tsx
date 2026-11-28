// SPDX-License-Identifier: Apache-2.0
// Storage > Offline maps: the map packs installed for the Offline Maps app (GET /v1/map/packs), how much disk is free
// for them, and the map sites set up on this box (GET /v1/sites, read only). Taking a pack away only FILES a request
// (map.pack.remove) that waits in Approvals; nothing is deleted here. Adding a region is `onemind map packs add` (no region list route yet: #1280).
import { useState } from 'react';
import { Link } from 'react-router';
import { Button, Card, Dialog } from '@onemind/ui';
import { usePoll } from '../lib/hooks';
import { useGateway, viaSdk } from '../lib/gateway';
import { Load, useRun } from './parts';

const mb = (n: number) => `${(n / 1_000_000).toFixed(n >= 100_000_000 ? 0 : 1)} MB`;
const gb = (n: number) => `${(n / 1_000_000_000).toFixed(1)} GB`;

export function OfflineMaps({ token }: { token: string }) {
  const client = useGateway(token);
  const run = useRun();
  const packs = usePoll(async () => {
    const p = await viaSdk(() => client.maps.packs());
    if (!p || !Array.isArray(p.packs)) throw new Error('The hub returned an invalid map pack list.');
    return p;
  }, 60_000);
  const sites = usePoll(async () => {
    const list = await viaSdk(() => client.maps.sites());
    if (!Array.isArray(list)) throw new Error('The hub returned an invalid map site list.');
    return list;
  }, 60_000);
  const [asking, setAsking] = useState<{ id: string; region: string }>();
  const [filed, setFiled] = useState<string>();
  // An account that may not read maps (for example a child) is simply not offered the card.
  if (packs.error?.status === 403 && !packs.data) return null;
  return (
    <Card as="article" title="Offline maps">
      <p>Map packs let maps work without the internet. They use disk space on this box.</p>
      {filed && (
        <p role="status" className="om-note">
          Request {filed} was filed. <Link to="/approvals">Review it in Approvals</Link>: the pack stays until you approve.
        </p>
      )}
      <Load res={packs} what="Reading the map packs">
        {(p) => (
          <>
            {p.free_bytes === null ? (
              <p className="om-hint">Offline Maps is not set up on this box, so there is no map disk to measure.</p>
            ) : (
              <p>{gb(p.free_bytes)} free for map packs.</p>
            )}
            {p.packs.length === 0 ? (
              <p className="om-hint">No map packs are installed.</p>
            ) : (
              <ul aria-label="Installed map packs">
                {p.packs.map((x) => (
                  <li key={x.id}>
                    <strong>{x.region}</strong> · {mb(x.bytes)} · installed {new Date(x.installed_at).toLocaleDateString()}{' '}
                    <Button size="sm" variant="ghost" aria-label={`Ask to take away the ${x.region} pack`} onClick={() => setAsking({ id: x.id, region: x.region })}>
                      Ask to take away
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </Load>
      <h3>Map sites</h3>
      <Load res={sites} what="Reading the map sites">
        {(list) =>
          list.length === 0 ? (
            <p className="om-hint">No map sites are set up. A site is a building or property with floors and areas.</p>
          ) : (
            <ul aria-label="Map sites">
              {list.map((s) => (
                <li key={s.id}>
                  <strong>{s.name}</strong> · {s.floors?.length ?? 0} floors · {s.areas?.length ?? 0} areas
                </li>
              ))}
            </ul>
          )
        }
      </Load>
      <Dialog
        open={asking !== undefined}
        onClose={() => setAsking(undefined)}
        title={`Ask to take away the ${asking?.region ?? ''} pack?`}
        description="This files a request. The pack is only deleted if you approve it in Approvals, and you can download it again later."
        actions={
          <>
            <Button variant="ghost" onClick={() => setAsking(undefined)}>
              Keep it
            </Button>
            <Button
              onClick={() => {
                const a = asking;
                setAsking(undefined);
                if (a) void run(async () => { const action = await viaSdk(() => client.maps.requestPackRemoval(a.id)); setFiled(action.id); }, 'Could not file the request');
              }}
            >
              File the request
            </Button>
          </>
        }
      />
    </Card>
  );
}
