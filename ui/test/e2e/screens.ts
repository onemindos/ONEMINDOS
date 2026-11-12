// SPDX-License-Identifier: Apache-2.0
// Every screen the browser checks visit, and the helpers they share (docs/testing/CI-MATRIX.md).
// A new demo route or dashboard page gets a line here, so axe and the console check cover it.
import AxeBuilder from '@axe-core/playwright';
import { expect, type Page, type TestInfo } from '@playwright/test';

export const UI_URL = 'http://127.0.0.1:4173/';
export const DASH_URL = 'http://127.0.0.1:4174/';
// The demo fixtures are frozen at 2026-11-12 15:00-15:04 UTC (ui/demo/src/*fixtures.ts); the dashboard
// mock builds its fixtures from Date.now(). One fixed clock makes every "x min ago" deterministic.
export const FIXED_TIME = new Date('2026-11-12T15:05:00Z');
export const DASH_TOKEN = 'owner-demo'; // dashboard/src/api/fixtures.ts DEMO_TOKENS (mock build only)

export type Theme = 'light' | 'dark';
export interface Screen {
  /** Stable name, used in test titles and snapshot file names. */
  name: string;
  target: 'ui' | 'dashboard';
  /** ui: hash route (no leading '#/'), optional query; dashboard: path. */
  route: string;
  query?: Record<string, string>;
  /** Dashboard screens need a signed-in session; the sign-in page does not. */
  signedIn?: boolean;
}

const ui = (route: string, query?: Record<string, string>, name?: string): Screen => ({
  name: name ?? `ui-${route.replace(/\//g, '-')}${query?.state ? `-${query.state}` : ''}`,
  target: 'ui',
  route,
  query,
});
const states = (route: string) =>
  (['loading', 'error', 'stale', 'empty'] as const).map((state) => ui(route, { state }));

// ui/demo/src/DemoApp.tsx routes and their arguments.
export const UI_SCREENS: Screen[] = [
  // Primary IA screens (docs/design/IA.md; same list as ui/scripts/screenshots.mjs)
  ...['home', 'apps', 'app/home-assistant', 'app/immich', 'approvals', 'activity', 'nodes', 'backups', 'updates', 'notifications', 'settings', 'gallery'].map((r) => ui(r)),
  // Home launcher variants (ui/demo/src/home/HomeLauncher.tsx)
  ...['edit', 'errors', 'fresh', 'loading', 'offline'].map((v) => ui(`home/${v}`)),
  // Settings sections (ui/src/settings SETTINGS_SECTIONS) and the system activity and approvals pages
  ui('system'),
  ...['account', 'users', 'agents', 'devices', 'network', 'storage', 'backups', 'updates', 'notifications', 'automation', 'about', 'activity', 'approvals'].map((s) => ui(`system/${s}`)),
  ...states('system/backups'),
  ...states('system/approvals'),
  // Appearance and customization states (ui/demo/src/customize/AppearanceDemo.tsx)
  ui('appearance'),
  ...['synced', 'custom', 'stale', 'empty', 'loading', 'error'].map((s) => ui(`appearance/${s}`)),
  // App Store (ui/demo/src/store/StoreDemo.tsx)
  ui('store'),
  ...['store/installed', 'store/updates', 'store/manage/home-assistant', 'store/app/immich', 'store/app/ollama'].map((r) => ui(r)),
  ...states('store'),
  // Shell: command palette, notifications, toasts, shared states, onboarding (ui/demo/src/shell/ShellScreens.tsx)
  ...['palette', 'palette-search', 'notifications', 'toasts', 'states'].map((a) => ui(`shell/${a}`)),
  ...[1, 2, 3, 4, 5, 6].map((n) => ui(`shell/onboarding-${n}`)),
];

// dashboard/src/App.tsx routes. The dashboard has one (light) theme today.
export const DASH_SCREENS: Screen[] = [
  { name: 'dash-signin', target: 'dashboard', route: '' },
  { name: 'dash-home', target: 'dashboard', route: '', signedIn: true },
  { name: 'dash-nodes', target: 'dashboard', route: 'nodes', signedIn: true },
  { name: 'dash-market', target: 'dashboard', route: 'market', signedIn: true },
  { name: 'dash-market-uptime-kuma', target: 'dashboard', route: 'market/uptime-kuma', signedIn: true },
  { name: 'dash-approvals', target: 'dashboard', route: 'approvals', signedIn: true },
];

export function urlFor(s: Screen, theme: Theme): string {
  if (s.target === 'dashboard') return DASH_URL + s.route;
  const q = new URLSearchParams({ theme, ...s.query });
  return `${UI_URL}?${q}#/${s.route}`;
}

/** Collects uncaught exceptions and console errors for the page's lifetime. */
export function watchErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(`console.error: ${m.text()}`);
  });
  return errors;
}

/** Opens a screen with the fixed clock (and a demo session for signed-in dashboard pages) and waits until it has settled. */
export async function open(page: Page, s: Screen, theme: Theme): Promise<void> {
  await page.clock.setFixedTime(FIXED_TIME);
  if (s.signedIn) {
    await page.addInitScript((token) => window.sessionStorage.setItem('onemind.token', token), DASH_TOKEN);
  }
  await page.goto(urlFor(s, theme));
  if (s.target === 'ui') {
    await expect(page.locator('#om-main')).toBeVisible();
  } else {
    await expect(page.locator('h1').first()).toBeVisible();
    // Mock data arrives asynchronously: wait until no "Loading …" status is left.
    await expect(page.getByRole('status').filter({ hasText: /^Loading / })).toHaveCount(0);
  }
  await settle(page);
}

export async function settle(page: Page): Promise<void> {
  await page.evaluate(async () => {
    await document.fonts.ready;
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  });
}

const BLOCKING = new Set(['serious', 'critical']);

/**
 * Runs axe-core (every rule axe enables by default: WCAG 2.0-2.2 A/AA plus best practices) and fails
 * on serious or critical findings. The full result is attached to the report either way, so
 * moderate and minor findings stay visible without blocking.
 */
export async function expectNoSeriousAxeViolations(page: Page, testInfo: TestInfo): Promise<void> {
  const results = await new AxeBuilder({ page }).analyze();
  await testInfo.attach('axe-results.json', { body: JSON.stringify(results, null, 2), contentType: 'application/json' });
  const blocking = results.violations.filter((v) => BLOCKING.has(v.impact ?? ''));
  const lines = blocking.map(
    (v) => `${v.impact} ${v.id}: ${v.help} (${v.helpUrl})\n${v.nodes.slice(0, 5).map((n) => `    ${n.target.join(' ')}`).join('\n')}`,
  );
  expect(lines, `axe found ${blocking.length} serious/critical violation(s):\n${lines.join('\n')}`).toEqual([]);
}
