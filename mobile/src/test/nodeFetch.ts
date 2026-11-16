// SPDX-License-Identifier: Apache-2.0
// React Native's jest preset replaces global fetch with a stub, so live tests speak HTTP with Node itself.
// (No @types/node in this package: the few Node pieces used are typed here.)
import type { FetchLike } from '../api/client';

interface NodeRes {
  statusCode?: number;
  headers: Record<string, string | string[] | undefined>;
  on(ev: string, fn: (arg?: unknown) => void): void;
}
interface NodeReq {
  on(ev: string, fn: (arg: unknown) => void): void;
  write(s: string): void;
  end(): void;
}
type HttpRequest = (url: string, opts: { method?: string; headers?: Record<string, string> }, cb: (res: NodeRes) => void) => NodeReq;

export const nodeFetch: FetchLike = (url, init) =>
  new Promise((resolve, reject) => {
    const { request } = jest.requireActual<{ request: HttpRequest }>('http');
    const req = request(url, { method: init?.method, headers: init?.headers as Record<string, string> }, (res) => {
      const chunks: string[] = [];
      res.on('data', (c) => chunks.push(String(c)));
      res.on('end', () => {
        const h = new Headers();
        for (const [k, v] of Object.entries(res.headers)) if (v !== undefined) h.set(k, Array.isArray(v) ? v.join(', ') : v);
        const text = chunks.join('');
        const status = res.statusCode ?? 0;
        resolve({ status, ok: status >= 200 && status < 300, headers: h, text: async () => text } as unknown as Response);
      });
    });
    req.on('error', (e) => reject(e));
    if (init?.body) req.write(init.body as string);
    req.end();
  });
