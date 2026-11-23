// SPDX-License-Identifier: Apache-2.0
// App deep links (#617): onemind://app/<id>/<route> and the matching web path /apps/<id>/<route>.
// The phone and desktop apps open the onemind:// form; the dashboard serves the same place at the web
// path. A built-in app the dashboard draws itself (Files, Settings, Market...) has its own screen, so
// its web path lands there; any other app lands on its app page.

/** The gateway's app id rule (core catalog.APP_ID_RE): lower-case letters, digits and dashes. */
const APP_ID = /^[a-z0-9]([a-z0-9-]{0,57}[a-z0-9])?$/;
/** One route segment: plain words only, so a link can never smuggle a scheme, a host or "..". */
const SEGMENT = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;
const SCHEME = 'onemind://app/';

/** Built-in apps with no screen of the same name. */
const SCREEN_ALIAS: Record<string, string> = { notifications: '/activity' };

function cleanRoute(route: string): string[] | undefined {
  const parts = route.split('/').filter(Boolean);
  if (parts.length > 8 || parts.some((p) => !SEGMENT.test(p) || p.includes('..'))) return undefined;
  return parts;
}

/** `onemind://app/<id>/<route>`; undefined when the id or the route is not a safe link. */
export function appDeepLink(appId: string, route = ''): string | undefined {
  const parts = cleanRoute(route);
  if (!APP_ID.test(appId) || !parts) return undefined;
  return `${SCHEME}${appId}${parts.length ? `/${parts.join('/')}` : ''}`;
}

/** The web path of the same place: `/apps/<id>/<route>`. */
export function appWebPath(appId: string, route = ''): string | undefined {
  const parts = cleanRoute(route);
  if (!APP_ID.test(appId) || !parts) return undefined;
  return `/apps/${appId}${parts.length ? `/${parts.join('/')}` : ''}`;
}

/** An onemind://app/... link as its web path, or undefined when it is not one (or not a safe one). */
export function deepLinkToPath(link: string): string | undefined {
  if (!link.startsWith(SCHEME)) return undefined;
  const rest = link.slice(SCHEME.length).split(/[?#]/)[0] ?? '';
  const [id = '', ...route] = rest.split('/');
  return appWebPath(id, route.join('/'));
}

/**
 * Where /apps/<id>/<route> opens when the dashboard draws that app itself: the screen with the app's id
 * (Settings → /settings/<route>), or undefined for an app that has its own app page.
 */
export function builtInScreenPath(appId: string, route: string, screenPaths: ReadonlyMap<string, string>): string | undefined {
  const base = SCREEN_ALIAS[appId] ?? screenPaths.get(appId);
  const parts = cleanRoute(route);
  if (!base || !parts) return undefined;
  return `${base === '/' ? '' : base}${parts.length ? `/${parts.join('/')}` : ''}` || '/';
}
