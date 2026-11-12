// SPDX-License-Identifier: Apache-2.0
// Demo of the Settings sections, the Activity timeline and the redesigned Approvals board.
// Routes: #/system/<section>, #/system/activity, #/system/approvals. `?state=` (or the demo
// chips) shows each screen loading, failing, stale or empty, so every state can be reviewed.
import { useState } from 'react';
import {
  AboutSection,
  AccountSection,
  AgentsSection,
  ApprovalsBoard,
  AuditTimeline,
  AutomationSection,
  BackupsSection,
  DevicesSection,
  NetworkSection,
  NotificationsSection,
  SETTINGS_SECTIONS,
  SettingsLayout,
  StorageSection,
  UpdatesSection,
  UsersSection,
  restoreBadge,
  useToast,
  type ActionSummary,
  type SettingsIntent,
  type SettingsLoadable,
  type SettingsSectionId,
} from '../../../src';
import { decided, pending } from '../fixtures';
import * as fx from './fixtures';

type DemoState = 'ready' | 'loading' | 'error' | 'stale' | 'empty';
const STATES: DemoState[] = ['ready', 'loading', 'error', 'stale', 'empty'];

function initialState(): DemoState {
  const s = new URLSearchParams(window.location.search).get('state');
  return STATES.includes(s as DemoState) ? (s as DemoState) : 'ready';
}

function load<T>(state: DemoState, data: T, empty: T): SettingsLoadable<T> {
  switch (state) {
    case 'loading':
      return { status: 'loading' };
    case 'error':
      return { status: 'error', error: { error: 'unavailable', message: 'gateway did not answer within 10 s' } };
    case 'stale':
      return { status: 'ready', data, asOf: fx.ago(7 * 60), stale: true };
    case 'empty':
      return { status: 'ready', data: empty, asOf: fx.ago(3) };
    default:
      return { status: 'ready', data, asOf: fx.ago(3) };
  }
}

const EMPTY = {
  account: { ...fx.account, passkeys: [], sessions: [], tokens: [] },
  devices: { nodes: [], join: null },
  network: { ...fx.network, remote: { enabled: false, exposed: [] }, lanNames: [], mesh: { ...fx.network.mesh, state: 'off' as const, peers: 0, peersOnline: 0 } },
  backups: { ...fx.backups, destinations: [], snapshots: [], lastVerifiedRestore: null, emergencyKit: { saved: false, keys: 0, of: 3 } },
  updates: { ...fx.updatesData, available: null, apps: [], history: [] },
  notifications: { ...fx.notifications, channels: [] },
  agents: { ...fx.agents, agents: [] },
  storage: { disks: [], apps: [] },
};

const SECTION_IDS = new Set(SETTINGS_SECTIONS.map((s) => s.id));

