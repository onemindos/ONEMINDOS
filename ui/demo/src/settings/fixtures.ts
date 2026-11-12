// SPDX-License-Identifier: Apache-2.0
// Typed fixtures for the Settings, Activity and Approvals demo. Shapes are the ones in
// ui/src/settings/types.ts (contract §3 plus PROPOSED endpoints). All names are invented,
// no addresses or real hosts; the clock is the demo's frozen NOW.
import type {
  AboutData,
  AccountData,
  ActionPlan,
  ActivityData,
  AgentsData,
  AutomationRule,
  BackupsData,
  DevicesData,
  NetworkData,
  NotificationsData,
  SettingsPerson,
  StorageData,
  UpdatesData,
} from '../../../src';
import { NOW, ago, later, pending } from '../fixtures';

const H = 3600;
const D = 86_400;

/**
 * A 25 × 25 pattern with QR finder squares, for the demo only. It is NOT an encoded QR code:
 * the gateway returns the real module matrix for a join code (FABRIC), the UI only draws it.
 */
function demoQr(seed: string): number[][] {
  const n = 25;
  let h = 2166136261;
  for (const c of seed) h = Math.imul(h ^ c.charCodeAt(0), 16777619);
  const finder = (x: number, y: number) => {
    for (const [ox, oy] of [[0, 0], [n - 7, 0], [0, n - 7]] as const) {
      const fx = x - ox;
      const fy = y - oy;
      if (fx >= -1 && fx <= 7 && fy >= -1 && fy <= 7) {
        if (fx < 0 || fy < 0 || fx > 6 || fy > 6) return 0;
        const edge = fx === 0 || fy === 0 || fx === 6 || fy === 6;
        const core = fx >= 2 && fx <= 4 && fy >= 2 && fy <= 4;
        return edge || core ? 1 : 0;
      }
    }
    return -1;
  };
  return Array.from({ length: n }, (_, y) =>
    Array.from({ length: n }, (_, x) => {
      const f = finder(x, y);
      if (f >= 0) return f;
      if (y === 6 || x === 6) return (x + y) % 2 === 0 ? 1 : 0;
      h = Math.imul(h ^ (x * 31 + y), 2654435761) >>> 0;
      return (h >>> 13) & 1;
    }),
  );
}

export const account: AccountData = {
  person: { id: 'person:owner', name: 'Owner', role: 'owner' },
  passkeysAvailable: true,
  passkeys: [
    { id: 'pk-1', name: 'Phone (Face ID)', created_at: ago(30 * D), last_used_at: ago(5 * 60) },
    { id: 'pk-2', name: 'Laptop (Touch ID)', created_at: ago(28 * D), last_used_at: ago(2 * D) },
  ],
  totp: false,
  requirePasskeyApproval: true,
  sessions: [
    { id: 'ses-a1', device: 'Firefox on laptop', client: 'browser', created_at: ago(3 * D), last_seen_at: ago(20), current: true, approval: 'passkey' },
    { id: 'ses-b7', device: 'OneMind app on phone', client: 'phone', created_at: ago(12 * D), last_seen_at: ago(5 * 60), approval: 'passkey' },
    { id: 'ses-c3', device: 'onemind CLI', client: 'cli', created_at: ago(7 * D), last_seen_at: ago(H), approval: 'token' },
  ],
  tokens: [
    { id: 'tok_5d1e', name: 'hermes-agent', principal: 'agent:hermes-agent', kind: 'agt', created_at: ago(5 * D), expires_at: later(25 * D), last_used_at: ago(6 * 60), revoked_at: null },
    { id: 'tok_91ac', name: 'backup script', principal: 'person:owner', kind: 'pat', created_at: ago(26 * D), expires_at: later(4 * D), last_used_at: ago(41 * 60), revoked_at: null },
    { id: 'tok_77f0', name: 'old laptop', principal: 'person:owner', kind: 'pat', created_at: ago(60 * D), expires_at: ago(10 * D), last_used_at: ago(20 * D), revoked_at: null },
  ],
};

export const people: SettingsPerson[] = [
  { id: 'person:owner', name: 'Owner', role: 'owner', signIn: 'passkey', last_seen_at: ago(5 * 60) },
  { id: 'person:alex', name: 'Alex', role: 'adult', signIn: 'passkey', last_seen_at: ago(2 * D) },
  { id: 'person:sam', name: 'Sam', role: 'adult', signIn: 'invited', last_seen_at: null },
  { id: 'person:guest-tv', name: 'Living-room TV', role: 'guest', signIn: 'totp', last_seen_at: ago(6 * H) },
];

