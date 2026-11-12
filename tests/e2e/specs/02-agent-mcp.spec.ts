// SPDX-License-Identifier: Apache-2.0
/**
 * Golden path, agent side (contract §7, §11.3): an AI agent connects to /mcp with the official
 * MCP TypeScript client, requests an install, and cannot approve it; the owner approves it in the
 * dashboard. The agent then asks for the removal and the owner approves that too.
 */
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import { expect, test } from '@playwright/test';
import { APPROVE_TIMEOUT_MS, hubEnv, type HubEnv } from '../lib/env';
import { Hub } from '../lib/hub';
import { approveOnScreen, signIn } from '../lib/session';

test.describe.configure({ mode: 'serial' });

const env = hubEnv();
const E = env as HubEnv;
test.skip('missing' in env, 'missing' in env ? env.missing : '');
test.skip(!('missing' in env) && !E.agentToken, 'E2E_AGENT_TOKEN_FILE is not set: no agent principal on this hub');

async function connect(token: string): Promise<Client> {
  const client = new Client({ name: 'onemind-e2e-agent', version: '0.1.0' });
  const transport = new StreamableHTTPClientTransport(new URL('/mcp', E.url), {
    requestInit: { headers: { Authorization: `Bearer ${token}` } },
  });
  await client.connect(transport);
  return client;
}

interface RequestResult {
  action_id: string;
  state: string;
}

async function agentRequests(type: 'app.install' | 'app.remove', reason: string): Promise<RequestResult> {
  const client = await connect(E.agentToken!);
  try {
    const res = await client.callTool({ name: 'request_action', arguments: { type, app_id: E.app, reason } });
    expect(res.isError, JSON.stringify(res.content)).toBeFalsy();
    return res.structuredContent as unknown as RequestResult;
  } finally {
    await client.close();
  }
}

test.beforeAll(async ({ request }) => {
  const hub = new Hub(request, E.url, E.ownerToken);
  if ((await hub.app(E.app)).installed) await hub.requestAndApprove('app.remove', E.app, APPROVE_TIMEOUT_MS);
});

test('the agent sees the read tools and request_action, and no approve tool', async () => {
  const client = await connect(E.agentToken!);
  try {
    expect(client.getServerVersion()?.name).toBeTruthy();
    const names = (await client.listTools()).tools.map((t) => t.name).sort();
    expect(names).toEqual(expect.arrayContaining(['list_apps', 'list_nodes', 'request_action']));
    expect(names.filter((n) => /approve|deny|grant|token|policy/.test(n))).toEqual([]);
    const nodes = await client.callTool({ name: 'list_nodes', arguments: {} });
    expect((nodes.structuredContent as { nodes: unknown[] }).nodes.length).toBeGreaterThan(0);
    const apps = await client.callTool({ name: 'list_apps', arguments: {} });
    expect((apps.structuredContent as { apps: { id: string }[] }).apps.map((a) => a.id)).toContain(E.app);
  } finally {
    await client.close();
  }
});

test('a person token is refused on /mcp', async ({ request }) => {
  const r = await request.post(`${E.url}/mcp`, {
    headers: { Authorization: `Bearer ${E.ownerToken}`, Accept: 'application/json, text/event-stream' },
    data: { jsonrpc: '2.0', id: 1, method: 'tools/list' },
  });
  expect(r.status()).toBe(403);
  expect((await r.json()).error).toBe('permission_denied');
});

test('the agent requests an install over MCP; it cannot approve; the owner approves', async ({ page, request }) => {
  const hub = new Hub(request, E.url, E.ownerToken);
  const req = await agentRequests('app.install', `golden-path e2e: the agent asks for ${E.app}`);
  expect(req.state).toBe('awaiting_approval');

  // The agent cannot approve its own request over REST either (§3, §11.3).
  const self = await hub.postAs(E.agentToken!, `/v1/actions/${req.action_id}/approve`);
  expect(self.status).toBe(403);
  expect(self.body?.error).toBe('permission_denied');

  await signIn(page, E.ownerToken);
  await page.goto(`/approvals?highlight=${req.action_id}`);
  const card = page.getByRole('article', { name: `Install ${E.app}` }).filter({ hasText: 'awaiting approval' });
  await expect(card).toContainText('AI agent');
  await expect(card).toContainText(E.agentId);
  expect(await approveOnScreen(page, `Install ${E.app}`, APPROVE_TIMEOUT_MS)).toBe(`Install ${E.app}: succeeded.`);

  const done = await hub.get<{ state: string; requested_by: { id: string; kind: string } }>(`/v1/actions/${req.action_id}`);
  expect(done.state).toBe('succeeded');
  expect(done.requested_by).toMatchObject({ id: E.agentId, kind: 'agent' });
  expect((await hub.app(E.app)).installed).toBe(true);
});

test('the agent requests the removal; the owner approves it', async ({ page, request }) => {
  const hub = new Hub(request, E.url, E.ownerToken);
  const req = await agentRequests('app.remove', 'golden-path e2e: clean up');
  expect(req.state).toBe('awaiting_approval');

  await signIn(page, E.ownerToken);
  await page.goto(`/approvals?highlight=${req.action_id}`);
  expect(await approveOnScreen(page, `Remove ${E.app}`, APPROVE_TIMEOUT_MS)).toBe(`Remove ${E.app}: succeeded.`);
  expect((await hub.app(E.app)).installed).toBe(false);
});
