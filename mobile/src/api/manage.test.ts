// SPDX-License-Identifier: Apache-2.0
// The box-management calls (§12.12, §12.17, §12.40, §12.41): path, method and body of each one.
import { HttpApi, OP, type FetchLike } from './client';
import { ApiError } from './types';

type Call = { url: string; init: RequestInit };

function api(status = 200, body: unknown = {}): { api: HttpApi; calls: Call[] } {
  const calls: Call[] = [];
  const fetchFn: FetchLike = async (url, init) => {
    calls.push({ url, init: init ?? {} });
    return new Response(JSON.stringify(body), { status });
  };
  return { api: new HttpApi({ baseUrl: 'https://hub.test', token: 't', fetchFn }), calls };
}
const bodyOf = (c: Call) => JSON.parse(String(c.init.body));
const header = (c: Call, k: string) => (c.init.headers as Record<string, string>)[k];

describe('first-run settings (§12.41)', () => {
  it('reads with GET and replaces with PUT', async () => {
    const r = api(200, { box_name: null, time_zone: null, backup_choice: 'later', backup_destination_id: null, saved: false });
    await expect(r.api.onboardingSettings()).resolves.toMatchObject({ saved: false });
    expect(r.calls[0]).toMatchObject({ url: 'https://hub.test/v1/onboarding/settings', init: { method: 'GET' } });
    const body = { box_name: 'home', time_zone: 'Europe/Berlin', backup_choice: 'usb' as const, backup_destination_id: 'dst_0123456789abcdef' };
    await r.api.saveOnboardingSettings(body);
    expect(r.calls[1]!.init.method).toBe('PUT');
    expect(bodyOf(r.calls[1]!)).toEqual(body);
  });

  it('a non-owner gets 403 permission_denied', async () => {
    const r = api(403, { error: 'permission_denied', message: 'owner only' });
    await expect(r.api.onboardingSettings()).rejects.toMatchObject({ code: 'permission_denied', status: 403 });
  });
});

describe('app lifecycle (§12.40)', () => {
  it('asks for the plan with the action type and files nothing', async () => {
    const r = api(200, { app_id: 'ollama', policy_verdict: 'needs_approval', plan: {}, plan_sha256: 'sha256:p' });
    await r.api.appPlan('ollama', 'app.restart');
    expect(r.calls[0]).toMatchObject({ url: 'https://hub.test/v1/apps/ollama/plan?type=app.restart', init: { method: 'GET' } });
  });

  it('encodes the app id', async () => {
    const r = api(200, { app_id: 'a', policy_verdict: 'needs_approval', plan: {}, plan_sha256: 'p' });
    await r.api.appPlan('a/b', 'app.stop');
    expect(r.calls[0]!.url).toBe('https://hub.test/v1/apps/a%2Fb/plan?type=app.stop');
  });
});

describe('backups (§12.12)', () => {
  it('reads status, destinations and runs', async () => {
    const s = api(200, { health: 'ok' });
    await s.api.backupStatus();
    expect(s.calls[0]!.url).toBe('https://hub.test/v1/backups/status');
    const l = api(200, []);
    await l.api.backupDestinations();
    await l.api.backupRuns();
    expect(l.calls.map((c) => c.url)).toEqual(['https://hub.test/v1/backups/destinations', 'https://hub.test/v1/backups/runs']);
  });

  it('a backup run is a request: approve is false and the idempotency key travels as a header', async () => {
    const r = api(202, { id: 'act-9', state: 'awaiting_approval' });
    await r.api.requestBackupRun({ reason: 'before the update', idempotencyKey: 'k-1' });
    const c = r.calls[0]!;
    expect(c).toMatchObject({ url: 'https://hub.test/v1/backups/runs', init: { method: 'POST' } });
    expect(bodyOf(c)).toEqual({ scope: 'box', reason: 'before the update', approve: false });
    expect(header(c, 'Idempotency-Key')).toBe('k-1');
  });

  it('a verify is a request too, never approving itself', async () => {
    const r = api(202, { id: 'act-10', state: 'awaiting_approval' });
    await r.api.requestBackupVerify({ idempotencyKey: 'k-2' });
    expect(bodyOf(r.calls[0]!)).toEqual({ approve: false });
    expect(r.calls[0]!.url).toBe('https://hub.test/v1/backups/verify');
  });
});

describe('automation (§12.17)', () => {
  it('reads state, rules and runs', async () => {
    const r = api(200, []);
    await r.api.automationRules();
    await r.api.automationRuns();
    expect(r.calls.map((c) => c.url)).toEqual(['https://hub.test/v1/automation/rules', 'https://hub.test/v1/automation/runs']);
    const s = api(200, { paused: false });
    await expect(s.api.automationState()).resolves.toEqual({ paused: false });
  });

  it('enable, disable, pause and resume are four different routes', async () => {
    const r = api(200, { id: 'r1', enabled: true });
    await r.api.setRuleEnabled('r1', true);
    await r.api.setRuleEnabled('r1', false);
    await r.api.setAutomationPaused(true, 'away');
    await r.api.setAutomationPaused(false);
    expect(r.calls.map((c) => c.url.replace('https://hub.test', ''))).toEqual([
      '/v1/automation/rules/r1/enable',
      '/v1/automation/rules/r1/disable',
      '/v1/automation/pause',
      '/v1/automation/resume',
    ]);
    expect(bodyOf(r.calls[2]!)).toEqual({ reason: 'away' });
  });
});

describe('files and migration (read only)', () => {
  it('lists roots and one folder, encoding root and path', async () => {
    const r = api(200, []);
    await r.api.filesRoots();
    await r.api.filesList('home:alex', '/Photos & more');
    expect(r.calls[0]!.url).toBe('https://hub.test/v1/files/roots');
    expect(r.calls[1]!.url).toBe('https://hub.test/v1/files/list?root=home%3Aalex&path=%2FPhotos%20%26%20more&limit=200');
  });

  it('lists migration plans', async () => {
    const r = api(200, []);
    await r.api.migratePlans();
    expect(r.calls[0]!.url).toBe('https://hub.test/v1/migrate/plans');
  });

  it('a 403 stays a typed permission error', async () => {
    const r = api(403, { error: 'permission_denied', message: 'no' });
    const e = await r.api.migratePlans().catch((x: unknown) => x);
    expect(e).toBeInstanceOf(ApiError);
  });
});

it('every new route is feature-detectable', () => {
  for (const op of [OP.onboardingSettings, OP.appPlan, OP.backupStatus, OP.backupRequestRun, OP.automationRules, OP.filesRoots, OP.migratePlans])
    expect(op).toMatch(/^(GET|POST) \/v1\//);
});
