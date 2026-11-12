// SPDX-License-Identifier: Apache-2.0
// Demo fixtures. Shapes follow sdk/contracts/poc-v0.md where the contract defines them
// (§2 heartbeat, §3 actions, §4/§9.3/§11.4 catalog); the rest (backups, alerts, updates,
// users) are proposals from docs/design/IA.md and are marked PROPOSED there.
// All names are invented. The clock is frozen so screenshots are reproducible.
import type { ActionSummary, AppTrust, NodeSummary } from '../../src';

export const NOW = Date.parse('2026-11-12T15:00:00Z');
export const ago = (s: number) => new Date(NOW - s * 1000).toISOString();
export const later = (s: number) => new Date(NOW + s * 1000).toISOString();
const H = 3600;
const D = 86_400;

export const BOX = 'home-hub';

export const nodes: NodeSummary[] = [
  {
    node_id: '3f9c2a1b7d4e',
    hostname: 'home-hub',
    role: 'hub',
    board: 'x86_64-efi',
    arch: 'amd64',
    os: { pretty: 'OneMind OS 0.3 (Debian 13)' },
    cpus: 8,
    mem_total_mb: 16_384,
    mem_available_mb: 9_420,
    disk_total_gb: 477,
    disk_free_gb: 352,
    k3s: { present: true, ready: true, role: 'server' },
    rauc: { present: true, booted_slot: 'A' },
    last_seen: ago(4),
    status: 'online',
    apps: 5,
  },
  {
    node_id: 'a1d07c55e912',
    hostname: 'pi-garage',
    role: 'node',
    board: 'rpi5',
    arch: 'arm64',
    os: { pretty: 'OneMind OS 0.3 (Debian 13)' },
    cpus: 4,
    mem_total_mb: 8_192,
    mem_available_mb: 5_900,
    disk_total_gb: 119,
    disk_free_gb: 96,
    k3s: { present: true, ready: true, role: 'agent' },
    rauc: { present: true, booted_slot: 'B' },
    last_seen: ago(7),
    status: 'online',
    apps: 2,
  },
  {
    node_id: '77be01c4aa30',
    hostname: 'office-laptop',
    role: 'node',
    board: 'x86_64-efi',
    arch: 'amd64',
    os: { pretty: 'Debian GNU/Linux 13 (trixie)' },
    cpus: 12,
    mem_total_mb: 32_768,
    mem_available_mb: 21_000,
    disk_total_gb: 953,
    disk_free_gb: 610,
    k3s: { present: true, ready: true, role: 'agent' },
    rauc: { present: false, booted_slot: null },
    last_seen: ago(75),
    status: 'stale',
    apps: 0,
  },
  {
    node_id: 'c09e5d2f1b88',
    hostname: 'cloud-relay',
    role: 'node',
    board: 'vm-do',
    arch: 'amd64',
    os: { pretty: 'Debian GNU/Linux 13 (trixie)' },
    cpus: 2,
    mem_total_mb: 2_048,
    mem_available_mb: 1_100,
    disk_total_gb: 50,
    disk_free_gb: 31,
    k3s: { present: true, ready: false, role: 'agent' },
    rauc: { present: false, booted_slot: null },
    last_seen: ago(3 * H + 600),
    status: 'offline',
    apps: 0,
  },
];

export interface DemoApp extends AppTrust {
  description: string;
  category: string;
  installed: boolean;
  status?: 'running' | 'starting' | 'stopped' | 'unhealthy';
  node?: string;
  colour: string;
  updateAvailable?: string;
  why?: string[];
}

const scanOk = (age: number, high = 0) => ({ scanned_at: ago(age), result: 'pass' as const, critical: 0, high, malware: 0, cosign: 'unsigned' as const });

