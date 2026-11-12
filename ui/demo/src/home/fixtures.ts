// SPDX-License-Identifier: Apache-2.0
// Typed fixtures for the Home launcher. Shapes follow sdk/contracts/poc-v0.md (§2 heartbeat,
// §3 nodes/apps/actions) and docs/design/TAXONOMY.md (category, deploy_class); fields the
// contract does not have yet are PROPOSED (see ui/src/home/README.md). All names invented;
// the clock is frozen so screenshots are reproducible.
import type { ActionSummary } from '../../../src/components/ApprovalCard';
import type { NodeSummary } from '../../../src/components/NodeCard';
import type { HomeLayout } from '../../../src/home/layout';
import type { HomeApp, HomeData, HomeNode } from '../../../src/home/types';

export const NOW = Date.parse('2026-11-12T15:04:00Z');
const ago = (s: number) => new Date(NOW - s * 1000).toISOString();
const later = (s: number) => new Date(NOW + s * 1000).toISOString();
const H = 3600;
const D = 86_400;

export const TIME_ZONE = 'Europe/London';
export const PERSON = { id: 'person:owner', name: 'Robin' };

/** Full heartbeat objects (NodeSummary, contract §2/§3) plus the two PROPOSED Home fields. */
export const nodes: Array<NodeSummary & HomeNode> = [
  {
    node_id: '3f9c2a1b7d4e', hostname: 'home-hub', role: 'hub', board: 'x86_64-efi', arch: 'amd64', os: { pretty: 'OneMind OS 0.3 (Debian 13)' },
    cpus: 8, mem_total_mb: 16_384, mem_available_mb: 9_420, disk_total_gb: 477, disk_free_gb: 352,
    k3s: { present: true, ready: true, role: 'server' }, rauc: { present: true, booted_slot: 'A' },
    uptime_s: 12 * D + 5 * H, cpu_percent: 23, temp_c: 52, last_seen: ago(4), status: 'online',
  },
  {
    node_id: 'a1d07c55e912', hostname: 'pi-garage', role: 'node', board: 'rpi5', arch: 'arm64', os: { pretty: 'OneMind OS 0.3 (Debian 13)' },
    cpus: 4, mem_total_mb: 8_192, mem_available_mb: 1_150, disk_total_gb: 119, disk_free_gb: 96,
    k3s: { present: true, ready: true, role: 'agent' }, rauc: { present: true, booted_slot: 'B' },
    uptime_s: 3 * D + 2 * H, cpu_percent: 71, temp_c: 78, last_seen: ago(7), status: 'online',
  },
  {
    node_id: '77be01c4aa30', hostname: 'office-laptop', role: 'node', board: 'x86_64-efi', arch: 'amd64', os: { pretty: 'Debian GNU/Linux 13 (trixie)' },
    cpus: 12, mem_total_mb: 32_768, mem_available_mb: 21_000, disk_total_gb: 953, disk_free_gb: 610,
    k3s: { present: true, ready: true, role: 'agent' }, rauc: { present: false, booted_slot: null },
    uptime_s: 5 * H, cpu_percent: 9, temp_c: null, last_seen: ago(75), status: 'stale',
  },
  {
    node_id: 'c09e5d2f1b88', hostname: 'cloud-relay', role: 'node', board: 'vm-do', arch: 'amd64', os: { pretty: 'Debian GNU/Linux 13 (trixie)' },
    cpus: 2, mem_total_mb: 2_048, mem_available_mb: 1_100, disk_total_gb: 50, disk_free_gb: 31,
    k3s: { present: true, ready: false, role: 'agent' }, rauc: { present: false, booted_slot: null },
    uptime_s: 40 * D, last_seen: ago(3 * H + 600), status: 'offline',
  },
];

