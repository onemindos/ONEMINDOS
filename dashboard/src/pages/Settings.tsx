// SPDX-License-Identifier: Apache-2.0
// Settings on @onemind/ui SettingsLayout. Appearance is live (saved per person in this browser
// until the §12 preferences route lands). About shows GET /v1/instance. Every other section says
// which work stream brings its API, instead of showing controls that would do nothing.
import { useParams } from 'react-router';
import { AppearanceSettings, Card, EmptyState, PageHeader, SETTINGS_SECTIONS, SettingsLayout, type SettingsSectionId } from '@onemind/ui';
import { useHub } from '../data/hub';
import { href } from '../shell/routes';

/** Section → the work stream (docs/leap/STATUS.md epic) and the §12 API that brings it. */
export const COMING: Record<Exclude<SettingsSectionId, 'appearance' | 'about'>, { stream: string; api: string }> = {
  account: { stream: 'CORE-SEC-2 (identity)', api: '/v1/auth/passkeys, /v1/auth/sessions' },
  users: { stream: 'UMB-ACCT (identity)', api: '/v1/people' },
  agents: { stream: 'CORE-SEC (identity)', api: '/v1/tokens, /v1/agents' },
  devices: { stream: 'CORE-FABRIC (core-net)', api: '/v1/fabric/join-codes' },
  network: { stream: 'CORE-FABRIC (core-net)', api: '/v1/fabric, /v1/tls' },
  storage: { stream: 'UMB-STOR', api: '/v1/storage' },
  backups: { stream: 'CORE-BACKUP', api: '/v1/backups' },
  updates: { stream: 'CORE-UPDATE', api: '/v1/os/status' },
  notifications: { stream: 'CORE-NOTIFY (notify-monitor)', api: '/v1/notify/routes' },
  automation: { stream: 'CORE-AUTO', api: '/v1/automations, /v1/policies' },
};

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
  const meta = SETTINGS_SECTIONS.find((s) => s.id === current)!;
  let body;
  if (current === 'appearance')
    body = (
      <>
        <PageHeader title="Appearance" lede="Theme, accent, wallpaper and layout. Saved for you only; it changes nothing on the box, so it needs no approval." />
        <AppearanceSettings />
      </>
    );
  else if (current === 'about') body = <About />;
  else {
    const c = COMING[current];
    body = (
      <EmptyState icon="settings" title={`${meta.label}: coming with ${c.stream}`} command={`GET ${c.api.split(',')[0]!.trim()}`}>
        <p>
          This hub does not serve these settings yet. They arrive with the {c.stream} work stream ({c.api}, contract §12). Nothing here is a placeholder control that would do
          nothing.
        </p>
      </EmptyState>
    );
  }
  return (
    <SettingsLayout current={current} explicit={explicit} hrefFor={(id) => href.setting(id)} indexHref={href.settings}>
      {body}
    </SettingsLayout>
  );
}
