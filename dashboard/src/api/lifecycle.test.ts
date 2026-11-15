// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it, vi } from 'vitest';
import { HttpApi, type FetchLike } from './client';

const preview = { plan: { summary: 'Restart the app.', objects: [], volumes: [], warnings: [] }, plan_sha256: 'sha256:reviewed', target: { kind: 'app', id: 'notes' } };

describe('gateway lifecycle reads', () => {
  it('reads the install plan and previews exact configure params without filing an action', async () => {
    const fetchFn = vi.fn<FetchLike>(async () => new Response(JSON.stringify(preview), { status: 200 }));
    const api = new HttpApi({ token: 'test-only', fetchFn });
    expect(await api.appPlan('notes')).toEqual(preview);
    expect(new URL(fetchFn.mock.calls[0]![0]).pathname).toBe('/v1/apps/notes/plan');
    await api.previewAction('app.configure', { app_id: 'notes', settings: { theme: 'dark' } });
    const [path, init] = fetchFn.mock.calls[1]!;
    expect(new URL(path).pathname).toBe('/v1/plans');
    expect(JSON.parse(init!.body as string)).toEqual({ type: 'app.configure', params: { app_id: 'notes', settings: { theme: 'dark' } } });
  });

  it('reads authenticated text logs but refuses an HTML fallback', async () => {
    const fetchFn = vi.fn<FetchLike>(async () => new Response('ready\n', { headers: { 'Content-Type': 'text/plain' } }));
    const api = new HttpApi({ token: 'test-only', fetchFn });
    expect(await api.appLogs('notes')).toBe('ready\n');
    expect(new URL(fetchFn.mock.calls[0]![0]).pathname + new URL(fetchFn.mock.calls[0]![0]).search).toBe('/v1/apps/notes/logs?tail=200');
    expect(fetchFn.mock.calls[0]?.[1]?.headers).toHaveProperty('Authorization');
    fetchFn.mockImplementation(async () => new Response('<html>fallback</html>', { headers: { 'Content-Type': 'text/html' } }));
    await expect(api.appLogs('notes')).rejects.toThrow('Unexpected response');
  });
});