export const apps: HomeApp[] = [
  {
    id: 'home-assistant', name: 'Home Assistant', version: '2026.11.1', description: 'Home automation that puts local control first.',
    category: 'home-automation', tags: ['hub', 'zigbee'], deploy_class: 'market-verified', plugin: true, installed: true, status: 'running',
    node: 'home-hub', hue: 'teal', update_available: '2026.11.2', open_url: 'https://home-assistant.home-hub.example',
    widgets: [{ id: 'energy', title: 'Energy today', template: 'stat', source: { path: '/api/onemind/widgets/energy', refreshSeconds: 300 } }],
  },
  {
    id: 'immich', name: 'Immich', version: '2.3.0', description: 'Photo and video backup from your phones.',
    category: 'files', tags: ['photos'], deploy_class: 'market-verified', plugin: true, installed: true, status: 'running', node: 'office-laptop', hue: 'blue',
    widgets: [{ id: 'library', title: 'Phone backup', template: 'progress', source: { path: '/api/onemind/widgets/library', refreshSeconds: 600 } }],
  },
  { id: 'jellyfin', name: 'Jellyfin', version: '10.11.2', description: 'Your films, shows and music, streamed at home.', category: 'media', tags: ['video', 'music'], deploy_class: 'market-verified', installed: true, status: 'running', node: 'home-hub', hue: 'violet', update_available: '10.11.3' },
  {
    id: 'uptime-kuma', name: 'Uptime Kuma', version: '2.0.2', description: 'Checks that your sites and services are up.',
    category: 'monitoring', tags: ['uptime'], deploy_class: 'market-verified', plugin: true, installed: true, status: 'running', node: 'pi-garage', hue: 'green',
    widgets: [{ id: 'monitors', title: 'Monitors', template: 'stats', source: { path: '/api/onemind/widgets/monitors', refreshSeconds: 30 } }],
  },
  {
    id: 'ntfy', name: 'ntfy', version: '2.37.2', description: 'Push notifications to your phone from any script.',
    category: 'notifications', tags: ['notifications'], deploy_class: 'market-verified', plugin: true, installed: true, status: 'running', node: 'home-hub', hue: 'amber',
    widgets: [{ id: 'messages', title: 'Last messages', template: 'list', source: { path: '/api/onemind/widgets/messages', refreshSeconds: 60 } }],
  },
  { id: 'hermes-agent', name: 'Hermes Agent', version: '0.4.0', description: 'Your AI agent. It asks; you approve.', category: 'ai', tags: ['agents'], deploy_class: 'market-community', plugin: true, installed: true, status: 'running', node: 'home-hub', hue: 'violet' },
  { id: 'vaultwarden', name: 'Vaultwarden', version: '1.34.3', description: 'Passwords for the whole household.', category: 'security', tags: ['passwords'], deploy_class: 'market-verified', installed: true, status: 'starting', node: 'home-hub', hue: 'blue' },
  {
    id: 'frigate', name: 'Frigate', version: '0.16.2', description: 'Camera recorder with local object detection.',
    category: 'home', tags: ['cameras'], deploy_class: 'market-verified', plugin: true, installed: true, status: 'unhealthy', node: 'pi-garage', hue: 'red',
    widgets: [{ id: 'events', title: 'Events', template: 'list', source: { path: '/api/onemind/widgets/events', refreshSeconds: 60 } }],
  },
  { id: 'node-red', name: 'Node-RED', version: '4.1.1', description: 'Wire devices and services together in flows.', category: 'automation', tags: ['workflows'], deploy_class: 'market-verified', installed: true, status: 'updating', node: 'pi-garage', hue: 'red' },
  { id: 'opentakserver', name: 'OpenTAKServer', version: '1.6.0', description: 'TAK server for field teams and maps.', category: 'field', tags: ['tak', 'maps'], deploy_class: 'market-community', installed: true, status: 'stopped', node: 'office-laptop', hue: 'green' },
  { id: 'family-site', name: 'Family site', version: 'sha-4e1c0a2', description: 'Your own static website, deployed from a compose file.', category: 'productivity', tags: ['website'], deploy_class: 'private', installed: true, status: 'running', node: 'home-hub', hue: 'amber' },
  { id: 'backup-agent', name: 'Backups', version: '0.3.1', description: 'The OS backup agent (restic). Part of OneMind.', category: 'files', tags: ['backup'], deploy_class: 'core', installed: true, status: 'running', node: 'home-hub', hue: 'neutral' },
  { id: 'paperless-ngx', name: 'Paperless-ngx', version: '2.18.0', description: 'Scan, index and archive your paper documents.', category: 'files', tags: ['documents'], deploy_class: 'market-verified', installed: false, hue: 'green' },
];

