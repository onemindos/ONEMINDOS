// SPDX-License-Identifier: Apache-2.0
import { useEffect, useMemo } from 'react';
import { Link } from 'react-router';
import { OneMind } from '@onemind/sdk';
import { useHub } from '../data/hub';
import { RECENT_UPDATED } from '../data/homeRecent';
import { usePoll } from '../lib/hooks';
import { SCREENS } from '../screens/registry';
import { useSignedIn } from '../session';
import { useShell } from '../shell/Shell';
import { showsNav } from '../shell/roles';
import { href } from '../shell/routes';

export function HomeRecent() {
  const { token, mock } = useSignedIn();
  const sdk = useMemo(() => new OneMind({ baseUrl: window.location.origin, token }), [token]);
  const { view, role } = useShell();
  const hub = useHub();
  const { data, error, loading, reload } = usePoll(async () => mock ? undefined : (await sdk.me.home.get()).home.recent ?? [], 30_000);
  useEffect(() => {
    const refresh = () => void reload();
    window.addEventListener(RECENT_UPDATED, refresh);
    return () => window.removeEventListener(RECENT_UPDATED, refresh);
  }, [reload]);
  const items = (data ?? []).flatMap((id) => {
    const [kind, key] = id.split(':');
    if (kind === 'sys') {
      const screen = SCREENS.find((s) => s.id === key && !s.hidden && showsNav(s.id, view, role));
      return screen ? [{ id, label: screen.title, path: screen.path }] : [];
    }
    const app = kind === 'app' && hub.apps.data?.find((a) => a.id === key);
    return app ? [{ id, label: app.name ?? app.id, path: app.installed ? href.manage(app.id) : href.app(app.id) }] : [];
  });
  return <section aria-label="Recent">
    <h2>Recent</h2>
    {loading ? <p>Loading recent visits…</p> : error || !data ? <p>Recent visits are unavailable.</p> : items.length
      ? <ul>{items.map((item) => <li key={item.id}><Link to={item.path}>{item.label}</Link></li>)}</ul>
      : <p>No recent visits.</p>}
  </section>;
}