export const devices: DevicesData = {
  nodes: [
    { node_id: '3f9c2a1b7d4e', hostname: 'home-hub', role: 'hub', arch: 'amd64', board: 'x86_64-efi', status: 'online', last_seen: ago(4), apps: 5 },
    { node_id: 'a1d07c55e912', hostname: 'pi-garage', role: 'worker', arch: 'arm64', board: 'rpi5', status: 'online', last_seen: ago(9), apps: 2 },
    { node_id: '77b2e0c4a5f1', hostname: 'office-laptop', role: 'worker', arch: 'amd64', board: 'x86_64-efi', status: 'stale', last_seen: ago(75), apps: 0 },
    { node_id: 'c0ffee12ab34', hostname: 'field-radio', role: 'leaf', arch: 'arm64', board: 'rpi-zero2', status: 'offline', last_seen: ago(3 * H), apps: 0 },
  ],
  join: { code: 'KTRV-9QXH', expires_at: later(9 * 60), qr: demoQr('KTRV-9QXH'), role: 'worker' },
};

export const network: NetworkData = {
  mesh: { state: 'degraded', peers: 3, peersOnline: 2, transport: 'WireGuard' },
  remote: {
    enabled: true,
    exposed: [
      { app_id: 'home-assistant', name: 'Home Assistant', tier: 'mesh' },
      { app_id: 'immich', name: 'Immich', tier: 'lan' },
    ],
  },
  lanNames: [
    { name: 'home-hub.local', target: 'The OneMind dashboard', kind: 'mdns' },
    { name: 'home-assistant.home-hub.local', target: 'Home Assistant, behind the gateway login', kind: 'mdns' },
    { name: 'photos.home-hub.local', target: 'Immich, behind the gateway login', kind: 'mdns' },
  ],
  certificates: [
    { id: 'ca', name: 'Box certificate authority', issuer: 'box-ca', expires_at: later(3 * 365 * D), covers: 'every name on this box' },
    { id: 'gw', name: 'Gateway certificate', issuer: 'box-ca', expires_at: later(11 * D), covers: '*.home-hub.local' },
  ],
};

export const backups: BackupsData = {
  destinations: [
    { id: 'usb', name: 'USB disk on home-hub', kind: 'usb', last_success_at: ago(41 * 60), state: 'current', used_gb: 84 },
    { id: 'peer', name: 'pi-garage', kind: 'box', last_success_at: ago(41 * 60), state: 'current', used_gb: 84 },
    { id: 's3', name: 'Offsite bucket', kind: 's3', last_success_at: ago(26 * H), state: 'behind', used_gb: 79 },
  ],
  schedule: { every: 'daily', at: '02:30', keep: '7 daily, 4 weekly and 12 monthly copies' },
  lastVerifiedRestore: { at: ago(D + 2 * H), snapshot: '0e7713cd', scope: 'ntfy and Home Assistant', result: 'ok' },
  snapshots: [
    { id: 'c81d02e4', at: ago(41 * 60), size_gb: 0.4, verified: 'untested' },
    { id: '0e7713cd', at: ago(D + 3 * H), size_gb: 1.1, verified: 'ok' },
    { id: 'f2a9be40', at: ago(8 * D), size_gb: 2.4, verified: 'ok' },
  ],
  emergencyKit: { saved: true, keys: 2, of: 3 },
};

export const updatesData: UpdatesData = {
  version: '0.3.1',
  slot: 'A',
  fallback: { slot: 'B', version: '0.3.0' },
  channel: 'security',
  window: { start: '03:00', end: '04:00' },
  available: {
    version: '0.3.2',
    channel: 'Security',
    notes: ['Fixes two openssl vulnerabilities (one high).', 'Linux kernel 6.12.58 with a fix for USB radios dropping after suspend.', 'The gateway refuses approvals older than their plan.'],
    cvesFixed: 2,
    size_mb: 412,
  },
  history: [
    { at: ago(9 * D), from: '0.3.0', to: '0.3.1', result: 'kept', by: 'person:owner' },
    { at: ago(12 * D), from: '0.2.9', to: '0.3.0', result: 'rolled-back', check: 'k3s not ready within 5 min on pi-garage', by: 'person:owner' },
    { at: ago(20 * D), from: '0.2.8', to: '0.2.9', result: 'kept', by: 'person:owner' },
  ],
  apps: [
    { app_id: 'home-assistant', name: 'Home Assistant', from: '2026.11.1', to: '2026.11.2', category: 'home', deploy_class: 'market-verified', notes: ['Fixes Zigbee pairing timeouts'] },
    { app_id: 'immich', name: 'Immich', from: '2.3.0', to: '2.3.1', category: 'files', deploy_class: 'market-verified', notes: ['Faster face grouping', 'Security fix in the share links'] },
    { app_id: 'searxng', name: 'SearXNG', from: '2026.10.30', to: '2026.11.10', category: 'news', deploy_class: 'market-community', notes: ['Not fully checked: upstream publishes no releases'] },
    { app_id: 'garage-flows', name: 'garage-flows', from: 'a41c9e0', to: '7d02b15', category: 'automation', deploy_class: 'private', notes: ['Your own deployment; new commit on main'] },
  ],
};

