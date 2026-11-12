// SPDX-License-Identifier: Apache-2.0
// Demo of the shell-wide pieces (src/shell): #/shell/<screen>.
// palette, palette-search, notifications, toasts, states, onboarding-1 … onboarding-6.
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Card,
  CommandPalette,
  NotificationBell,
  NotificationCentre,
  Onboarding,
  PageHeader,
  PaletteTrigger,
  StateView,
  buildPaletteCommands,
  markAllNotificationsRead,
  pushRecentCommand,
  setNotificationsRead,
  toastForNotification,
  toastForRequest,
  usePaletteHotkey,
  useToast,
  type OnboardingDraft,
  type PaletteCommand,
  type ShellNotification,
} from '../../../src';
import { nodes, pending } from '../fixtures';
import './shell-demo.css';
import { NOW, hub, notifications, paletteApps, recent as initialRecent, starterApps } from './fixtures';

const go = (href: string) => {
  window.location.hash = href;
};

const SCREENS: Array<[string, string]> = [
  ['palette', 'Command palette'],
  ['palette-search', 'Palette search'],
  ['notifications', 'Notifications'],
  ['toasts', 'Toasts'],
  ['states', 'States'],
  ['onboarding-1', 'Onboarding'],
];

function ShellNav({ current }: { current: string }) {
  return (
    <nav aria-label="Shell demos" className="d-row">
      {SCREENS.map(([id, label]) => (
        <a key={id} href={`#/shell/${id}`} className="d-chip" aria-current={current === id || (id === 'onboarding-1' && current.startsWith('onboarding')) ? 'page' : undefined}>
          {label}
        </a>
      ))}
    </nav>
  );
}

function PaletteDemo({ query }: { query: string }) {
  const toast = useToast();
  const [open, setOpen] = useState(true);
  const [recent, setRecent] = useState(initialRecent);
  const commands = useMemo(() => buildPaletteCommands({ now: NOW, apps: paletteApps, nodes, pending, canApprove: true }), []);
  usePaletteHotkey(() => setOpen(true));
  const run = (c: PaletteCommand) => {
    setRecent((r) => pushRecentCommand(r, c.id));
    if (c.request) toast.show(toastForRequest(c.title.replace(/^Request /, ''), `demo-${c.id}`, go));
    else if (c.href) go(c.href);
  };
  return (
    <>
      <PageHeader
        title="Command palette"
        lede="Press Cmd K or Ctrl K anywhere. Find apps, nodes, settings and approvals, or type > to make a request. Every row shows the API or CLI call that does the same."
        actions={<PaletteTrigger onOpen={() => setOpen(true)} />}
      />
      <ShellNav current={query ? 'palette-search' : 'palette'} />
      <Card title="Keyboard" level={2}>
        <dl className="d-kv">
          <dt>Cmd K / Ctrl K</dt>
          <dd>Open from any screen</dd>
          <dt>↑ ↓, Ctrl Home / End</dt>
          <dd>Move through results</dd>
          <dt>Enter</dt>
          <dd>Open, or create the request (it waits in Approvals)</dd>
          <dt>&gt; @ #</dt>
          <dd>Only requests, only nodes, apps in a category</dd>
          <dt>Esc</dt>
          <dd>Clear the search, then close</dd>
        </dl>
      </Card>
      <CommandPalette open={open} onClose={() => setOpen(false)} commands={commands} onRun={run} recent={recent} initialQuery={query} />
    </>
  );
}

function NotificationsDemo() {
  const [items, setItems] = useState<ShellNotification[]>(notifications);
  const centre = {
    items,
    now: NOW,
    onSetRead: (ids: string[], read: boolean) => setItems((x) => setNotificationsRead(x, ids, read)),
    onReadAll: () => setItems(markAllNotificationsRead),
  };
  return (
    <>
      <div className="d-shell-bar">
        <PageHeader title="Notifications" lede="The bell lives in the top bar. Approvals waiting, failed backups, offline nodes, updates and rollbacks; each opens where it happened." />
        <NotificationBell {...centre} defaultOpen />
      </div>
      <ShellNav current="notifications" />
      <div className="d-grid">
        <Card title="Stale: hub not answering" level={2} subtitle="The list stays, labelled with its age; read state cannot change until the hub answers.">
          <div className="d-shell-frame">
            <NotificationCentre {...centre} items={notifications.slice(0, 2)} state="stale" ageSeconds={240} onRetry={() => {}} />
          </div>
        </Card>
        <Card title="Nothing needs you" level={2} subtitle="Filter with nothing in it: the empty state says why.">
          <div className="d-shell-frame">
            <NotificationCentre {...centre} items={notifications.filter((n) => n.read)} initialFilter="needs-you" />
          </div>
        </Card>
      </div>
    </>
  );
}