export const apps: DemoApp[] = [
  {
    id: 'home-assistant',
    name: 'Home Assistant',
    version: '2026.11.1',
    description: 'Home automation that puts local control and privacy first.',
    category: 'home',
    license: 'Apache-2.0',
    licenseClass: 'L1',
    tier: 'verified',
    scan: { ...scanOk(1 * D, 3), cosign: 'verified' },
    links: { docs: 'https://www.home-assistant.io/docs/', github: 'https://github.com/home-assistant/core', website: 'https://www.home-assistant.io' },
    archs: ['amd64', 'arm64'],
    requires: { minMemoryMb: 1024 },
    permissions: ['Open a web page on your network', 'Use the host network for device discovery', 'Keep its data in a volume that is backed up'],
    installed: true,
    status: 'running',
    node: 'home-hub',
    colour: 'teal',
    updateAvailable: '2026.11.2',
  },
  {
    id: 'ntfy',
    name: 'ntfy',
    version: '2.37.2',
    description: 'Send push notifications to your phone from any script or app.',
    category: 'notifications',
    license: 'Apache-2.0 OR GPL-2.0',
    licenseClass: 'L1',
    tier: 'verified',
    scan: scanOk(2 * D),
    links: { docs: 'https://docs.ntfy.sh', github: 'https://github.com/binwiederhier/ntfy' },
    archs: ['amd64', 'arm64'],
    requires: { minMemoryMb: 128 },
    permissions: ['Open a web page on your network'],
    installed: true,
    status: 'running',
    node: 'home-hub',
    colour: 'green',
  },
  {
    id: 'uptime-kuma',
    name: 'Uptime Kuma',
    version: '2.5.10',
    description: 'Self-hosted uptime monitoring.',
    category: 'monitoring',
    license: 'MIT',
    licenseClass: 'L1',
    tier: 'verified',
    scan: scanOk(1 * D, 1),
    links: { docs: 'https://github.com/louislam/uptime-kuma/wiki', github: 'https://github.com/louislam/uptime-kuma' },
    archs: ['amd64', 'arm64'],
    requires: { minMemoryMb: 256 },
    permissions: ['Open a web page on your network', 'Make outbound connections to the sites it checks'],
    installed: true,
    status: 'running',
    node: 'pi-garage',
    colour: 'blue',
  },
  {
    id: 'hermes-agent',
    name: 'Hermes agent',
    version: '0.23.0',
    description: 'An AI agent that can read your nodes and apps and ask for changes. It can never approve them.',
    category: 'ai',
    license: 'MIT',
    licenseClass: 'L1',
    tier: 'verified',
    scan: scanOk(3 * D, 4),
    links: { github: 'https://github.com/NousResearch/hermes-agent' },
    archs: ['amd64', 'arm64'],
    requires: { minMemoryMb: 2048 },
    permissions: ['Get an agent identity: may request actions, never approve them', 'Read the list of nodes and apps', 'Call your chosen model provider'],
    installed: true,
    status: 'running',
    node: 'home-hub',
    colour: 'violet',
  },
  {
    id: 'node-red',
    name: 'Node-RED',
    version: '4.1.2',
    description: 'Low-code programming for event-driven flows.',
    category: 'automation',
    license: 'Apache-2.0',
    licenseClass: 'L1',
    tier: 'verified',
    scan: scanOk(1 * D),
    links: { docs: 'https://nodered.org/docs/', github: 'https://github.com/node-red/node-red' },
    archs: ['amd64', 'arm64'],
    requires: { minMemoryMb: 256 },
    permissions: ['Open a web page on your network'],
    installed: false,
    colour: 'red',
  },
  {
    id: 'vaultwarden',
    name: 'Vaultwarden',
    version: '1.35.1',
    description: 'A lightweight password manager server compatible with Bitwarden apps.',
    category: 'security',
    license: 'AGPL-3.0-only',
    licenseClass: 'L2',
    tier: 'verified',
    scan: scanOk(4 * D),
    links: { github: 'https://github.com/dani-garcia/vaultwarden' },
    archs: ['amd64', 'arm64'],
    requires: { minMemoryMb: 128 },
    permissions: ['Open a web page on your network', 'Keep its data in a volume that is backed up'],
    installed: false,
    colour: 'blue',
  },
  {
    id: 'immich',
    name: 'Immich',
    version: '2.3.0',
    description: 'Photo and video backup with search, on your own hardware.',
    category: 'media',
    license: 'AGPL-3.0-only',
    licenseClass: 'L2',
    tier: 'community',
    scan: scanOk(9 * D),
    links: { docs: 'https://immich.app/docs', github: 'https://github.com/immich-app/immich' },
    archs: ['amd64', 'arm64'],
    requires: { minMemoryMb: 6144, gpu: false },
    installed: false,
    colour: 'amber',
    why: ['pi-garage: needs 6 GB free memory, has 5.8 GB', 'office-laptop: stale for 1 min, not used for placement'],
  },
  {
    id: 'cryptominer-demo',
    name: 'Example blocked app',
    version: '0.0.1',
    description: 'Shown so you can see what a blocked Market entry looks like.',
    category: 'other',
    license: 'PolyForm-Noncommercial-1.0.0',
    licenseClass: 'blocked',
    tier: 'blocked',
    scan: { scanned_at: ago(1 * D), result: 'fail', critical: 2, high: 9, malware: 1, cosign: 'unsigned' },
    archs: ['amd64'],
    installed: false,
    colour: 'neutral',
  },
];

