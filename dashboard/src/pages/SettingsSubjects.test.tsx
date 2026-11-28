// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { App } from '../App';
import { DEMO_TOKENS } from '../api/fixtures';
import { MockApi } from '../api/mock';
import { SessionProvider } from '../session';

const json = (v: unknown, status = 200) => new Response(JSON.stringify(v), { status, headers: { 'content-type': 'application/json' } });
const tree = {
  version: '1', root: 'om', grammar: 'om.<kind>.<scope>',
  kinds: [{ kind: 'sensor', description: 'Readings from devices.', core: true, stream: 'SENSORS', envelope: 'datapoint', retention: { policy: 'limits', max_age_s: 86400 },
    subjects: [{ pattern: 'om.sensor.>', publishers: ['node', 'app'], owner: null, stream: 'SENSORS', retention: { policy: 'limits' }, envelope: 'datapoint' }] }],
  reserved: [{ kind: 'secret', reason: 'never on the bus' }], envelopes: [], mappings: [],
};

function mount(check: () => Response = () => json({ subject: 'om.sensor.x', publisher: 'app', ok: true, reason: 'allowed by om.sensor.>', kind: 'sensor', pattern: 'om.sensor.>' }), body: unknown = tree) {
  const calls: string[] = [];
  const treeNow = body;
  vi.stubGlobal('fetch', vi.fn(async (url: string | URL | Request) => {
    const u = new URL(String(url));
    calls.push(u.pathname + u.search);
    if (u.pathname === '/v1/subjects') return json(treeNow);
    if (u.pathname === '/v1/subjects/check') return check();
    if (u.pathname === '/v1/instance') return json({ name: 'Box', version: '0.1.0', hub_node_id: 'n' });
    return json({ error: 'not_found', message: u.pathname }, 404);
  }));
  window.sessionStorage.setItem('onemind.token', 'owner-demo');
  render(<MemoryRouter initialEntries={['/settings/about']}><SessionProvider deps={{ mock: false, makeApi: () => new MockApi('owner-demo'), knownPrincipal: () => DEMO_TOKENS['owner-demo'] }}><App mock={false} /></SessionProvider></MemoryRouter>);
  return calls;
}
afterEach(() => { vi.unstubAllGlobals(); window.sessionStorage.clear(); });

it('lists the message kinds with who may send and how long they are kept', async () => {
  mount();
  const card = within(await screen.findByRole('article', { name: 'Message subjects' }));
  await userEvent.setup().click(card.getByText('Who may send which messages (technical)'));
  const kinds = within(await card.findByRole('list', { name: 'Message kinds' }));
  expect(kinds.getByText(/Readings from devices/)).toBeInTheDocument();
  expect(kinds.getByText(/up to 24 h/)).toBeInTheDocument();
  expect(kinds.getByText(/May send: node, app/)).toBeInTheDocument();
  expect(card.getByText(/Reserved: secret/)).toBeInTheDocument();
});

it('asks the gateway whether a sender may use a subject, and only asks', async () => {
  const calls = mount();
  const u = userEvent.setup();
  const card = within(await screen.findByRole('article', { name: 'Message subjects' }));
  await u.click(card.getByText('Who may send which messages (technical)'));
  const check = card.getByRole('button', { name: 'Check' });
  expect(check).toBeDisabled();
  await u.type(card.getByLabelText('Subject to check'), 'om.sensor.x');
  await u.selectOptions(card.getByLabelText('Sender'), 'agent');
  await u.click(check);
  expect(await card.findByText(/Allowed: allowed by om.sensor/)).toBeInTheDocument();
  await waitFor(() => expect(calls).toContain('/v1/subjects/check?subject=om.sensor.x&publisher=agent'));
});

it('says not allowed with the reason', async () => {
  mount(() => json({ subject: 'x', publisher: 'app', ok: false, reason: 'apps may not send on om.node', kind: null, pattern: null }));
  const u = userEvent.setup();
  const card = within(await screen.findByRole('article', { name: 'Message subjects' }));
  await u.click(card.getByText('Who may send which messages (technical)'));
  await u.type(card.getByLabelText('Subject to check'), 'om.node.x');
  await u.click(card.getByRole('button', { name: 'Check' }));
  expect(await card.findByText(/Not allowed: apps may not send on om.node/)).toBeInTheDocument();
});

it('shows minutes for a kind kept under an hour, and days for a long one, never "0 h"', async () => {
  const kind = tree.kinds[0]!;
  mount(undefined, { ...tree, kinds: [
    { ...kind, kind: 'event', description: 'Short.', retention: { policy: 'limits', max_age_s: 1800 } },
    { ...kind, kind: 'log', description: 'Long.', retention: { policy: 'limits', max_age_s: 7 * 86400 } },
  ] });
  const card = within(await screen.findByRole('article', { name: 'Message subjects' }));
  await userEvent.setup().click(card.getByText('Who may send which messages (technical)'));
  const kinds = within(await card.findByRole('list', { name: 'Message kinds' }));
  expect(kinds.getByText(/up to 30 min/)).toBeInTheDocument();
  expect(kinds.getByText(/up to 7 days/)).toBeInTheDocument();
  expect(kinds.queryByText(/up to 0 h/)).not.toBeInTheDocument();
});
