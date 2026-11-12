// SPDX-License-Identifier: Apache-2.0
/**
 * Golden-path steps that depend on streams not merged yet. Each one checks whether its route is in
 * /openapi.json (contract §12 "Compatibility": a §12 route exists only once its module ships) or its
 * name is in GET /v1/instance `features` (§12.1), and is skipped with the reason until then. When a
 * stream lands, its step runs here without anyone editing the suite; the owning stream then deepens it.
 */
import { expect, test, type APIRequestContext } from '@playwright/test';
import { APPROVE_TIMEOUT_MS, hubEnv, type HubEnv } from '../lib/env';
import { Hub } from '../lib/hub';

test.describe.configure({ mode: 'serial' });

const env = hubEnv();
const E = env as HubEnv;
test.skip('missing' in env, 'missing' in env ? env.missing : '');

let paths = new Set<string>();
let features: string[] = [];

test.beforeAll(async ({ request }) => {
  const hub = new Hub(request, E.url, E.ownerToken);
  paths = await hub.openapiPaths();
  features = (await hub.get<{ features?: string[] }>('/v1/instance')).features ?? [];
});

function hubFor(request: APIRequestContext, token = E.ownerToken) {
  return new Hub(request, E.url, token);
}

test('open the installed app through the box app proxy', async ({ request }) => {
  test.skip(!features.includes('app-proxy'), 'not merged yet: mesh and app proxy (CORE-NET-P1, networking stream)');
  const hub = hubFor(request);
  await hub.requestAndApprove('app.install', E.app, APPROVE_TIMEOUT_MS);
  try {
    const row = (await hub.apps()).find((a) => a.id === E.app) as unknown as { url?: string; open_url?: string };
    const url = row.url ?? row.open_url;
    expect(url, 'an installed app has the URL the proxy serves it at').toBeTruthy();
    // Signed out, the hub edge must not hand out the app (§12.6 forward-auth: sign-in or 403).
    const anon = await request.get(url!, { maxRedirects: 0, ignoreHTTPSErrors: true });
    expect([302, 303, 307, 401, 403]).toContain(anon.status());
  } finally {
    await hub.requestAndApprove('app.remove', E.app, APPROVE_TIMEOUT_MS);
  }
});

test('GET /v1/me names the owner and the agent correctly (§12.6)', async ({ request }) => {
  test.skip(!paths.has('/v1/me'), 'not merged yet: identity, /v1/me and scopes (DEV-API-5, CORE-SEC-2)');
  const me = await hubFor(request).get<{ principal: { kind: string; role: string }; capabilities: string[] }>('/v1/me');
  expect(me.principal).toMatchObject({ kind: 'person', role: 'owner' });
  expect(me.capabilities).toContain('can_approve');
  if (E.agentToken) {
    const a = await hubFor(request, E.agentToken).get<{ principal: { kind: string }; capabilities: string[] }>('/v1/me');
    expect(a.principal.kind).toBe('agent');
    expect(a.capabilities).not.toContain('can_approve');
  }
});

test('passkey registration options are offered to the owner (§12.6)', async ({ request }) => {
  test.skip(
    !paths.has('/v1/auth/passkeys/register/options'),
    'not merged yet: owner passkeys and passkey-signed approvals (CORE-SEC-2, F-2); household accounts (CORE-SEC-10)',
  );
  const r = await hubFor(request).postAs(E.ownerToken, '/v1/auth/passkeys/register/options', {});
  expect(r.status).toBe(200);
  expect(JSON.stringify(r.body)).toContain('challenge');
});

test('the box CA is published for pairing (§12.7, F-1)', async ({ request }) => {
  test.skip(!paths.has('/v1/tls'), 'not merged yet: HTTPS with a per-box CA (CORE-SEC-1, F-1)');
  const tls = await hubFor(request).get<{ ca_sha256: string; names: string[] }>('/v1/tls');
  expect(tls.ca_sha256).toMatch(/^[0-9a-f]{64}$/);
  expect(tls.names).toContain('onemind.local');
});

test('the events stream answers with server-sent events (§12.8)', async () => {
  test.skip(!paths.has('/v1/events'), 'not merged yet: events stream over SSE (DEV-API-8)');
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), 20_000);
  try {
    const r = await fetch(`${E.url}/v1/events`, {
      headers: { Authorization: `Bearer ${E.ownerToken}`, Accept: 'text/event-stream' },
      signal: ctl.signal,
    });
    expect(r.status).toBe(200);
    expect(r.headers.get('content-type')).toContain('text/event-stream');
  } finally {
    clearTimeout(timer);
    ctl.abort();
  }
});

test('alerts are listed (§12.14)', async ({ request }) => {
  test.skip(!paths.has('/v1/alerts'), 'not merged yet: notifications and alerts (CORE-NOTIFY-1)');
  expect(Array.isArray(await hubFor(request).get<unknown[]>('/v1/alerts'))).toBe(true);
});

test('backup status is reported (§12.12)', async ({ request }) => {
  test.skip(!paths.has('/v1/backups/status'), 'not merged yet: backup agent and API (CORE-BACKUP-2, CORE-BACKUP-8)');
  await hubFor(request).get<unknown>('/v1/backups/status');
});