export const pending: ActionSummary[] = [
  {
    id: 'a-7f31',
    type: 'app.install',
    params: { app_id: 'node-red' },
    state: 'awaiting_approval',
    created_at: ago(6 * 60),
    expires_at: later(23 * H),
    requested_by: { id: 'agent:hermes-agent', kind: 'agent', role: 'agent' },
    reason: 'You asked me to automate the garage lights. Node-RED can run that flow.',
    impact: 'Downloads about 180 MB and starts one web app on home-hub. Uses about 256 MB of memory.',
  },
  {
    id: 'a-7f2c',
    type: 'app.update',
    params: { app_id: 'home-assistant', from: '2026.11.1', to: '2026.11.2' },
    state: 'awaiting_approval',
    created_at: ago(2 * H),
    expires_at: later(5 * D),
    requested_by: { id: 'system:updates', kind: 'agent', role: 'agent' },
    reason: 'Patch release. Scan passed today. A snapshot is taken first; if the app is unhealthy after 5 minutes it is reverted.',
    impact: 'Home Assistant restarts (about 1 minute).',
  },
  {
    id: 'a-7f12',
    type: 'os.update',
    params: { node_id: 'home-hub', from: '0.3.1', to: '0.3.2', channel: 'security' },
    state: 'awaiting_approval',
    created_at: ago(9 * H),
    expires_at: later(40 * 60),
    requested_by: { id: 'system:updates', kind: 'agent', role: 'agent' },
    reason: 'Security update (openssl, linux). Installs into slot B; the box reboots and keeps B only if every health check passes.',
    impact: 'home-hub reboots in the maintenance window (03:00–04:00). Apps are unavailable for about 3 minutes.',
  },
];

export const decided: ActionSummary[] = [
  { id: 'a-7e90', type: 'app.install', params: { app_id: 'ntfy' }, state: 'succeeded', created_at: ago(2 * D), expires_at: ago(D), requested_by: { id: 'agent:hermes-agent', kind: 'agent' }, decided_by: { id: 'person:owner', kind: 'person' } },
  { id: 'a-7e71', type: 'app.install', params: { app_id: 'immich' }, state: 'cancelled', created_at: ago(3 * D), expires_at: ago(2 * D), requested_by: { id: 'person:alex', kind: 'person' }, decided_by: { id: 'person:owner', kind: 'person' } },
  { id: 'a-7e55', type: 'app.remove', params: { app_id: 'jellyfin' }, state: 'failed', created_at: ago(4 * D), expires_at: ago(3 * D), requested_by: { id: 'person:owner', kind: 'person' }, decided_by: { id: 'person:owner', kind: 'person' }, message: 'namespace app-jellyfin stuck terminating' },
  { id: 'a-7e40', type: 'node.join', params: { node_id: 'pi-garage' }, state: 'succeeded', created_at: ago(6 * D), expires_at: ago(6 * D - H), requested_by: { id: 'person:owner', kind: 'person' }, decided_by: { id: 'person:owner', kind: 'person' } },
];

