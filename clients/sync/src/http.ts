// SPDX-License-Identifier: Apache-2.0
// The plain HTTPS/JSON transport (docs/design/SYNC.md §2). Swappable: the client only sees Transport.
import { SyncHttpError } from './client.ts';
import type { Transport } from './types.ts';

export interface HttpOptions {
  baseUrl: string; // https://<box>:<port>, no trailing slash
  token: () => string | Promise<string>; // the person's gateway token or session bearer
  fetch?: typeof fetch;
}

export function httpTransport<R>(o: HttpOptions): Transport<R> {
  const f = o.fetch ?? fetch;
  async function call(path: string, init?: { method: string; body: string }) {
    const res = await f(o.baseUrl + path, {
      ...init, headers: { Authorization: `Bearer ${await o.token()}`, 'Content-Type': 'application/json' } });
    const body = await res.json().catch(() => null);
    if (!res.ok) throw new SyncHttpError(res.status, body?.reason ?? null, body?.message ?? `HTTP ${res.status}`);
    return { res, body };
  }
  return {
    async pull(app, cursor, limit) {
      const q = new URLSearchParams({ limit: String(limit), ...(cursor ? { cursor } : {}) });
      const { res, body } = await call(`/v1/sync/${app}/changes?${q}`);
      return { changes: body, more: /rel="next"/.test(res.headers.get('link') ?? '') };
    },
    async push(app, ops) {
      return (await call(`/v1/sync/${app}/push`, { method: 'POST', body: JSON.stringify({ ops }) })).body.results;
    },
  };
}
