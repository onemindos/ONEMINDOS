// SPDX-License-Identifier: Apache-2.0
// Typed fixtures for the shell demo screens. Shapes: contract §2/§3 (nodes, actions), NOT-P1
// alert record (notifications, PROPOSED), TAXONOMY.md §1/§2 (categories, deployment classes).
// All names are invented. The clock is the demo's frozen NOW.
import type { PaletteApp, ShellNotification, StarterApp } from '../../../src';
import { NOW, ago, apps as demoApps } from '../fixtures';

export { NOW };

/** Legacy demo slugs mapped to TAXONOMY.md §1 ("Slugs already on main"). */
const SLUG: Record<string, string> = { notifications: 'automation', security: 'network', media: 'files' };

export const paletteApps: PaletteApp[] = demoApps
  .filter((a) => a.tier !== 'blocked')
  .map((a) => ({
    id: a.id,
    name: a.name,
    category: SLUG[a.category] ?? a.category,
    tagline: a.description,
    installed: a.installed,
    status: a.status,
    deployClass: a.tier === 'community' ? 'market-community' : 'market-verified',
    plugin: a.id === 'hermes-agent',
    updateAvailable: a.updateAvailable,
  }));

paletteApps.push(
  { id: 'jellyfin', name: 'Jellyfin', category: 'media', tagline: 'Stream your films and shows', installed: false, deployClass: 'market-verified' },
  { id: 'opentakserver', name: 'OpenTAKServer', category: 'field', tagline: 'TAK server for ATAK and iTAK', installed: false, deployClass: 'market-verified' },
  { id: 'n8n', name: 'n8n', category: 'automation', tagline: 'Workflow automation', installed: false, deployClass: 'list-only' },
);

export const recent = ['app:home-assistant', 'node:a1d07c55e912', 'set:appearance'];

export const notifications: ShellNotification[] = [
  {
    id: 'n-9',
    kind: 'approval_waiting',
    severity: 'warning',
    source: 'approvals',
    title: 'Hermes agent wants to install Node-RED',
    body: 'You asked it to automate the garage lights. Expires in 23 h.',
    created: ago(6 * 60),
    read: false,
    href: '#/approvals/a-7f31',
    actionId: 'a-7f31',
  },
  {
    id: 'n-8',
    kind: 'backup_failed',
    severity: 'critical',
    source: 'backup',
    title: 'Offsite backup failed twice',
    body: 'offsite-s3 refused the upload (403). Local backups are fine; the offsite copy is 26 h old.',
    created: ago(55 * 60),
    read: false,
    href: '#/backups',
  },
  {
    id: 'n-7',
    kind: 'app_rolled_back',
    severity: 'warning',
    source: 'updates',
    title: 'Uptime Kuma 2.6.0 was rolled back',
    body: 'Health probe failed 3 times after the update. Running 2.5.10 again; data from the snapshot.',
    created: ago(3 * 3600),
    read: false,
    href: '#/app/uptime-kuma',
  },
  {
    id: 'n-6',
    kind: 'node_offline',
    severity: 'warning',
    source: 'fabric',
    title: 'cloud-relay is offline',
    body: 'No heartbeat for 3 h. It runs no apps.',
    created: ago(3 * 3600 + 600),
    read: true,
    href: '#/nodes/c09e5d2f1b88',
  },
  {
    id: 'n-5',
    kind: 'update_applied',
    severity: 'info',
    source: 'updates',
    title: 'ntfy updated to 2.37.2',
    body: 'Healthy 5 minutes after the update. Snapshot kept for 7 days.',
    created: ago(20 * 3600),
    read: true,
    href: '#/app/ntfy',
  },
  {
    id: 'n-4',
    kind: 'update_applied',
    severity: 'info',
    source: 'updates',
    title: 'OneMind OS 0.3.1 is running on home-hub',
    body: 'Slot A committed after every health check passed.',
    created: ago(2 * 86_400),
    read: true,
    href: '#/updates',
  },
  {
    id: 'n-3',
    kind: 'app_installed',
    severity: 'info',
    source: 'market',
    title: 'ntfy is installed',
    created: ago(2 * 86_400 + 600),
    read: true,
    href: '#/app/ntfy',
  },
];

