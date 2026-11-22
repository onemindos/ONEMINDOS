// SPDX-License-Identifier: Apache-2.0
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';
import { renderApp, seriousViolations } from '../test/helpers';
import { parseLogs, levelOf } from '../data/logs';
import type { SecretsChangeBody } from '../api/client';

const T = { timeout: 4000 };
const b64u = (b: Uint8Array) => btoa(String.fromCharCode(...b)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
const subtle = globalThis.crypto.subtle;

async function boxKey() {
  const pair = (await subtle.generateKey({ name: 'X25519' }, true, ['deriveBits'])) as CryptoKeyPair;
  return b64u(new Uint8Array(await subtle.exportKey('raw', pair.publicKey)));
}
const declared = (id: string) => ({
  app_id: id,
  key_id: 'box-1',
  missing_required: [],
  secrets: [{ name: 'app-env', description: 'Settings', keys: [{ key: 'API_KEY', kind: 'api-key', description: 'The key', required: false, source: 'owner', set: false, version: null, updated_at: null }] }],
});

it('Secrets: seals a typed value in the browser and files an approval request, never a direct write', async () => {
  const u = userEvent.setup();
  const view = renderApp({ token: 'owner-demo', route: '/control-hub?tab=secrets' });
  const api = view.getApi();
  const pub = await boxKey();
  const sent: Array<{ id: string; body: SecretsChangeBody; key: { idempotency_key: string; expires_at: string } }> = [];
  Object.assign(api, {
    appSecrets: async (id: string) => declared(id),
    secretsPublicKey: async () => ({ alg: 'X25519', key: pub, key_id: 'box-1', sealed_alg: 'X25519-AES256GCM' }),
    requestSecretsChange: vi.fn(async (id: string, body: SecretsChangeBody, key: { idempotency_key: string; expires_at: string }) => {
      sent.push({ id, body, key });
      return { id: 'act-secret-1', type: 'app.configure', state: 'awaiting_approval', params: { app_id: id }, idempotency_key: key.idempotency_key, expires_at: key.expires_at };
    }),
  });
  const field = await screen.findByLabelText('API_KEY', undefined, T);
  expect(field).toHaveAttribute('type', 'password');
  expect(await seriousViolations(view.container)).toEqual([]);
  await u.type(field, 'sk-plaintext-value-123');
  await u.click(screen.getByRole('button', { name: 'Request change' }));
  await waitFor(() => expect(sent).toHaveLength(1), T);
  const json = JSON.stringify(sent[0]);
  expect(json).not.toContain('sk-plaintext-value-123');
  expect(sent[0]!.body.sealed).toMatchObject({ alg: 'X25519-AES256GCM', kid: 'box-1' });
  expect(sent[0]!.body.sealed?.ct.length).toBeGreaterThan(20);
  expect(sent[0]!.key.idempotency_key).toBeTruthy();
  // The request lands on Approvals: no write happened without an owner decision.
  expect(await screen.findByRole('heading', { level: 1, name: /Approvals/ }, T)).toBeInTheDocument();
}, 20000);

it('Secrets: a person who is not an owner gets a plain note instead of the form', async () => {
  const view = renderApp({ token: 'adult-demo', route: '/control-hub?tab=secrets' });
  Object.assign(view.getApi(), { appSecrets: async (id: string) => declared(id) });
  expect(await screen.findByText(/Only an owner can change secrets/, undefined, T)).toBeInTheDocument();
  expect(screen.queryByLabelText('API_KEY')).toBeNull();
});

it('Secrets: says so when the app declares none', async () => {
  const view = renderApp({ token: 'owner-demo', route: '/control-hub?tab=secrets' });
  Object.assign(view.getApi(), { appSecrets: async (id: string) => ({ app_id: id, key_id: 'box-1', missing_required: [], secrets: [] }) });
  expect(await screen.findByText(/declares no secrets/, undefined, T)).toBeInTheDocument();
});

it('Logs: shows the hub lines in the shared log viewer and says when the times are the read time', async () => {
  const u = userEvent.setup();
  const view = renderApp({ token: 'owner-demo', route: '/control-hub?tab=logs' });
  Object.assign(view.getApi(), { appLogs: async () => 'started ok\nERROR could not reach db\n' });
  const log = await screen.findByRole('log', undefined, T);
  expect(within(log).getByText('could not reach db', { exact: false })).toBeInTheDocument();
  expect(screen.getByText(/does not time-stamp every line/)).toBeInTheDocument();
  await u.click(screen.getByRole('tab', { name: 'Overview' }));
  expect(await screen.findByRole('table', { name: 'Machines' }, T)).toBeInTheDocument();
});

it('parseLogs reads a leading time and a level only when the line says one', () => {
  const at = new Date('2026-11-21T10:00:00Z');
  const { lines, untimed } = parseLogs('2026-11-21T09:59:00Z WARN disk almost full\nplain line\n\n', at);
  expect(lines).toEqual([
    { at: '2026-11-21T09:59:00.000Z', level: 'warn', text: 'WARN disk almost full' },
    { at: at.toISOString(), level: 'info', text: 'plain line' },
  ]);
  expect(untimed).toBe(1);
  expect(levelOf('request failed')).toBe('error');
  expect(levelOf('all good')).toBe('info');
});