export function SystemDemo({ arg }: { arg?: string }) {
  const toast = useToast();
  const [state, setState] = useState<DemoState>(initialState);
  const [waiting, setWaiting] = useState<ActionSummary[]>(() => [fx.riskyAction, ...pending]);
  const [done, setDone] = useState<ActionSummary[]>(decided);
  const now = fx.NOW;
  const onIntent = (i: SettingsIntent) =>
    toast.show(
      i.mode === 'request'
        ? { tone: 'info', title: `Requested: ${i.title}`, body: `Waiting in Approvals. Same call: ${i.call}` }
        : { tone: 'ok', title: i.title, body: `Done at once. Same call: ${i.call}` },
    );
  const onRetry = () => setState('ready');
  const decide = (a: ActionSummary, d: 'approve' | 'deny') => {
    setWaiting((xs) => xs.filter((x) => x.id !== a.id));
    setDone((xs) => [{ ...a, state: d === 'approve' ? 'dispatched' : 'cancelled', decided_by: { id: 'person:owner', kind: 'person' } }, ...xs]);
    toast.show({ tone: d === 'approve' ? 'ok' : 'neutral', title: d === 'approve' ? 'Approved with your passkey' : 'Denied', body: d === 'approve' ? 'Running now. Follow it in Activity.' : undefined });
  };

  const chips = (
    <div className="om-set-chips om-set-demo-states" role="group" aria-label="Demo: show this screen as">
      <span className="d-demo-flag">Demo state</span>
      {STATES.map((s) => (
        <button key={s} type="button" className="om-set-chip" aria-pressed={state === s} onClick={() => setState(s)}>
          {s[0]!.toUpperCase() + s.slice(1)}
        </button>
      ))}
    </div>
  );

  if (arg === 'activity')
    return (
      <>
        {chips}
        <AuditTimeline
          data={load(state, fx.activityData, { ...fx.activityData, entries: [] })}
          now={now}
          onRetry={onRetry}
          onVerify={() => toast.show({ tone: 'ok', title: 'Chain verified', body: 'Entries #1 to #1,289. Same call: onemind audit verify' })}
        />
      </>
    );

  if (arg === 'approvals') {
    const actions = load(state, waiting, []);
    const plans = Object.fromEntries(
      [[fx.riskyAction.id, fx.riskyPlan] as const, ...Object.entries(fx.plans)].map(([id, p]) => [id, state === 'stale' ? { status: 'ready' as const, data: p, asOf: fx.ago(7 * 60), stale: true } : { status: 'ready' as const, data: p, asOf: fx.ago(3) }]),
    );
    return (
      <>
        {chips}
        <ApprovalsBoard actions={actions} plans={plans} decided={done.slice(0, 5)} now={now} canDecide={{ allowed: true }} onApprove={(a) => decide(a, 'approve')} onDeny={(a) => decide(a, 'deny')} onRetry={onRetry} />
      </>
    );
  }

  const explicit = !!arg && SECTION_IDS.has(arg as SettingsSectionId);
  const current = (explicit ? arg : 'account') as SettingsSectionId;
  const rb = restoreBadge(fx.backups.lastVerifiedRestore, now);
  const p = { now, onIntent, onRetry };
  const body = (() => {
    switch (current) {
      case 'users':
        return <UsersSection data={load(state, fx.people, [])} {...p} />;
      case 'devices':
        return <DevicesSection data={load(state, fx.devices, EMPTY.devices)} {...p} />;
      case 'network':
        return <NetworkSection data={load(state, fx.network, EMPTY.network)} {...p} />;
      case 'backups':
        return <BackupsSection data={load(state, fx.backups, EMPTY.backups)} {...p} />;
      case 'updates':
        return <UpdatesSection data={load(state, fx.updatesData, EMPTY.updates)} {...p} />;
      case 'notifications':
        return <NotificationsSection data={load(state, fx.notifications, EMPTY.notifications)} {...p} />;
      case 'automation':
        return <AutomationSection data={load(state, fx.automations, [])} {...p} />;
      case 'agents':
        return <AgentsSection data={load(state, fx.agents, EMPTY.agents)} approvalsHref="#/system/approvals" {...p} />;
      case 'storage':
        return <StorageSection data={load(state, fx.storage, EMPTY.storage)} {...p} />;
      case 'about':
        return <AboutSection data={load(state, fx.about, fx.about)} {...p} />;
      default:
        return <AccountSection data={load(state, fx.account, EMPTY.account)} {...p} />;
    }
  })();
  return (
    <>
      {chips}
      <SettingsLayout
        current={current}
        explicit={explicit}
        hrefFor={(id) => `#/system/${id}`}
        indexHref="#/system"
        hints={{
          backups: rb.tone === 'ok' ? undefined : { tone: rb.tone, label: rb.label },
          updates: { tone: 'warn', label: '5 waiting' },
          network: { tone: 'warn', label: 'Degraded' },
          account: { tone: 'warn', label: 'Token expiring' },
        }}
      >
        {body}
      </SettingsLayout>
    </>
  );
}
