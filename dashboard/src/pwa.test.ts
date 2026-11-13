// SPDX-License-Identifier: Apache-2.0
// public/sw.js: static files and the shell only. API answers, authenticated requests, other
// origins and non-GET requests are never touched, never cached.
import { describe, expect, it } from 'vitest';

import SRC from '../public/sw.js?raw';

interface Ev {
  request: { method: string; url: string; mode: string; headers: Headers };
  responded: boolean;
  respondWith(p: Promise<unknown>): void;
}

function boot() {
  const listeners: Record<string, (e: unknown) => void> = {};
  const puts: string[] = [];
  const store = new Map<string, unknown>();
  const cache = { put: async (k: unknown, v: unknown) => void (puts.push(typeof k === 'string' ? k : (k as { url: string }).url), store.set(typeof k === 'string' ? k : (k as { url: string }).url, v)) };
  const caches = { open: async () => cache, match: async (k: unknown) => store.get(typeof k === 'string' ? k : (k as { url: string }).url), keys: async () => [], delete: async () => true };
  const fetched: string[] = [];
  const fetchFn = async (r: { url: string }) => {
    fetched.push(r.url);
    return { ok: true, type: 'basic', clone() { return this; } };
  };
  const self = { location: { origin: 'https://box.local' }, addEventListener: (n: string, f: (e: unknown) => void) => void (listeners[n] = f), skipWaiting() {}, clients: { claim() {} } };
  new Function('self', 'caches', 'fetch', 'URL', 'Response', SRC)(self, caches, fetchFn, URL, { error: () => 'err' });
  const fire = (url: string, o: { method?: string; mode?: string; headers?: Record<string, string> } = {}) => {
    const ev: Ev = { request: { method: o.method ?? 'GET', url, mode: o.mode ?? 'cors', headers: new Headers(o.headers) }, responded: false, respondWith(p) { this.responded = true; void p; } };
    listeners.fetch!(ev);
    return ev.responded;
  };
  return { fire, puts, fetched };
}

describe('service worker', () => {
  it('never handles the API, health, MCP or OpenAPI paths', () => {
    const { fire } = boot();
    for (const p of ['/v1/actions', '/v1/me', '/v1/notifications?limit=100', '/healthz', '/mcp', '/openapi.json']) expect(fire(`https://box.local${p}`)).toBe(false);
  });

  it('never handles requests with credentials, other origins or non-GET', () => {
    const { fire } = boot();
    expect(fire('https://box.local/assets/app.js', { headers: { Authorization: 'Bearer x' } })).toBe(false);
    expect(fire('https://evil.example/assets/app.js')).toBe(false);
    expect(fire('https://box.local/assets/app.js', { method: 'POST' })).toBe(false);
    expect(fire('https://box.local/v1/actions', { mode: 'navigate' })).toBe(false);
  });

  it('handles static assets and navigations, and caches only those', async () => {
    const { fire, puts } = boot();
    expect(fire('https://box.local/assets/app-123.js')).toBe(true);
    expect(fire('https://box.local/brand/favicon.svg')).toBe(true);
    expect(fire('https://box.local/approvals', { mode: 'navigate' })).toBe(true);
    await new Promise((r) => setTimeout(r, 10));
    expect(puts.every((u) => !u.includes('/v1/'))).toBe(true);
    expect(puts.length).toBeGreaterThan(0);
  });
});