/** Starter apps for the wizard, across the TAXONOMY categories. */
export const starterApps: StarterApp[] = [
  { id: 'home-assistant', name: 'Home Assistant', tagline: 'Smart-home hub with local control', category: 'home', deployClass: 'market-verified', minMemoryMb: 1024, recommended: true },
  { id: 'immich', name: 'Immich', tagline: 'Photo and video backup with search', category: 'files', deployClass: 'market-community', minMemoryMb: 4096, recommended: true },
  { id: 'vaultwarden', name: 'Vaultwarden', tagline: 'Passwords for the whole family', category: 'network', deployClass: 'market-verified', minMemoryMb: 128, recommended: true },
  { id: 'hermes-agent', name: 'Hermes agent', tagline: 'An AI that asks; you approve', category: 'ai', deployClass: 'market-verified', plugin: true, minMemoryMb: 2048, recommended: true },
  { id: 'mosquitto', name: 'Mosquitto', tagline: 'MQTT broker for sensors', category: 'home', deployClass: 'market-verified', minMemoryMb: 64 },
  { id: 'nextcloud', name: 'Nextcloud', tagline: 'Files, calendar and contacts', category: 'files', deployClass: 'market-verified', minMemoryMb: 1024 },
  { id: 'jellyfin', name: 'Jellyfin', tagline: 'Stream your films and shows', category: 'media', deployClass: 'market-verified', minMemoryMb: 1024 },
  { id: 'navidrome', name: 'Navidrome', tagline: 'Your music, everywhere', category: 'media', deployClass: 'market-verified', minMemoryMb: 256 },
  { id: 'memos', name: 'Memos', tagline: 'Quick notes', category: 'notes', deployClass: 'market-verified', minMemoryMb: 128 },
  { id: 'karakeep', name: 'Karakeep', tagline: 'Bookmarks and read-later', category: 'notes', deployClass: 'market-community', minMemoryMb: 512 },
  { id: 'vikunja', name: 'Vikunja', tagline: 'Tasks and projects', category: 'productivity', deployClass: 'market-verified', minMemoryMb: 256 },
  { id: 'ollama', name: 'Ollama', tagline: 'Run AI models on your own hardware', category: 'ai', deployClass: 'market-verified', minMemoryMb: 4096 },
  { id: 'node-red', name: 'Node-RED', tagline: 'Wire up flows and automations', category: 'automation', deployClass: 'market-verified', minMemoryMb: 256 },
  { id: 'ntfy', name: 'ntfy', tagline: 'Push notifications to your phone', category: 'automation', deployClass: 'market-verified', minMemoryMb: 128 },
  { id: 'adguard-home', name: 'AdGuard Home', tagline: 'Block ads for every device', category: 'network', deployClass: 'market-verified', minMemoryMb: 128 },
  { id: 'uptime-kuma', name: 'Uptime Kuma', tagline: 'Know when a site goes down', category: 'monitoring', deployClass: 'market-verified', minMemoryMb: 256 },
  { id: 'freshrss', name: 'FreshRSS', tagline: 'News feeds, no algorithm', category: 'news', deployClass: 'market-verified', minMemoryMb: 128 },
  { id: 'gitea', name: 'Gitea', tagline: 'Your own Git server', category: 'developer', deployClass: 'market-verified', minMemoryMb: 512 },
  { id: 'mealie', name: 'Mealie', tagline: 'Recipes and meal plans', category: 'family', deployClass: 'market-verified', minMemoryMb: 256 },
  { id: 'actual', name: 'Actual', tagline: 'Budgeting that stays private', category: 'finance', deployClass: 'market-verified', minMemoryMb: 256 },
  { id: 'kiwix', name: 'Kiwix', tagline: 'Wikipedia, offline', category: 'learning', deployClass: 'market-verified', minMemoryMb: 256 },
  { id: 'opentakserver', name: 'OpenTAKServer', tagline: 'TAK server for ATAK and iTAK', category: 'field', deployClass: 'market-verified', minMemoryMb: 1024 },
  { id: 'n8n', name: 'n8n', tagline: 'Workflow automation', category: 'automation', deployClass: 'list-only', minMemoryMb: 512 },
];

export const hub = { freeMemoryMb: 9420, usbDisk: '1 TB USB disk (usb-backup)' };
