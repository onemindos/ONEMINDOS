// SPDX-License-Identifier: Apache-2.0
// Settings > About: this box as a device card, with the technical facts one tap away. Family-facing
// copy only: no routes, no section numbers (those live under "Technical details").
import { Link } from 'react-router';
import { Card, PageHeader } from '@onemind/ui';
import { useHub } from '../data/hub';
import { usePoll } from '../lib/hooks';
import { useSignedIn } from '../session';
import { SpatialStatus } from '../screens/spatial/SpatialStatus';
import { AboutBox } from './AboutBox';
import { DeviceCard } from './DeviceCard';
import { PrivacyCard } from './PrivacyCard';
import { RenameBoxCard } from './RenameBoxCard';
import { SettingsBusEvents } from './SettingsBusEvents';
import { SettingsEngine } from './SettingsEngine';
import { SettingsSubjects } from './SettingsSubjects';
import { UpsCard } from './UpsCard';

export function SettingsAbout() {
  const hub = useHub();
  const { api, signOut } = useSignedIn();
  const i = hub.instance.data;
  // Demo mode has no device facts, a child has no nodes:read: the card then shows the name and version only.
  const about = usePoll(async () => (api.about ? api.about() : Promise.reject(new Error('unsupported'))), 30_000);
  const node = about.data?.nodes.find((n) => n.node_id === about.data?.hub_node_id) ?? about.data?.nodes[0];
  return (
    <>
      <PageHeader title="About" lede="This box at a glance." />
      {i ? (
        <DeviceCard name={i.name ?? 'OneMind'} version={i.version} node={node} onLogOut={signOut} />
      ) : (
        <p className="om-hint">{hub.instance.error ? `Could not read this box: ${hub.instance.error.message}` : 'Loading…'}</p>
      )}
      <RenameBoxCard current={i?.name} />
      <UpsCard />
      <PrivacyCard />
      <details className="dash-tech">
        <summary>Technical details</summary>
        <dl className="om-facts">
          <div>
            <dt>Hub node</dt>
            <dd>
              <code>{i?.hub_node_id ?? 'unknown'}</code>
            </dd>
          </div>
          <div>
            <dt>Nodes reporting</dt>
            <dd>{hub.nodes.data?.length ?? 'unknown'}</dd>
          </div>
        </dl>
        <p className="om-hint">
          Read from <code>GET /v1/instance</code>, <code>GET /v1/nodes</code> and <code>GET /v1/os/about</code>.
        </p>
        <AboutBox />
      </details>
      <SettingsEngine />
      <SettingsBusEvents />
      <SettingsSubjects />
      <SpatialStatus />
      <Card title="Plugin signing trust">
        <p>Owners can enroll public signing keys for private plugins. Changes wait for approval.</p>
        <Link to="/settings/plugin-keys">Manage plugin signing keys</Link>
      </Card>
    </>
  );
}