export const pending: ActionSummary[] = [
  {
    id: 'a-7f31', type: 'app.install', params: { app_id: 'paperless-ngx' }, state: 'awaiting_approval', expires_at: later(20 * H), created_at: ago(9 * 60),
    requested_by: { id: 'agent:hermes-agent', kind: 'agent', role: 'agent' }, reason: 'You asked me to file the scanned letters in the inbox folder.',
  },
  {
    id: 'a-7f2c', type: 'app.update', params: { app_id: 'home-assistant', from: '2026.11.1', to: '2026.11.2' }, state: 'awaiting_approval', expires_at: later(6 * H), created_at: ago(2 * H),
    requested_by: { id: 'system:updates', kind: 'agent', role: 'agent' }, reason: 'Patch release with 3 security fixes.',
  },
  {
    id: 'a-7f12', type: 'os.update', params: { node_id: 'home-hub', from: '0.3.1', to: '0.3.2', channel: 'security' }, state: 'awaiting_approval', expires_at: later(40 * 60), created_at: ago(9 * H),
    requested_by: { id: 'system:updates', kind: 'agent', role: 'agent' }, reason: 'Fixes 2 CVEs in the base image.',
  },
];

export const homeData: HomeData = {
  hub: { observed_at: ago(2) },
  nodes: { state: 'ready', data: nodes },
  apps: { state: 'ready', data: apps },
  approvals: { state: 'ready', data: pending },
  activity: {
    state: 'ready',
    data: [
      { seq: 1042, at: ago(9 * 60), actor: { kind: 'agent', name: 'Hermes Agent' }, text: 'asked to install Paperless-ngx', result: { tone: 'warn', label: 'Waiting' } },
      { seq: 1041, at: ago(41 * 60), actor: { kind: 'system', name: 'Backups' }, text: 'backed up the whole box (412 MB new)', result: { tone: 'ok', label: 'Done' } },
      { seq: 1040, at: ago(2 * H), actor: { kind: 'system', name: 'Updates' }, text: 'found Home Assistant 2026.11.2' },
      { seq: 1039, at: ago(5 * H), actor: { kind: 'person', name: 'Robin' }, text: 'approved Uptime Kuma settings change', result: { tone: 'ok', label: 'Done' } },
      { seq: 1038, at: ago(D), actor: { kind: 'system', name: 'Backups' }, text: 'restore test of Immich passed', result: { tone: 'ok', label: 'Verified' } },
      { seq: 1037, at: ago(D + 4 * H), actor: { kind: 'person', name: 'Alex' }, text: 'asked to install Jellyfin', result: { tone: 'ok', label: 'Approved' } },
    ],
  },
  backups: {
    state: 'ready',
    data: {
      last_run: ago(41 * 60),
      last_verified_restore: ago(D + 3 * H),
      destinations: [
        { name: 'usb-backup', last_success: ago(41 * 60), state: 'ok' },
        { name: 'pi-garage', last_success: ago(41 * 60), state: 'ok' },
        { name: 'offsite-s3', last_success: ago(26 * H), state: 'behind' },
      ],
      observed_at: ago(30),
    },
  },
  updates: {
    state: 'ready',
    data: {
      os: { from: '0.3.1', to: '0.3.2', channel: 'security', action_id: 'a-7f12' },
      apps: [
        { app_id: 'home-assistant', from: '2026.11.1', to: '2026.11.2' },
        { app_id: 'jellyfin', from: '10.11.2', to: '10.11.3' },
      ],
      checked_at: ago(2 * H),
    },
  },
  mesh: {
    state: 'ready',
    data: {
      links: [
        { hostname: 'pi-garage', via: 'lan', state: 'up', rtt_ms: 2 },
        { hostname: 'office-laptop', via: 'mesh', state: 'degraded', rtt_ms: 84 },
        { hostname: 'cloud-relay', via: 'leaf', state: 'down' },
      ],
      remote_access: 'mesh',
      observed_at: ago(10),
    },
  },
  appWidgets: {
    'uptime-kuma/monitors': { state: 'ready', data: { template: 'stats', items: [{ value: 12, label: 'Up' }, { value: 0, label: 'Down' }, { value: 1, label: 'Paused' }, { value: '38 ms', label: 'Avg response' }], updated_at: ago(12) } },
    'ntfy/messages': { state: 'ready', data: { template: 'list', items: [{ text: 'Backup finished', detail: 'backups', at: ago(41 * 60) }, { text: 'Garage door left open', detail: 'home', at: ago(3 * H) }, { text: 'Disk 80 % on pi-garage', detail: 'alerts', at: ago(6 * H) }], updated_at: ago(40) } },
    'home-assistant/energy': { state: 'ready', data: { template: 'stat', value: '4.2', unit: 'kWh', label: 'Used today, 18 % solar', updated_at: ago(22 * 60) } },
    'immich/library': { state: 'ready', data: { template: 'progress', label: 'Photos from phones', value: 9_812, max: 10_040, text: '9,812 of 10,040 backed up', updated_at: ago(4 * 60) } },
    'frigate/events': { state: 'ready', data: { template: 'list', items: [{ text: 'Person at the front door', at: ago(9 * 60) }, { text: 'Car in the drive', at: ago(52 * 60) }], updated_at: ago(9 * 60) } },
  },
  weather: { temp_c: 9, summary: 'Light rain', source: 'Home Assistant', updated_at: ago(12 * 60) },
};