export const notifications: NotificationsData = {
  channels: [
    { id: 'in-app', kind: 'in-app', label: 'In the app', state: 'ok', last_delivery_at: ago(6 * 60), minSeverity: 'info' },
    { id: 'phone', kind: 'push-android', label: 'Phone push (via ntfy on this box)', state: 'ok', last_delivery_at: ago(6 * 60), minSeverity: 'warning' },
    { id: 'matrix', kind: 'matrix', label: 'Matrix room', state: 'failing', last_delivery_at: ago(2 * D), minSeverity: 'critical' },
  ],
  quiet: { enabled: true, start: '22:00', end: '07:00', allowCritical: true },
};

export const automations: AutomationRule[] = [
  { id: 'r-1', name: 'Weekly restore drill', trigger: { kind: 'schedule', detail: 'Sundays 04:30' }, creates: 'backup.verify', policy: 'standing', last_run_at: ago(4 * D), next_run_at: later(3 * D - 10 * H), state: 'on' },
  { id: 'r-2', name: 'Garage lights at dusk', trigger: { kind: 'event', detail: 'evt.home.sun.set' }, creates: 'app.call home-assistant', policy: 'ask', last_run_at: ago(22 * H), next_run_at: null, state: 'on' },
  { id: 'r-3', name: 'Restart a stuck camera', trigger: { kind: 'webhook', detail: 'from Uptime Kuma' }, creates: 'app.restart frigate', policy: 'ask', last_run_at: null, next_run_at: null, state: 'paused' },
];

export const agents: AgentsData = {
  mcp: { enabled: true, path: '/mcp' },
  agents: [
    {
      id: 'agent:hermes-agent',
      name: 'Hermes agent',
      state: 'active',
      tools: [
        { name: 'list_nodes', kind: 'read' },
        { name: 'list_apps', kind: 'read' },
        { name: 'read_logs', kind: 'read' },
        { name: 'request_install', kind: 'request' },
        { name: 'request_restart', kind: 'request' },
      ],
      tokens: 1,
      last_active_at: ago(6 * 60),
      week: { asked: 6, approved: 4, denied: 1 },
      pending: 1,
    },
    {
      id: 'agent:kitchen-assistant',
      name: 'Kitchen assistant',
      state: 'suspended',
      tools: [
        { name: 'list_apps', kind: 'read' },
        { name: 'request_app_call', kind: 'request' },
      ],
      tokens: 0,
      last_active_at: ago(9 * D),
      week: { asked: 0, approved: 0, denied: 0 },
      pending: 0,
    },
  ],
};

export const storage: StorageData = {
  disks: [
    { id: 'd1', node: 'home-hub', label: 'System and apps', kind: 'nvme', role: 'data', total_gb: 477, used_gb: 125, health: 'ok', encrypted: true },
    { id: 'd2', node: 'home-hub', label: 'Backup disk', kind: 'usb', role: 'backup', total_gb: 1000, used_gb: 84, health: 'ok', encrypted: true },
    { id: 'd3', node: 'pi-garage', label: 'SD card', kind: 'ssd', role: 'system', total_gb: 119, used_gb: 101, health: 'warn', encrypted: false },
  ],
  apps: [
    { app_id: 'immich', name: 'Immich', category: 'files', deploy_class: 'market-verified', used_gb: 61.2 },
    { app_id: 'home-assistant', name: 'Home Assistant', category: 'home', deploy_class: 'market-verified', used_gb: 6.4 },
    { app_id: 'frigate', name: 'Frigate', category: 'home', deploy_class: 'market-verified', used_gb: 22.8 },
    { app_id: 'hermes-agent', name: 'Hermes agent', category: 'ai', deploy_class: 'market-verified', used_gb: 9.1 },
    { app_id: 'uptime-kuma', name: 'Uptime Kuma', category: 'monitoring', deploy_class: 'market-verified', used_gb: 0.3 },
    { app_id: 'searxng', name: 'SearXNG', category: 'news', deploy_class: 'market-community', used_gb: 0.1 },
    { app_id: 'garage-flows', name: 'garage-flows', category: 'automation', deploy_class: 'private', used_gb: 0.2 },
  ],
};

