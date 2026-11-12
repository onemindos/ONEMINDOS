// SPDX-License-Identifier: Apache-2.0
// Dashboard routes, and the mapping from the hash links @onemind/ui uses by default ("#/apps",
// "#/app/<id>", "#/settings/people", ...) to the dashboard's real paths. ui components take
// hrefs as props where they can; this covers the rest (palette commands, notification links).

export const href = {
  home: '/',
  market: '/market',
  app: (id: string) => `/market/${encodeURIComponent(id)}`,
  installed: '/installed',
  manage: (id: string) => `/installed/${encodeURIComponent(id)}`,
  approvals: '/approvals',
  approval: (id: string) => `/approvals?highlight=${encodeURIComponent(id)}`,
  activity: '/activity',
  nodes: '/nodes',
  settings: '/settings',
  setting: (id: string) => `/settings/${id}`,
};

/** ui settings slugs (palette) → SettingsLayout section ids. */
const SETTINGS_ALIAS: Record<string, string> = { people: 'users', security: 'account', remote: 'network' };

/**
 * An in-app path for a ui link, or undefined when it is not an in-app link (an external or
 * protocol-relative URL is never followed from here).
 */
export function toRoute(link: string): string | undefined {
  let p = link.startsWith('#/') ? link.slice(1) : link;
  if (!p.startsWith('/') || p.startsWith('//')) return undefined;
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
    case 'notifications':
      return href.activity;
    case 'backups':
    case 'updates':
      return href.setting(parts[0]);
    case 'settings':
      return parts[1] ? href.setting(SETTINGS_ALIAS[parts[1]] ?? parts[1]) : href.settings;
    default:
      p = path;
      return p + q;
  }
}

/** Which nav item a path belongs to. */
export function navId(pathname: string): string {
  const first = pathname.split('/').filter(Boolean)[0] ?? 'home';
  return first;
}