function ToastsDemo() {
  const toast = useToast();
  const fired = useRef(false);
  // The library keeps 4 toasts at most: the request confirmation plus three notifications.
  const kinds: ShellNotification[] = [notifications[3]!, notifications[2]!, notifications[1]!];
  useEffect(() => {
    if (fired.current) return;
    fired.current = true;
    toast.show(toastForRequest('Install Node-RED', 'a-7f31', go));
    for (const n of kinds) toast.show(toastForNotification(n, go));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return (
    <>
      <PageHeader title="Toasts" lede="Confirm what just happened and link to where it lives. Errors stay until closed; the rest leave after 6 s, paused while hovered or focused. The notification centre keeps the copy." />
      <ShellNav current="toasts" />
      <Card title="Show a toast" level={2}>
        <div className="d-row">
          <button type="button" className="om-btn om-btn-secondary" onClick={() => toast.show(toastForRequest('Install Immich', 'a-demo', go))}>
            Request sent
          </button>
          {notifications.slice(1, 5).map((n) => (
            <button key={n.id} type="button" className="om-btn om-btn-secondary" onClick={() => toast.show(toastForNotification(n, go))}>
              {n.kind.replace(/_/g, ' ')}
            </button>
          ))}
        </div>
      </Card>
    </>
  );
}

function StatesDemo() {
  return (
    <>
      <PageHeader title="States" lede="One component decides loading, empty, error, stale, offline and forbidden for every panel, with the same words and the same look." />
      <ShellNav current="states" />
      <div className="d-grid">
        <Card title="Loading" level={2} subtitle="Layout-shaped skeleton; after 10 s it says what is slow.">
          <StateView state="loading" what="Loading apps" skeleton="list" />
        </Card>
        <Card title="Loading, slow" level={2}>
          <StateView state="loading" what="Loading backups" slow compact />
        </Card>
        <Card title="Empty" level={2}>
          <StateView state="empty" empty="approvals" />
        </Card>
        <Card title="Empty, with an action" level={2}>
          <StateView state="empty" empty="nodes" action={<button type="button" className="om-btn om-btn-primary om-btn-sm">Add a node</button>} />
        </Card>
        <Card title="Error" level={2} subtitle="The contract error code and the hub's message.">
          <StateView state="error" error={{ error: 'conflict', message: 'An install of immich is already running (action a-7f40).' }} onRetry={() => {}} />
        </Card>
        <Card title="Forbidden" level={2}>
          <StateView state="forbidden" forbiddenReason="Only the owner can see backup keys. Ask the owner to share a restore link." />
        </Card>
        <Card title="Stale" level={2} variant="stale">
          <StateView state="stale" ageSeconds={95} onRetry={() => {}}>
            <ul className="d-list">
              <li>home-hub · 5 apps · 9.2 GB free</li>
              <li>pi-garage · 2 apps · 5.8 GB free</li>
            </ul>
          </StateView>
        </Card>
        <Card title="Offline" level={2} variant="stale">
          <StateView state="offline" ageSeconds={3 * 3600 + 600}>
            <ul className="d-list">
              <li>cloud-relay · 0 apps · 1.1 GB free</li>
            </ul>
          </StateView>
        </Card>
      </div>
    </>
  );
}

const TZ = ['UTC', 'Europe/London', 'Europe/Berlin', 'America/New_York', 'Asia/Tokyo'];
const DRAFTS: Array<Partial<OnboardingDraft>> = [
  { boxName: 'home-hub', timeZone: 'Europe/London' },
  { boxName: 'home-hub', timeZone: 'Europe/London', ownerName: 'Dana' },
  { boxName: 'home-hub', timeZone: 'Europe/London', ownerName: 'Dana', passkey: 'registered', accent: 'lagoon' },
  { boxName: 'home-hub', timeZone: 'Europe/London', ownerName: 'Dana', passkey: 'registered', accent: 'lagoon', starterApps: ['home-assistant', 'vaultwarden', 'hermes-agent'] },
  { boxName: 'home-hub', timeZone: 'Europe/London', ownerName: 'Dana', passkey: 'registered', accent: 'lagoon', starterApps: ['home-assistant', 'vaultwarden', 'hermes-agent'] },
  { boxName: 'home-hub', timeZone: 'Europe/London', ownerName: 'Dana', passkey: 'registered', accent: 'lagoon', starterApps: ['home-assistant', 'vaultwarden', 'hermes-agent'], backup: { destination: 'usb', kitSaved: true } },
];

function OnboardingDemo({ step }: { step: number }) {
  const i = Math.min(Math.max(step, 1), 6) - 1;
  return (
    <Onboarding
        key={i}
        apps={starterApps}
        initial={DRAFTS[i]}
        initialStep={i}
        timeZones={TZ}
        hub={hub}
        onThemeChange={() => {}}
        onRestore={() => go('#/backups')}
        onFinish={() => go('#/home')}
      />
  );
}

export function ShellScreens({ arg = 'palette' }: { arg?: string }) {
  if (arg.startsWith('onboarding')) return <OnboardingDemo step={Number(arg.split('-')[1] ?? 1)} />;
  switch (arg) {
    case 'palette-search':
      return <PaletteDemo query="ho" />;
    case 'notifications':
      return <NotificationsDemo />;
    case 'toasts':
      return <ToastsDemo />;
    case 'states':
      return <StatesDemo />;
    default:
      return <PaletteDemo query="" />;
  }
}
