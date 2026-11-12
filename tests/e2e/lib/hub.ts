// SPDX-License-Identifier: Apache-2.0
/** Thin REST helpers over contract §3 (used to set up, cross-check and clean up, never to replace the UI). */
import { randomUUID } from 'node:crypto';
import { expect, type APIRequestContext } from '@playwright/test';

export interface Action {
  id: string;
  type: string;
  state: string;
  params: { app_id: string };
  requested_by?: { id: string; kind: string };
}
export interface CatalogApp {
  id: string;
  name: string;
  installed: boolean;
  status: string;
  scan?: { scanned_at: string; result: string } | null;
}
export interface NodeRecord {
  node_id: string;
  hostname: string;
  role: string;
  status: string;
}

export class Hub {
  constructor(
    private readonly request: APIRequestContext,
    readonly url: string,
    private readonly token: string,
  ) {}

  private headers(token = this.token) {
    return { Authorization: `Bearer ${token}` };
  }

  async get<T>(path: string): Promise<T> {
    const r = await this.request.get(`${this.url}${path}`, { headers: this.headers() });
    expect(r.status(), `GET ${path}`).toBe(200);
    return (await r.json()) as T;
  }

  nodes = () => this.get<NodeRecord[]>('/v1/nodes');
  apps = () => this.get<CatalogApp[]>('/v1/apps');
  actions = () => this.get<Action[]>('/v1/actions');

  async app(id: string): Promise<CatalogApp> {
    const a = (await this.apps()).find((x) => x.id === id);
    expect(a, `app ${id} in the catalog`).toBeDefined();
    return a!;
  }

  /** Request and approve in one go (setup and cleanup only). */
  async requestAndApprove(type: 'app.install' | 'app.remove', appId: string, timeout: number): Promise<Action> {
    const created = await this.request.post(`${this.url}/v1/actions`, {
      headers: this.headers(),
      data: {
        type,
        params: { app_id: appId },
        idempotency_key: randomUUID(),
        expires_at: new Date(Date.now() + 3_600_000).toISOString(),
      },
    });
    expect([200, 201], `create ${type}`).toContain(created.status());
    const a = (await created.json()) as Action;
    const approved = await this.request.post(`${this.url}/v1/actions/${encodeURIComponent(a.id)}/approve`, {
      headers: this.headers(),
      timeout,
    });
    expect(approved.status(), `approve ${type}`).toBe(200);
    return (await approved.json()) as Action;
  }

  /** POST with another principal's token; returns status and body. */
  async postAs(token: string, path: string, data?: unknown) {
    const r = await this.request.post(`${this.url}${path}`, { headers: this.headers(token), data });
    let body: unknown;
    try {
      body = await r.json();
    } catch {
      body = undefined;
    }
    return { status: r.status(), body: body as { error?: string } | undefined };
  }

  /** Paths in /openapi.json: a §12 route exists only once its module ships (§12 "Compatibility"). */
  async openapiPaths(): Promise<Set<string>> {
    const r = await this.request.get(`${this.url}/openapi.json`);
    expect(r.status()).toBe(200);
    const doc = (await r.json()) as { paths?: Record<string, unknown> };
    return new Set(Object.keys(doc.paths ?? {}));
  }
}
