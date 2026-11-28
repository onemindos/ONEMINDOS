// SPDX-License-Identifier: Apache-2.0
import { useEffect, useMemo } from 'react';
import { Link } from 'react-router';
import { OneMind } from '@onemind/sdk';
import { Card } from '@onemind/ui';
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
  return (
    <Card title="Recent" level={2} className="dash-recent">
      {loading ? <p className="om-hint">Loading recent visits…</p> : error || !data ? <p className="om-hint">Recent visits are unavailable.</p> : items.length
        ? <ul className="dash-recent-list">{items.map((item) => <li key={item.id}><Link to={item.path}>{item.label}</Link></li>)}</ul>
        : <p className="om-hint">No recent visits.</p>}
    </Card>
  );
}
