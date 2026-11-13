// SPDX-License-Identifier: Apache-2.0
// Every request HttpApi can make must be a route the hub serves: the committed OpenAPI document
// (sdk/openapi/onemind-v1.json, checked against the gateway by ci-sdk) is the reference.
import spec from '../../../sdk/openapi/onemind-v1.json';
import { HttpApi, type FetchLike } from './client';

/** Feature-detected routes the gateway does not ship yet (the phone hides what needs them). */
const NOT_YET = new Set([
  'GET /v1/actions/{}/preview', // plan_unchecked fallback; approve-options covers it
  'POST /v1/devices/requests', // device registry (clients.md §4.4)
  'GET /v1/devices/requests/{}',
  'POST /v1/devices/token',
]);

function served(): Set<string> {
  const out = new Set<string>();
  for (const [path, item] of Object.entries((spec as { paths: Record<string, object> }).paths))
    for (const m of Object.keys(item)) out.add(`${m.toUpperCase()} ${path.replace(/\{[^}]*\}/g, '{}')}`);
  return out;
}

it('calls only routes the hub serves (or feature-detected ones it does not ship yet)', async () => {
  const seen: string[] = [];
  const fn: FetchLike = async (url, init) => {
    const path = new URL(url).pathname.replace(/\/x1(?=\/|$)/g, '/{}');
    seen.push(`${init?.method ?? 'GET'} ${path}`);
    const list = /\/(nodes|apps|actions|notifications|alerts|registrations|destinations|runs|rules|roots|list|plans)$/.test(path) && init?.method !== 'POST';
    return new Response(JSON.stringify(list ? [] : { key: 'k', marked: 0 }), { status: 200 });
  };
  const api = new HttpApi({ baseUrl: 'https://hub.test', token: 't', fetchFn: fn });
  const id = 'x1';
  const calls: Array<() => Promise<unknown>> = [
    () => api.healthz(), () => api.instance(), () => api.nodes(), () => api.node(id), () => api.apps(),
    () => api.createAction({ type: 'app.install', params: {}, idempotency_key: 'k', expires_at: '' }),
    () => api.actions(), () => api.action(id), () => api.approve(id, { plan_sha256: 'p' }), () => api.deny(id),
    () => api.me(), () => api.approveOptions(id), () => api.preview(id), () => api.notifications(),
    () => api.notification(id), () => api.markRead(id), () => api.markAllRead(), () => api.alerts('open'),
    () => api.ackAlert(id), () => api.fixAlert(id),
    () => api.pushRegister({ platform: 'unifiedpush', endpoint: 'https://e', label: 'l' }),
    () => api.pushRegistrations(), () => api.pushUnregister(id), () => api.vapidPublicKey(), () => api.loginOptions(),
    () => api.login({ passkey: { id, clientDataJSON: '', authenticatorData: '', signature: '' }, client: 'app' }),
    () => api.refreshSession('r'), () => api.logout(), () => api.passkeyRegisterOptions(),
    () => api.passkeyRegister({ credential: { id, clientDataJSON: '', attestationObject: '' }, label: 'l' }),
    () => api.deviceRequest({ name: 'n', kind: 'phone', platform: 'ios', app_version: '', os_version: '', jwk: { kty: 'EC', crv: 'P-256', x: '', y: '' } }),
    () => api.deviceRequestStatus(id), () => api.deviceToken('proof', 'r'),
    () => api.onboardingSettings(), () => api.saveOnboardingSettings({ box_name: 'a', time_zone: 'UTC', backup_choice: 'later', backup_destination_id: null }),
    () => api.appPlan(id, 'app.restart'), () => api.backupStatus(), () => api.backupDestinations(), () => api.backupRuns(),
    () => api.requestBackupRun({ idempotencyKey: 'k' }), () => api.requestBackupVerify({ idempotencyKey: 'k' }),
    () => api.automationState(), () => api.automationRules(), () => api.automationRuns(),
    () => api.setRuleEnabled(id, true), () => api.setRuleEnabled(id, false), () => api.setAutomationPaused(true), () => api.setAutomationPaused(false),
    () => api.filesRoots(), () => api.filesList('r', '/'), () => api.migratePlans(),
  ];
  for (const c of calls) await c().catch(() => undefined);
  expect(seen).toHaveLength(calls.length);
  const ok = served();
  const missing = seen.filter((op) => !ok.has(op) && !NOT_YET.has(op));
  expect(missing).toEqual([]);
  // A route listed as not-yet that the hub now serves should be moved out of NOT_YET.
  expect([...NOT_YET].filter((op) => ok.has(op))).toEqual([]);
});
