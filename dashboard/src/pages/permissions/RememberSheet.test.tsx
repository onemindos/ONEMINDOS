// SPDX-License-Identifier: Apache-2.0
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import type { ActionSummary } from '@onemind/ui';
import { RememberSheet } from './RememberSheet';

vi.mock('../../session', () => ({
  useSession: () => ({ signOut: vi.fn() }),
  useSignedIn: () => ({ token: 'owner-session', signIn: vi.fn(), api: { logout: vi.fn() }, anon: {} }),
}));
vi.mock('../../lib/webauthn', () => ({ webauthnSupported: () => true, getPasskey: vi.fn() }));

const action: ActionSummary = { id: 'act_1', type: 'notes.read', params: { vault: 'home', folder: 'inbox' }, state: 'awaiting_approval',
  expires_at: '2099-01-01T00:00:00Z', requested_by: { id: 'agent:reader', kind: 'agent' } };
const rule = { allow: { types: ['notes.read'], requested_by: ['agent:reader'], params: { vault: { const: 'home' } } }, limits: { per_day: 10 } };
type Call = { path: string; body: Record<string, unknown> };
let calls: Call[] = [];
let refuse: string | undefined;

beforeEach(() => {
  calls = [];
  refuse = undefined;
  vi.stubGlobal('fetch', vi.fn(async (url: string, init: RequestInit) => {
    const call = { path: new URL(url).pathname, body: JSON.parse(String(init.body ?? '{}')) };
    calls.push(call);
    if (call.path.endsWith('/approve-options')) {
      if (refuse) return Response.json({ error: 'conflict', message: 'no', reason: refuse }, { status: 409 });
      return Response.json({ challenge: 'c1', action_sha256: 'a', plan_sha256: 'sha256:plan', expires_at: '2099-01-01T00:00:00Z', device_payload: '',
        publicKey: { challenge: 'abc' }, remember: { rule, rule_sha256: 'sha256:rule', summary: 'agent:reader may notes.read for vault = home, up to 10 a day, until 2026-12-26.', required_level: 'L1' } });
    }
    return Response.json({ id: 'act_1', state: 'succeeded', remembered_policy: 'pol_new' });
  }));
});
afterEach(() => vi.unstubAllGlobals());

it('shows the rule the gateway wrote, then signs exactly that rule with the passkey', async () => {
  const sign = vi.fn(async () => ({ id: 'cred' }));
  const onDone = vi.fn();
  render(<RememberSheet action={action} onClose={vi.fn()} onDone={onDone} sign={sign} />);
  const user = userEvent.setup();
  await user.click(screen.getByLabelText('folder = inbox')); // allow any folder
  await user.click(screen.getByRole('button', { name: 'Show the rule' }));
  expect(await screen.findByText(/agent:reader may notes.read for vault = home/)).toBeVisible();
  expect(calls[0]).toEqual({ path: '/v1/actions/act_1/approve-options',
    body: { remember: { lifetime: '30d', lapse_unused: true, per_day: 10, notify_after: 'digest', unpin: ['folder'] } } });
  await user.click(screen.getByRole('button', { name: 'Approve and remember with passkey' }));
  expect(onDone).toHaveBeenCalledWith('pol_new');
  expect(sign).toHaveBeenCalledWith({ challenge: 'abc' });
  expect(calls[1]).toEqual({ path: '/v1/actions/act_1/approve', body: { webauthn: { id: 'cred' }, remember: { rule }, plan_sha256: 'sha256:plan' } });
});

it('a changed choice needs a new rule before the passkey, and Forever says it never ends', async () => {
  render(<RememberSheet action={action} onClose={vi.fn()} onDone={vi.fn()} sign={vi.fn()} />);
  const user = userEvent.setup();
  await user.click(screen.getByRole('button', { name: 'Show the rule' }));
  await screen.findByRole('button', { name: 'Approve and remember with passkey' });
  await user.click(screen.getByLabelText('Forever'));
  expect(screen.getByText(/This rule never ends by itself/)).toBeVisible();
  expect(screen.queryByRole('button', { name: 'Approve and remember with passkey' })).toBeNull();
  expect(screen.getByRole('button', { name: 'Show the rule' })).toBeVisible();
});

it('says in plain words why the gateway refused to remember', async () => {
  refuse = 'needs_proven_key';
  render(<RememberSheet action={action} onClose={vi.fn()} onDone={vi.fn()} sign={vi.fn()} />);
  await userEvent.setup().click(screen.getByRole('button', { name: 'Show the rule' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('needs a proven hardware key');
});

it('lets the daily limit be typed freely, then keeps it between 1 and 1000', async () => {
  render(<RememberSheet action={action} onClose={vi.fn()} onDone={vi.fn()} sign={vi.fn()} />);
  const user = userEvent.setup();
  const box = screen.getByLabelText(/At most this many a day/);
  await user.clear(box);
  await user.type(box, '25');
  expect(box).toHaveValue(25); // not 1, then 12
  await user.click(screen.getByRole('button', { name: 'Show the rule' }));
  await screen.findByRole('button', { name: 'Approve and remember with passkey' });
  expect(calls[0]!.body).toEqual({ remember: expect.objectContaining({ per_day: 25 }) });
  await user.clear(box);
  expect(screen.queryByRole('button', { name: 'Approve and remember with passkey' })).toBeNull(); // typing drops the old rule
  await user.type(box, '5000');
  await user.tab();
  expect(box).toHaveValue(1000);
  await user.clear(box);
  await user.tab();
  expect(box).toHaveValue(1);
  await user.click(screen.getByRole('button', { name: 'Show the rule' }));
  await screen.findByRole('button', { name: 'Approve and remember with passkey' });
  expect(calls.at(-1)!.body).toEqual({ remember: expect.objectContaining({ per_day: 1 }) });
});
