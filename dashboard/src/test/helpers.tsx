// SPDX-License-Identifier: Apache-2.0
import { render } from '@testing-library/react';
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
  return Object.assign(new MockApi(token), {
    appPlan: (id: string) => preview('app.install', { app_id: id }), previewAction: preview,
    appSettings: async () => ({ fields: [], values: {} }), appLogs: async () => '',
  });
}

/**
 * Render the whole app on a route. With `token`, the user starts signed in.
 * One MockApi is shared for the whole test (so state changes are visible);
 * when the user signs in through the form, it is rebuilt for the typed token.
 */
export function renderApp(opts: { token?: string; route?: string; knownRole?: boolean } = {}) {
  let api = testApi(opts.token ?? '');
  if (opts.token) window.sessionStorage.setItem('onemind.token', opts.token);
  const deps: SessionDeps = {
    mock: true,
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
        <App mock />
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
