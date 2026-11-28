// SPDX-License-Identifier: Apache-2.0
// Dashboard routes, and the mapping from the hash links @onemind/ui uses by default ("#/apps",
// "#/app/<id>", "#/settings/people", ...) to the dashboard's real paths. ui components take
// hrefs as props where they can; this covers the rest (palette commands, notification links).
import { navIdFor } from '../screens/registry';
import { deepLinkToPath } from '../lib/appLinks';

export const href = {
  home: '/',
  market: '/market',
  app: (id: string) => `/market/${encodeURIComponent(id)}`,
  /** Atlas Market (04): the person's own app requests, waiting and decided. */
  marketRequests: '/market/requests',
  installed: '/installed',
  /** #617: the Market's Built in tab (GET /v1/system-apps). */
  builtIn: '/built-in',
  sources: '/sources',
  compose: '/compose',
  /** PLG-GIT-01: the Market's Custom tab (apps linked from a Git repository). */
  custom: '/custom',
  manage: (id: string) => `/installed/${encodeURIComponent(id)}`,
  browser: (id: string) => `/browser/${encodeURIComponent(id)}`,
  approvals: '/approvals',
  approval: (id: string) => `/approvals?highlight=${encodeURIComponent(id)}`,
  activity: '/activity',
  nodes: '/nodes',
  machines: '/machines',
  alerts: '/alerts',
  storage: '/storage',
  backups: '/backups',
  troubleshoot: '/troubleshoot',
  automation: '/automation',
  updates: '/updates',
  fileSharing: '/file-sharing',
  usage: '/usage',
  network: '/network',
  coming: '/coming',
  controlHub: '/control-hub',
  agents: '/agents',
  settings: '/settings',
  setting: (id: string) => `/settings/${id}`,
};

/** ui settings slugs (palette) → SettingsLayout section ids. */
const SETTINGS_ALIAS: Record<string, string> = { people: 'users', remote: 'network' };

/**
 * An in-app path for a ui link (or an onemind://app deep link), or undefined when it is not an in-app link (an external or
 * protocol-relative URL is never followed from here).
 */
export function toRoute(link: string): string | undefined {
  // onemind://app/<id>/<route> (#617) opens the same place as its web path, /apps/<id>/<route>.
  if (link.startsWith('onemind://')) return deepLinkToPath(link);
  let p = link.startsWith('#/') ? link.slice(1) : link;
  // Browsers read a backslash as "/" and drop tabs and newlines, so "/\host" is protocol-relative too;
  // react-router falls back to location.assign when pushState refuses another origin.
  // eslint-disable-next-line no-control-regex
  if (!p.startsWith('/') || p.startsWith('//') || /[\\\u0000-\u001f\u007f]/.test(p)) return undefined;
  const [path = '/', query = ''] = p.split('?');
  const parts = path.split('/').filter(Boolean);
  const q = query ? `?${query}` : '';
  switch (parts[0]) {
    case undefined:
    case 'home':
      return '/';
    case 'apps':
    case 'store':
      return href.market + q;
    case 'app':
      return parts[1] ? `/market/${parts[1]}` : href.market;
    case 'approvals':
      return parts[1] ? `/approvals?highlight=${parts[1]}` : href.approvals + q;
    case 'nodes':
      return href.nodes;
    case 'machines':
      return parts.length === 2 ? path + q : href.machines;
    case 'notifications':
      return href.activity;
    case 'backups':
      return href.backups;
    case 'automation':
      return href.automation;
    case 'updates':
      return href.updates;
    case 'file-sharing':
      return href.fileSharing;
    case 'usage':
      return href.usage;
    case 'network':
      return href.network;
    case 'storage':
      return href.storage;
    case 'settings':
      return parts[1] ? href.setting(SETTINGS_ALIAS[parts[1]] ?? parts[1]) : href.settings;
    default:
      p = path;
      return p + q;
  }
}

/** Which nav item a path belongs to (the screen registry knows detail pages and tabs). */
export function navId(pathname: string): string {
  return navIdFor(pathname);
}