export type ActorKind = 'person' | 'agent' | 'system';
export interface ActivityEntry {
  at: string;
  actor: string;
  kind: ActorKind;
  text: string;
  result?: 'ok' | 'bad' | 'warn' | 'info';
  resultLabel?: string;
  node?: string;
  app?: string;
  seq: number;
}

export const activity: ActivityEntry[] = [
  { seq: 1284, at: ago(6 * 60), actor: 'agent:hermes-agent', kind: 'agent', text: 'requested Install node-red', result: 'warn', resultLabel: 'Waiting', app: 'node-red' },
  { seq: 1283, at: ago(41 * 60), actor: 'system:backup', kind: 'system', text: 'backed up 6 volumes to usb-backup (412 MB new)', result: 'ok', resultLabel: 'Done' },
  { seq: 1282, at: ago(2 * H), actor: 'system:updates', kind: 'system', text: 'requested Update home-assistant 2026.11.1 → 2026.11.2', result: 'warn', resultLabel: 'Waiting', app: 'home-assistant' },
  { seq: 1281, at: ago(3 * H + 600), actor: 'system:fabric', kind: 'system', text: 'cloud-relay stopped reporting', result: 'bad', resultLabel: 'Offline', node: 'cloud-relay' },
  { seq: 1280, at: ago(9 * H), actor: 'system:updates', kind: 'system', text: 'found OS 0.3.2 on the security channel; requested install', result: 'warn', resultLabel: 'Waiting', node: 'home-hub' },
  { seq: 1279, at: ago(D + 2 * H), actor: 'system:backup', kind: 'system', text: 'weekly restore drill: restored ntfy and home-assistant to scratch, all probes passed', result: 'ok', resultLabel: 'Verified' },
  { seq: 1278, at: ago(2 * D), actor: 'person:owner', kind: 'person', text: 'approved Install ntfy (asked by agent:hermes-agent)', result: 'ok', resultLabel: 'Done', app: 'ntfy' },
  { seq: 1277, at: ago(2 * D + 60), actor: 'agent:hermes-agent', kind: 'agent', text: 'requested Install ntfy', result: 'info', resultLabel: 'Approved', app: 'ntfy' },
  { seq: 1276, at: ago(3 * D), actor: 'person:owner', kind: 'person', text: 'denied Install immich (asked by person:alex)', result: 'info', resultLabel: 'Denied', app: 'immich' },
];

export interface Alert {
  id: string;
  severity: 'critical' | 'warning' | 'info';
  title: string;
  body: string;
  source: string;
  created: string;
  fix?: string;
  acked?: boolean;
  actionId?: string;
}

export const alerts: Alert[] = [
  { id: 'al-1', severity: 'warning', title: 'cloud-relay is offline', body: 'No heartbeat for 3 h. Its apps are not affected because it runs none.', source: 'fabric', created: ago(3 * H + 480), fix: 'Remove the node from the fabric' },
  { id: 'al-2', severity: 'warning', title: 'OS security update waiting for approval', body: 'OS 0.3.2 fixes 2 CVEs. The approval expires in 40 min; after that it waits for the next window.', source: 'updates', created: ago(9 * H), actionId: 'a-7f12' },
  { id: 'al-3', severity: 'info', title: 'office-laptop has no A/B slots', body: 'It is a developer install, so OS updates cannot roll back by themselves.', source: 'repairs', created: ago(5 * D), acked: true },
];