export const demoLayout: HomeLayout = {
  version: 1,
  widgets: [
    { id: 'w-approvals', kind: 'approvals', size: 'M' },
    { id: 'w-system', kind: 'system', size: 'M' },
    { id: 'w-updates', kind: 'updates', size: 'S' },
    { id: 'w-backups', kind: 'backups', size: 'S' },
    { id: 'w-kuma', kind: 'app', appId: 'uptime-kuma', widgetId: 'monitors', size: 'S' },
    { id: 'w-mesh', kind: 'mesh', size: 'S' },
    { id: 'w-hub', kind: 'system', nodeId: '3f9c2a1b7d4e', size: 'M' },
    { id: 'w-ntfy', kind: 'app', appId: 'ntfy', widgetId: 'messages', size: 'S' },
    { id: 'w-energy', kind: 'app', appId: 'home-assistant', widgetId: 'energy', size: 'S' },
    { id: 'w-activity', kind: 'activity', size: 'M' },
    { id: 'w-immich', kind: 'app', appId: 'immich', widgetId: 'library', size: 'S' },
    { id: 'w-frigate', kind: 'app', appId: 'frigate', widgetId: 'events', size: 'S' },
  ],
  pinned: ['home-assistant', 'immich', 'jellyfin', 'vaultwarden', 'hermes-agent'],
};

/** Every section still loading (first paint). */
export const loadingData: HomeData = {
  hub: { observed_at: ago(1) },
  nodes: { state: 'loading' },
  apps: { state: 'loading' },
  approvals: { state: 'loading' },
  activity: { state: 'loading' },
  backups: { state: 'loading' },
  updates: { state: 'loading' },
  mesh: { state: 'loading' },
  appWidgets: {},
};

/** The hub stopped answering 6 minutes ago: everything is last known. */
export const offlineData: HomeData = { ...homeData, hub: { observed_at: ago(6 * 60) } };

/** Sections that failed, with the contract error shape. */
export const errorData: HomeData = {
  ...homeData,
  backups: { state: 'error', error: 'not_found', message: 'The backup agent is not running on home-hub.' },
  mesh: { state: 'error', error: 'outcome_unknown', message: 'The fabric did not answer within 5 s.' },
  appWidgets: { ...homeData.appWidgets, 'uptime-kuma/monitors': { state: 'error', error: 'invalid_payload', message: 'Uptime Kuma sent data that does not match the stats template.' } },
};

/** A new box: one node, no apps, nothing waiting. */
export const freshData: HomeData = {
  hub: { observed_at: ago(2) },
  nodes: { state: 'ready', data: [nodes[0]!] },
  apps: { state: 'ready', data: [apps.find((a) => a.id === 'backup-agent')!].map((a) => ({ ...a, installed: false })) },
  approvals: { state: 'ready', data: [] },
  activity: { state: 'ready', data: [] },
  backups: { state: 'ready', data: { last_run: null, last_verified_restore: null, destinations: [], observed_at: ago(5) } },
  updates: { state: 'ready', data: { os: null, apps: [], checked_at: ago(H) } },
  mesh: { state: 'ready', data: { links: [], remote_access: 'off', observed_at: ago(5) } },
  appWidgets: {},
  weather: null,
};