export const about: AboutData = {
  box: 'home-hub',
  version: '0.3.1',
  build: 'onemind-os 0.3.1 · debian 13 · rauc bundle 2026.10.31',
  base: 'Debian 13',
  uptime_s: 9 * D + 4 * H + 1260,
  components: [
    { name: 'Gateway', version: '0.3.1', state: 'ok' },
    { name: 'onemindd (node agent)', version: '0.3.1', state: 'ok' },
    { name: 'Message bus (NATS)', version: '2.12.1', state: 'ok' },
    { name: 'k3s', version: '1.34.2', state: 'ok' },
    { name: 'Backup agent (restic)', version: '0.18.1', state: 'warn' },
    { name: 'Updater (RAUC)', version: '1.15', state: 'ok' },
  ],
  lastBundle_at: null,
};

export const activityData: ActivityData = {
  verify: { state: 'verified', first: 1, last: 1289, checked_at: ago(2 * 60), checkpoint: { seq: 1280, at: ago(H), storedOff: 'your phone' } },
  entries: [
    { seq: 1289, at: ago(4 * 60), actor: { id: 'person:owner', kind: 'person' }, kind: 'sign-in', text: 'signed in with a passkey (Firefox on laptop)', hash: '9f2c1a', result: 'ok', resultLabel: 'Passkey' },
    { seq: 1288, at: ago(6 * 60), actor: { id: 'agent:hermes-agent', kind: 'agent' }, kind: 'request', text: 'requested Install node-red: “You asked me to automate the garage lights.”', app: 'node-red', hash: '41be07', result: 'warn', resultLabel: 'Waiting' },
    { seq: 1287, at: ago(41 * 60), actor: { id: 'system:backup', kind: 'system' }, kind: 'result', text: 'backed up 6 volumes to the USB disk (412 MB new)', node: 'home-hub', hash: 'c0d3e1', result: 'ok', resultLabel: 'Done' },
    { seq: 1286, at: ago(2 * H), actor: { id: 'system:updates', kind: 'system' }, kind: 'request', text: 'requested Update home-assistant 2026.11.1 → 2026.11.2', app: 'home-assistant', hash: '77a0b9', result: 'warn', resultLabel: 'Waiting' },
    { seq: 1285, at: ago(3 * H + 600), actor: { id: 'system:fabric', kind: 'system' }, kind: 'result', text: 'field-radio stopped reporting', node: 'field-radio', hash: '1e9d44', result: 'bad', resultLabel: 'Offline' },
    { seq: 1284, at: ago(4 * H), actor: { id: 'person:owner', kind: 'person' }, kind: 'config', text: 'suspended agent:kitchen-assistant (instant; cancelled 0 requests)', hash: '5a6b2f', result: 'info', resultLabel: 'Suspended' },
    { seq: 1283, at: ago(D + 2 * H), actor: { id: 'system:backup', kind: 'system' }, kind: 'result', text: 'restore drill: restored ntfy and Home Assistant to scratch, every probe passed', hash: 'b81c30', result: 'ok', resultLabel: 'Verified' },
    { seq: 1282, at: ago(D + 5 * H), actor: { id: 'system:audit', kind: 'system' }, kind: 'checkpoint', text: 'signed checkpoint #1280 and sent it to your phone', hash: 'e44f10', result: 'ok', resultLabel: 'Signed' },
    { seq: 1281, at: ago(2 * D), actor: { id: 'person:owner', kind: 'person' }, kind: 'decision', text: 'approved Install ntfy (asked by agent:hermes-agent) with a passkey', app: 'ntfy', hash: '03fa9d', result: 'ok', resultLabel: 'Done' },
    { seq: 1280, at: ago(2 * D + 60), actor: { id: 'agent:hermes-agent', kind: 'agent' }, kind: 'request', text: 'requested Install ntfy', app: 'ntfy', hash: '6c2e81', result: 'info', resultLabel: 'Approved' },
    { seq: 1279, at: ago(3 * D), actor: { id: 'person:owner', kind: 'person' }, kind: 'decision', text: 'denied Install immich (asked by person:alex)', app: 'immich', hash: 'aa1907', result: 'info', resultLabel: 'Denied' },
  ],
};

