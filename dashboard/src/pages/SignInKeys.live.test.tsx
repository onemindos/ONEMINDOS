// SPDX-License-Identifier: Apache-2.0
// Mounts the whole app with no role on the session (a real gateway): the role comes from the shell's GET /v1/me (Refs #1284).
import { screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { MockApi } from '../api/mock';
import { renderApp } from '../test/helpers';

const phone = { credential_id: 'phone', label: 'iPhone', created_at: '2026-11-20T10:00:00Z', last_used_at: null, level: 'L1',
  level_reason: 'no_attestation', explanation: 'A device check key.', model: null, aaguid: null, attestation: 'none', device_bound: false, synced: true };
const table = { rows: [], types: [], household_level: 'L1', grace: true, recovery_needed: false, box_confirm: true };

function gateway() {
  const paths: string[] = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const path = new URL(url, 'http://hub.test').pathname;
    paths.push(path);
    const body: Record<string, unknown> = { '/v1/auth/passkeys': [phone], '/v1/verification-requirements': table, '/v1/auth/authenticator-allowlist': [] };
    return path in body ? Response.json(body[path]) : Response.json({ error: 'not_found', message: 'no' }, { status: 404 });
  }));
  return paths;
}
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); window.sessionStorage.clear(); });

const open = (token: string) => renderApp({ token, mock: false, knownRole: false, route: '/settings/sign-in-keys' });
const T = { timeout: 5000 };

it('an owner sees the trusted key models and their tables are requested', async () => {
  const paths = gateway();
  open('owner-demo');
  expect(await screen.findByText('Trusted key models', {}, T)).toBeVisible();
  await waitFor(() => { expect(paths).toContain('/v1/auth/authenticator-allowlist'); expect(paths).toContain('/v1/verification-requirements'); }, T);
});

it('an adult sees no trusted key models and neither owner path is requested', async () => {
  const paths = gateway();
  open('adult-demo');
  expect(await screen.findByText('L1 · Device check', {}, T)).toBeVisible();
  expect(screen.queryByText('Trusted key models')).toBeNull();
  expect(paths).not.toContain('/v1/auth/authenticator-allowlist');
  expect(paths).not.toContain('/v1/verification-requirements');
});

it('an owner whose GET /v1/me answers after the page mounted still gets the table and the grace hint', async () => {
  const paths = gateway();
  const real = MockApi.prototype.me;
  vi.spyOn(MockApi.prototype, 'me').mockImplementation(async function (this: MockApi) {
    await new Promise((r) => setTimeout(r, 600));
    return real.call(this);
  });
  open('owner-demo');
  expect(await screen.findByText(/accept a Device check key plus the code on the box's own screen/, {}, T)).toBeVisible();
  expect(paths).toContain('/v1/verification-requirements');
});
