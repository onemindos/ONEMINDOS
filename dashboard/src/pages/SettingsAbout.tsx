// SPDX-License-Identifier: Apache-2.0
// Settings > About: this OneMind as the hub reports it (GET /v1/instance).
import { Card, PageHeader } from '@onemind/ui';
import { useHub } from '../data/hub';
import { AboutBox } from './AboutBox';

export function SettingsAbout() {
  const hub = useHub();
  const i = hub.instance.data;
  return (
    <>
      <PageHeader title="About" lede="This OneMind, as the hub reports it (GET /v1/instance)." />
      <Card title={i?.name ?? 'OneMind'} level={2}>
        {i ? (
          <dl className="om-facts">
            <div>
              <dt>Version</dt>
              <dd>{i.version}</dd>
            </div>
            <div>
              <dt>Hub node</dt>
              <dd>
                <code>{i.hub_node_id}</code>
              </dd>
            </div>
            <div>
              <dt>Nodes reporting</dt>
              <dd>{hub.nodes.data?.length ?? 'unknown'}</dd>
            </div>
          </dl>
        ) : (
          <p className="om-hint">{hub.instance.error ? `Could not read the instance: ${hub.instance.error.message}` : 'Loading…'}</p>
        )}
      </Card>
      <AboutBox />
      <p className="om-hint">Diagnostic bundles come with §12 (About &amp; diagnostics).</p>
    </>
  );
}