/** Gateway-computed plans for the waiting requests in ../fixtures (pending). */
export const plans: Record<string, ActionPlan> = {
  [pending[0]!.id]: {
    action_id: pending[0]!.id,
    plan_hash: 'sha256:4be1…9c07',
    computed_at: ago(6 * 60),
    app: { id: 'node-red', name: 'Node-RED', category: 'automation', deploy_class: 'market-verified', plugin: false },
    placement: { node: 'home-hub', fits: true, reason: '256 MB needed, 9.2 GB free; amd64 image published.' },
    effects: [
      { kind: 'image', label: 'nodered/node-red 4.1.2', detail: 'digest sha256:0c1f…e2, about 180 MB', risk: 'low' },
      { kind: 'volume', label: 'One data volume, 1 GB', detail: 'backed up nightly', risk: 'low' },
      { kind: 'port', label: 'Home network only, behind the gateway login', detail: 'no host ports', risk: 'low' },
      { kind: 'egress', label: 'Talks to the npm registry when you add nodes', detail: 'registry.npmjs.org', risk: 'medium' },
    ],
    scan: { at: ago(9 * H), critical: 0, high: 0, malware: 'clean' },
    undo: 'reversible',
  },
  [pending[1]!.id]: {
    action_id: pending[1]!.id,
    plan_hash: 'sha256:aa70…13de',
    computed_at: ago(2 * H),
    app: { id: 'home-assistant', name: 'Home Assistant', category: 'home', deploy_class: 'market-verified', plugin: false },
    placement: { node: 'home-hub', fits: true, reason: 'Stays where it runs.' },
    effects: [
      { kind: 'image', label: 'home-assistant 2026.11.2', detail: 'digest sha256:51ab…7f, 38 MB changed', risk: 'low' },
      { kind: 'device', label: 'Keeps access to the Zigbee USB radio', risk: 'medium' },
      { kind: 'host-network', label: 'Keeps using the node’s network directly', detail: 'for device discovery', risk: 'medium' },
      { kind: 'restart', label: 'Home Assistant restarts', detail: 'about 1 minute', risk: 'low' },
    ],
    scan: { at: ago(3 * H), critical: 0, high: 0, malware: 'clean' },
    undo: 'snapshot',
  },
  [pending[2]!.id]: {
    action_id: pending[2]!.id,
    plan_hash: 'sha256:0d3c…b8a2',
    computed_at: ago(9 * H),
    placement: { node: 'home-hub', fits: true, reason: 'Installs into slot B; slot A stays as the fallback.' },
    effects: [
      { kind: 'image', label: 'OneMind OS 0.3.2 bundle', detail: 'signed, 412 MB', risk: 'low' },
      { kind: 'restart', label: 'home-hub reboots in the window (03:00–04:00)', detail: 'apps unavailable about 3 minutes', risk: 'medium' },
    ],
    undo: 'snapshot',
  },
};

/** An agent asking for something with real reach, to show a high-impact plan. */
export const riskyAction = {
  id: 'a-7f40',
  type: 'exposure.enable',
  params: { app_id: 'home-assistant', tier: 'public' },
  state: 'awaiting_approval' as const,
  created_at: ago(20 * 60),
  expires_at: later(2 * H),
  requested_by: { id: 'agent:hermes-agent', kind: 'agent' as const, role: 'agent' as const },
  reason: 'You asked to check the house from work without the VPN.',
  impact: 'Home Assistant becomes reachable from the whole internet.',
};
export const riskyPlan: ActionPlan = {
  action_id: riskyAction.id,
  plan_hash: 'sha256:f1e0…77c4',
  computed_at: ago(20 * 60),
  app: { id: 'home-assistant', name: 'Home Assistant', category: 'home', deploy_class: 'market-verified', plugin: false },
  effects: [
    { kind: 'exposure', label: 'Anyone on the internet can reach its login page', detail: 'through the relay, HTTPS', risk: 'high' },
    { kind: 'egress', label: 'Keeps an outbound tunnel open to the relay', risk: 'medium' },
    { kind: 'agent-scope', label: 'None: agents gain nothing from this', risk: 'low' },
  ],
  undo: 'reversible',
};

export { NOW, ago };
