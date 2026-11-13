// SPDX-License-Identifier: Apache-2.0
// Hash-routed demo of every IA screen (docs/design/IA.md). Fixtures only, frozen clock.
import { useEffect, useState } from 'react';
import { AppShell, FreshnessPill, ThemeSwitch, ToastProvider, type NavItem } from '../../src';
import { BOX, pending, alerts } from './fixtures';
import { Home } from './screens/Home';
import { Apps } from './screens/Apps';
import { AppPage } from './screens/AppPage';
import { Approvals } from './screens/Approvals';
import { Activity } from './screens/Activity';
import { Nodes } from './screens/Nodes';
import { Backups } from './screens/Backups';
import { Updates } from './screens/Updates';
import { Notifications } from './screens/Notifications';
import { Settings } from './screens/Settings';
import { Gallery } from './screens/Gallery';
import { HomeLauncher } from './home/HomeLauncher';
import { StoreDemo } from './store/StoreDemo';
import { SystemDemo } from './settings/SystemDemo';
import { AppearanceDemo } from './customize/AppearanceDemo';
import { ShellScreens } from './shell/ShellScreens';
import { NetworkDemo } from './network/NetworkDemo';
import { BackupsDemo } from './backups/BackupsDemo';

export const NAV: NavItem[] = [
  { id: 'home', label: 'Home', href: '#/home', icon: 'home', primary: true },
  { id: 'apps', label: 'Apps', href: '#/apps', icon: 'apps', primary: true },
  { id: 'approvals', label: 'Approvals', href: '#/approvals', icon: 'approvals', primary: true, badge: pending.length, badgeLabel: `${pending.length} waiting` },
  { id: 'activity', label: 'Activity', href: '#/activity', icon: 'activity', primary: true },
  { id: 'notifications', label: 'Alerts', href: '#/notifications', icon: 'bell', badge: alerts.filter((a) => !a.acked).length, badgeLabel: `${alerts.filter((a) => !a.acked).length} open` },
  { id: 'nodes', label: 'Nodes', href: '#/nodes', icon: 'nodes', group: 'System' },
  { id: 'network', label: 'Network', href: '#/network', icon: 'link', group: 'System' },
  { id: 'backups', label: 'Backups', href: '#/backups', icon: 'backups', group: 'System' },
  { id: 'updates', label: 'Updates', href: '#/updates', icon: 'updates', group: 'System' },
  { id: 'settings', label: 'Settings', href: '#/settings', icon: 'settings', group: 'System' },
  { id: 'gallery', label: 'Components', href: '#/gallery', icon: 'info', group: 'Design system' },
];

function route(): { id: string; arg?: string } {
  const [, id = 'home', arg] = window.location.hash.split('/');
  return { id, arg };
}

export function DemoApp() {
  const [r, setR] = useState(route);
  useEffect(() => {
    const on = () => {
      setR(route());
      window.scrollTo(0, 0);
      document.getElementById('om-main')?.focus({ preventScroll: true });
    };
    window.addEventListener('hashchange', on);
    return () => window.removeEventListener('hashchange', on);
  }, []);

  const screen = (() => {
    switch (r.id) {
      case 'apps':
        return <Apps />;
      case 'app':
        return <AppPage id={r.arg ?? 'home-assistant'} />;
      case 'approvals':
        return <Approvals />;
      case 'activity':
        return <Activity />;
      case 'nodes':
        return <Nodes />;
      case 'backups':
        return <Backups />;
      case 'updates':
        return <Updates />;
      case 'notifications':
        return <Notifications />;
      case 'settings':
        return <Settings />;
      case 'gallery':
        return <Gallery />;
      case 'system': return <SystemDemo arg={r.arg} />;
      case 'appearance': return <AppearanceDemo arg={r.arg} />;
      case 'store': return <StoreDemo />;
      case 'home': return <HomeLauncher variant={r.arg} />;
      case 'shell': return <ShellScreens arg={r.arg} />;
      case 'network': return <NetworkDemo arg={r.arg} />;
      case 'backup': return <BackupsDemo arg={r.arg} />;
      default:
        return <Home />;
    }
  })();

  return (
    <ToastProvider>
      <AppShell
        boxName={BOX}
        nav={NAV}
        current={r.id === 'app' ? 'apps' : r.id}
        status={<FreshnessPill state="live" detail="hub updated just now" />}
        account={
          <>
            <span className="d-demo-flag">Demo data</span>
            <span className="d-hide-compact">
              <ThemeSwitch />
            </span>
          </>
        }
      >
        {screen}
      </AppShell>
    </ToastProvider>
  );
}
