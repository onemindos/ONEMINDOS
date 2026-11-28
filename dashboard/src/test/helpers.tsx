// SPDX-License-Identifier: Apache-2.0
import { render, screen, within } from '@testing-library/react';
import type userEvent from '@testing-library/user-event';
import axe from 'axe-core';
import { MemoryRouter } from 'react-router';
import { App } from '../App';
import { DEMO_TOKENS } from '../api/fixtures';
import { MockApi } from '../api/mock';
import { SessionProvider, type SessionDeps } from '../session';
import type { ActionType, AppParams } from '../api/types';

/** Lifecycle fixtures belong only in tests, not in the user-reachable demo gateway. */
function testApi(token: string) {
  const preview = async (type: ActionType, params: AppParams) => ({ plan: { summary: `${type}: ${params.app_id}`, objects: [], volumes: [], warnings: [] }, plan_sha256: 'sha256:test-fixture', app_id: params.app_id, type, risk: 'write', policy_verdict: 'needs_approval', reason: null });
  const api = new MockApi(token);
  const listApps = api.apps.bind(api);
  // Licence gate responses for the SPDX expressions in the dashboard test catalogue.
  const licenceClasses: Record<string, 'L1' | 'L2'> = {
    MIT: 'L1', 'Apache-2.0': 'L1', 'GPL-2.0-only': 'L2', 'GPL-3.0-only': 'L2', 'AGPL-3.0-only': 'L2',
  };
  return Object.assign(api, {
    apps: async () => (await listApps()).map((app) => {
      const cls = app.license && licenceClasses[app.license];
      return app.scan && cls && app.license
        ? { ...app, scan: { ...app.scan, licence: { class: cls, spdx: app.license } } } : app;
    }),
    appPlan: (id: string) => preview('app.install', { app_id: id }), previewAction: preview,
    appSettings: async () => ({ fields: [], values: {} }), appLogs: async () => '',
  });
}

/**
 * Render the whole app on a route. With `token`, the user starts signed in.
 * One MockApi is shared for the whole test (so state changes are visible);
 * when the user signs in through the form, it is rebuilt for the typed token.
 */
export function renderApp(opts: { token?: string; route?: string; knownRole?: boolean; mock?: boolean } = {}) {
  let api = testApi(opts.token ?? '');
  if (opts.token) window.sessionStorage.setItem('onemind.token', opts.token);
  const deps: SessionDeps = {
    mock: opts.mock ?? true,
    makeApi: (t) => {
      if (t === '') return t === (opts.token ?? '') ? api : testApi(''); // the credential-less client
      if (t !== (opts.token ?? '')) api = testApi(t);
      return api;
    },
    // knownRole=false simulates a real gateway, where v0 cannot ask "who am I".
    knownPrincipal: opts.knownRole === false ? () => undefined : (t) => DEMO_TOKENS[t],
  };
  const utils = render(
    <MemoryRouter initialEntries={[opts.route ?? '/']}>
      <SessionProvider deps={deps}>
        <App mock={deps.mock} />
      </SessionProvider>
    </MemoryRouter>,
  );
  return { ...utils, getApi: () => api };
}

/**
 * Run axe-core on the rendered DOM and return serious/critical violations.
 * jsdom has no layout or canvas, so axe cannot measure colour contrast here;
 * that one rule is switched off in unit tests and checked instead by running
 * axe in a real browser against `npm run preview` (see README).
 */
export async function seriousViolations(node: Element = document.body) {
  const res = await axe.run(node, { resultTypes: ['violations'], rules: { 'color-contrast': { enabled: false } } });
  return res.violations
    .filter((v) => v.impact === 'serious' || v.impact === 'critical')
    .map((v) => `${v.id} (${v.impact}): ${v.help} → ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`);
}

type User = ReturnType<typeof userEvent.setup>;

/**
 * Every screen the person can reach (D-016): the dock shows the Atlas places and the launcher
 * lists all of them, so this opens the launcher and returns it. In the Console view (sidebar)
 * it returns the sidebar instead.
 */
export async function screensNav(u: User, timeout = 4000) {
  const nav = await screen.findByRole('navigation', { name: 'Main' }, { timeout });
  const all = within(nav).queryByRole('button', { name: /screens and apps/ });
  if (!all) return within(nav);
  await u.click(all);
  return within(await screen.findByRole('dialog', { name: 'Launcher' }, { timeout }));
}

/** Open a screen the way a person would: from the dock, or from the launcher when it is not docked. */
export async function openScreen(u: User, name: string | RegExp) {
  const nav = await screen.findByRole('navigation', { name: 'Main' }, { timeout: 4000 });
  const docked = within(nav).queryAllByRole('link', { name });
  if (docked.length) return u.click(docked[0]!);
  const lp = await screensNav(u);
  await u.click(lp.getAllByRole('link', { name })[0]!);
}
