// SPDX-License-Identifier: Apache-2.0
// Settings on @onemind/ui SettingsLayout. Appearance is live (saved per person in this browser
// until the §12 preferences route lands). About shows GET /v1/instance. Machines, storage, backups,
// updates and automation are real screens, so their sections redirect there (App.tsx).
import { useParams } from 'react-router';
import { AppearanceSettings, Card, PageHeader, SETTINGS_SECTIONS, SettingsLayout, type SettingsSectionId } from '@onemind/ui';
import { useHub } from '../data/hub';
import { Account } from './Account';
import { Inbox } from './Inbox';
import { Tokens } from './Tokens';
import { Users } from './Users';
import { href } from '../shell/routes';

const IDS = new Set(SETTINGS_SECTIONS.map((s) => s.id));

function About() {
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
      <p className="om-hint">Diagnostic bundles and component versions come with §12 (About &amp; diagnostics).</p>
    </>
  );
}

export function Settings() {
  const { section } = useParams();
  const explicit = !!section && IDS.has(section as SettingsSectionId);
  const current = (explicit ? section : 'appearance') as SettingsSectionId;
  let body;
  if (current === 'appearance')
    body = (
      <>
        <PageHeader title="Appearance" lede="Theme, accent, wallpaper and layout. Saved for you only; it changes nothing on the box, so it needs no approval." />
        <AppearanceSettings />
      </>
    );
  else if (current === 'account') body = <Account />;
  else if (current === 'users') body = <Users />;
  else if (current === 'agents') body = <Tokens />;
  else if (current === 'notifications') body = <Inbox />;
  // devices, network, storage, backups, updates and automation have their own screens (App.tsx redirects).
  else body = <About />;
  return (
    <SettingsLayout current={current} explicit={explicit} hrefFor={(id) => href.setting(id)} indexHref={href.settings}>
      {body}
    </SettingsLayout>
  );
}