export const backup = {
  lastRun: ago(41 * 60),
  lastVerifiedRestore: ago(D + 2 * H),
  schedule: 'Every hour, keep 24 hourly · 7 daily · 4 weekly',
  destinations: [
    { id: 'usb', name: 'usb-backup', kind: 'USB disk on home-hub', last: ago(41 * 60), state: 'ok' as const, size: '84 GB of 1 TB' },
    { id: 'peer', name: 'pi-garage', kind: 'Another OneMind box', last: ago(41 * 60), state: 'ok' as const, size: '84 GB of 119 GB' },
    { id: 's3', name: 'offsite-s3', kind: 'S3-compatible bucket', last: ago(26 * H), state: 'warn' as const, size: '79 GB' },
  ],
  snapshots: [
    { id: 'c81d02e4', at: ago(41 * 60), scope: 'Whole box', size: '412 MB new', verified: false },
    { id: '5b0f9a11', at: ago(101 * 60), scope: 'Whole box', size: '96 MB new', verified: false },
    { id: '0e7713cd', at: ago(D + 3 * H), scope: 'Whole box', size: '1.1 GB new', verified: true },
    { id: 'f2a9be40', at: ago(8 * D), scope: 'Whole box', size: '2.4 GB new', verified: true },
  ],
  keys: [
    { name: 'Box key', where: 'TPM on home-hub', state: 'ok' as const },
    { name: 'Owner recovery key', where: 'Printed emergency kit', state: 'ok' as const },
    { name: 'Offsite key', where: 'Not set up', state: 'warn' as const },
  ],
};

export const updates = {
  os: { booted: 'A', version: '0.3.1', other: 'B', otherVersion: '0.3.0', channel: 'security', window: '03:00–04:00 daily', available: '0.3.2' },
  history: [
    { at: ago(9 * D), what: 'OS 0.3.0 → 0.3.1', node: 'home-hub', result: 'ok' as const, label: 'Committed (slot A)' },
    { at: ago(12 * D), what: 'OS 0.2.9 → 0.3.0', node: 'pi-garage', result: 'bad' as const, label: 'Rolled back: k3s not ready after 5 min' },
    { at: ago(12 * D - H), what: 'OS 0.2.9 → 0.3.0 (retry)', node: 'pi-garage', result: 'ok' as const, label: 'Committed (slot B)' },
    { at: ago(14 * D), what: 'Uptime Kuma 2.5.9 → 2.5.10', node: 'pi-garage', result: 'ok' as const, label: 'Healthy after 5 min' },
  ],
};

export const people = [
  { id: 'person:owner', name: 'Owner', role: 'owner', signIn: 'Passkey (2 devices)', last: ago(5 * 60) },
  { id: 'person:alex', name: 'Alex', role: 'adult', signIn: 'Passkey', last: ago(2 * D) },
  { id: 'person:guest-tv', name: 'Living-room TV', role: 'guest', signIn: 'Device code', last: ago(6 * H) },
];

export const tokens = [
  { id: 'agent:hermes-agent', kind: 'Agent', scope: 'read nodes, read apps, request actions', created: ago(5 * D), last: ago(6 * 60) },
  { id: 'cli:owner-laptop', kind: 'CLI token', scope: 'owner (expires in 23 d)', created: ago(7 * D), last: ago(H) },
];

export const posture = [
  { item: 'HTTPS on your network', state: 'ok' as const, detail: 'Per-box certificate authority; installed on 2 devices' },
  { item: 'Sign-in', state: 'ok' as const, detail: 'Passkeys only; no passwords' },
  { item: 'Disk encryption', state: 'ok' as const, detail: 'Data partition encrypted, key sealed to the TPM' },
  { item: 'Secure Boot', state: 'warn' as const, detail: 'Disabled in firmware on home-hub' },
  { item: 'App isolation', state: 'ok' as const, detail: 'Each app in its own namespace; restricted Pod Security; default-deny network' },
  { item: 'Exposed to the internet', state: 'ok' as const, detail: 'Nothing is exposed. Remote access is off.' },
  { item: 'Agents', state: 'ok' as const, detail: '1 agent; it can request, never approve' },
];
