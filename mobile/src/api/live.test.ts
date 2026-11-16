// SPDX-License-Identifier: Apache-2.0
// MOB-LIVE-01: the phone's API client against a REAL gateway. Skipped unless ONEMIND_LIVE_HUB is set:
//   make -C core run   (or any hub)   then   ONEMIND_LIVE_HUB=http://127.0.0.1:8080 \
//   ONEMIND_LIVE_TOKEN=dev-owner-token-change-me npx jest src/api/live.test.ts
import { nodeFetch } from '../test/nodeFetch';
import { HttpApi, OP } from './client';
import type { CatalogApp } from './types';

const hub = process.env.ONEMIND_LIVE_HUB;
const token = process.env.ONEMIND_LIVE_TOKEN ?? 'dev-owner-token-change-me';
const d = hub ? describe : describe.skip;

d('phone client against a real hub', () => {
  const api = new HttpApi({ baseUrl: hub ?? 'http://x', token, fetchFn: nodeFetch });

  it('is healthy and lists its features before sign-in', async () => {
    expect((await api.healthz()).ok).toBe(true);
    const f = await api.features();
    expect(f.source).toBe('openapi');
    expect(f.has(OP.me)).toBe(true);
  });

  it('Home: instance, nodes, apps, actions answer in the shapes the screens read', async () => {
    const inst = await api.instance();
    expect(typeof inst.name).toBe('string');
    expect(Array.isArray(await api.nodes())).toBe(true);
    const apps = await api.apps();
    expect(Array.isArray(apps)).toBe(true);
    expect(Array.isArray(await api.actions())).toBe(true);
    for (const a of apps.slice(0, 5) as CatalogApp[]) {
      expect(typeof a.id).toBe('string');
      expect(typeof a.name).toBe('string');
    }
  });

  it('Settings: /v1/me says who is signed in', async () => {
    const me = await api.me();
    expect(me.principal.role).toBe('owner');
  });

  it('Alerts, notifications, backups, automation, files answer (or are cleanly absent)', async () => {
    const f = await api.features();
    if (f.has(OP.alerts)) expect(Array.isArray(await api.alerts('open'))).toBe(true);
    if (f.has(OP.notifications)) expect(Array.isArray(await api.notifications())).toBe(true);
    if (f.has(OP.backupStatus)) await api.backupStatus();
    if (f.has(OP.automationState)) await api.automationState();
  });

  it('Approvals: an install request is filed, shows up pending, and denies cleanly', async () => {
    const apps = await api.apps();
    const target = apps[0]!;
    const made = await api.createAction({
      type: 'app.install',
      params: { app_id: target.id },
      idempotency_key: `live-${Date.now()}`,
      expires_at: new Date(Date.now() + 3600_000).toISOString(),
    });
    expect(made.state).toBe('awaiting_approval');
    const listed = await api.actions();
    expect(listed.some((a) => a.id === made.id)).toBe(true);
    const denied = await api.deny(made.id, 'live test');
    expect(denied.state).toBe('cancelled');
  });
});
