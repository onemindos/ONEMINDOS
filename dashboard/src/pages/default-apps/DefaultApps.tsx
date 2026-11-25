// SPDX-License-Identifier: Apache-2.0
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router';
import { OneMind, OneMindError } from '@onemind/sdk';
import { Button, Card, CATEGORIES } from '@onemind/ui';
import type { CatalogApp } from '../../api/types';
import { openUrl } from '../../data/adapters';
import { useHub } from '../../data/hub';
import { usePoll } from '../../lib/hooks';
import { openAppOrSay } from '../../lib/openApp';
import { useSignedIn } from '../../session';
import { href } from '../../shell/routes';

function purposes(apps: CatalogApp[]) {
  const groups = new Map<string, CatalogApp[]>();
  for (const app of apps) {
    const purpose = app.browser ? 'browser' : app.category;
    if (!app.installed || !app.web_port || !purpose || !/^[a-z][a-z0-9-]{0,39}$/.test(purpose)) continue;
    const group = groups.get(purpose);
    if (group) group.push(app);
    else groups.set(purpose, [app]);
  }
  return groups;
}

function Choices({ settings }: { settings: boolean }) {
  const { token, api } = useSignedIn();
  const { apps } = useHub();
  const navigate = useNavigate();
  const client = useMemo(() => new OneMind({ baseUrl: window.location.origin, token }), [token]);
  const current = usePoll(() => client.me.home.get(), 30_000);
  const [picks, setPicks] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const groups = useMemo(() => purposes(apps.data ?? []), [apps.data]);

  async function save(purpose: string, appId: string) {
    if (!current.data || saving) return;
    setSaving(true);
    setError('');
    try {
      const { home, etag } = current.data;
      const defaults = { ...home.default_apps };
      if (appId) defaults[purpose] = appId;
      else delete defaults[purpose];
      await client.me.home.save({ ...home, default_apps: defaults }, etag);
    } catch (e) {
      setError(e instanceof OneMindError && e.status === 412
        ? 'Your Home changed on another device. Check the latest choice and try again.'
        : 'Your choice could not be saved. Check the connection and try again.');
    } finally {
      await current.reload();
      setSaving(false);
    }
  }

  function launch(app: CatalogApp) {
    if (app.browser) navigate(href.browser(app.id));
    else {
      const url = openUrl(app);
      if (url) openAppOrSay(api, app.name || app.id, url);
    }
  }

  return <Card title={settings ? 'Default apps' : 'Open with'}>
    {error && <p role="alert">{error}</p>}
    {apps.error || current.error
      ? <p role="status">Could not read your apps or preferences. <Button onClick={() => { void current.reload(); void apps.reload(); }}>Retry</Button></p>
      : !apps.data || !current.data ? <p role="status">Loading apps and preferences…</p>
      : !groups.size ? <p>No installed apps offer a window for this account.</p>
      : Array.from(groups, ([purpose, options]) => {
        const label = purpose === 'browser' ? 'Web browser' : CATEGORIES.find((c) => c.slug === purpose)?.label ?? purpose;
        const saved = current.data?.home.default_apps?.[purpose] ?? '';
        const selected = (settings ? saved : picks[purpose] ?? saved);
        const app = options.find((a) => a.id === selected);
        const canOpen = app && (app.browser || openUrl(app));
        return <div key={purpose}>
          <label>{label}{' '}
            <select value={app?.id ?? ''} disabled={saving} onChange={(e) => {
              const id = e.target.value;
              if (settings) void save(purpose, id);
              else setPicks((old) => ({ ...old, [purpose]: id }));
            }}>
              <option value="">{settings ? 'Ask each time' : 'Choose an app'}</option>
              {options.map((a) => <option key={a.id} value={a.id}>{a.name || a.id}</option>)}
            </select>
          </label>{' '}
          {!settings && <Button disabled={!canOpen} onClick={() => app && launch(app)}>{app ? `Open with ${app.name || app.id}` : 'Open'}</Button>}
          {!settings && app && !canOpen && <p>Open the dashboard from the box’s local domain to launch this app.</p>}
        </div>;
      })}
  </Card>;
}

export function DefaultApps() {
  const { mock, person } = useSignedIn();
  return mock ? <p role="status">Connect to your hub to choose default apps.</p> : <Choices settings key={person} />;
}

export function OpenWith() {
  const { mock, person } = useSignedIn();
  return mock ? null : <Choices settings={false} key={person} />;
}
