// SPDX-License-Identifier: Apache-2.0
import type { components } from '@onemind/sdk';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { App } from '../App';
import { DEMO_TOKENS } from '../api/fixtures';
import { MockApi } from '../api/mock';
import { SessionProvider } from '../session';

type Tip = components['schemas']['TipView'];

const market: Tip = {
  id: 'find-an-app',
  title: 'Find an app',
  collection: 'apps',
  body: 'Review permissions before requesting an install.',
  opens: { dashboard: '/market', phone: 'onemind://apps' },
  skip_if_done: [],
  clip: { release: 'tip-find-an-app', caption: 'Open the Market.' },
  state: 'new',
  state_updated_at: null,
};
const backup: Tip = {
  ...market, id: 'check-backups', title: 'Check backups', body: 'Review your restore history.',
  collection: 'start', opens: { dashboard: '/backups', phone: 'onemind://backups' }, clip: null, state: 'done',
};

function mount(route: string, tip = market) {
  const fetch = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    const request = new URL(String(url));
    const path = request.pathname;
    if (path.startsWith('/v1/tips')) expect(init?.redirect).toBe('error');
    switch (path) {
      case '/v1/search':
        return Response.json(request.searchParams.get('q') === 'backup' && request.searchParams.get('types') === 'tip'
          ? [{ id: backup.id, title: backup.title, provider: 'tips', app_id: 'tips', type: 'tip', link: `onemind://app/tips/${backup.id}` }]
          : []);
      case '/v1/tips':
        return Response.json({ pack: { version: '0.1.0', source: 'image' }, tips: [market, backup] });
      case '/v1/tips/collections':
        return Response.json({
          collections: [{ id: 'apps', title: 'Apps', count: 1 }, { id: 'start', title: 'Getting started', count: 1 }],
          checklist: [backup.id],
        });
      case '/v1/auth/passkeys':
        return Response.json([{ id: 'key-1' }]);
      case '/v1/users':
        return Response.json([{ disabled: false }, { disabled: true }]);
      case '/v1/backups/status':
        return Response.json({ last_verified_restore_at: '2026-01-01T00:00:00Z' });
      case '/v1/backups/kit':
        return Response.json({ state: 'issued' });
      case '/v1/tips/find-an-app':
        return Response.json(tip);
      case '/v1/tips/check-backups':
        return Response.json(backup);
      default:
        return Response.json({ error: 'not_found', message: 'Route missing' }, { status: 404 });
    }
  });
  vi.stubGlobal('fetch', fetch);
  window.sessionStorage.setItem('onemind.token', 'owner-demo');
  const user = userEvent.setup();
  render(<MemoryRouter initialEntries={[route]}><SessionProvider deps={{
    mock: false,
    makeApi: () => new MockApi('owner-demo'),
    knownPrincipal: () => DEMO_TOKENS['owner-demo'],
  }}><App mock={false} /></SessionProvider></MemoryRouter>);
  return { fetch, user };
}

afterEach(() => vi.unstubAllGlobals());

it.each(['global', 'settings'])('opens a matching tip from %s search', async scope => {
  const { user } = mount(scope === 'global' ? '/' : '/settings/appearance');
  if (scope === 'global') {
    await user.keyboard('{Control>}k{/Control}');
    await user.type(await screen.findByRole('combobox', { name: /Search apps/ }), 'backup');
    const options = within(await screen.findByRole('group', { name: 'Tips' }));
    const option = options.getByRole('option');
    expect(option).toHaveTextContent(backup.title);
    expect(option).toHaveTextContent('Open');
    await user.click(option);
  } else {
    await user.type(await screen.findByRole('searchbox', { name: 'Search settings' }), 'backup');
    await user.click(await screen.findByRole('link', { name: 'Open Check backups' }));
  }
  expect(await screen.findByText(backup.body)).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Open', exact: true })).toHaveAttribute('href', '/backups');
});

it('browses collections and searches the loaded pack with / and no further requests', async () => {
  const { fetch, user } = mount('/tips');
  const search = await screen.findByRole('searchbox', { name: 'Search Tips' });
  const collection = within(screen.getByRole('region', { name: 'Collections' }));
  expect(collection.getByRole('link', { name: backup.title })).toBeInTheDocument();
  await user.keyboard('/');
  expect(search).toHaveFocus();
  await user.type(search, 'permissions install');
  expect(collection.getByRole('link', { name: market.title })).toBeInTheDocument();
  expect(collection.queryByRole('link', { name: backup.title })).not.toBeInTheDocument();
  await user.clear(search);
  await user.selectOptions(collection.getByRole('combobox', { name: 'Collection' }), 'apps');
  expect(collection.queryByRole('link', { name: backup.title })).not.toBeInTheDocument();
  const checklist = within(screen.getByRole('region', { name: 'Getting started checklist' }));
  expect(checklist.getByRole('link', { name: backup.title })).toBeInTheDocument();
  const states = await checklist.findByRole('list', { name: 'Setup status' });
  expect(states).toHaveTextContent('Save a passkey Done');
  expect(states).toHaveTextContent('Add another person To do');
  expect(states).toHaveTextContent('Verify a backup restore Done');
  expect(states).toHaveTextContent('Save the recovery key To do');
  expect(fetch.mock.calls.map(([url]) => String(url)).sort()).toEqual([
    `${window.location.origin}/v1/auth/passkeys`,
    `${window.location.origin}/v1/backups/kit`,
    `${window.location.origin}/v1/backups/status`,
    `${window.location.origin}/v1/tips`,
    `${window.location.origin}/v1/tips/collections`,
    `${window.location.origin}/v1/users`,
  ]);
  await user.click(screen.getByRole('button', { name: 'Copy link' }));
  expect(await navigator.clipboard.readText()).toBe(`${window.location.origin}/tips`);
});

it('opens a real dashboard route from the tip, shows its clip caption, and copies its deep link', async () => {
  const { fetch, user } = mount('/tips/find-an-app');
  expect(await screen.findByRole('heading', { name: market.title, level: 1 })).toBeInTheDocument();
  expect(screen.getByText('Open the Market.')).toBeInTheDocument();
  expect(fetch.mock.calls.map(([url]) => String(url))).toEqual([`${window.location.origin}/v1/tips/find-an-app`]);
  await user.click(screen.getByRole('button', { name: 'Copy link' }));
  expect(await navigator.clipboard.readText()).toBe(`${window.location.origin}/tips/find-an-app`);
  await user.click(screen.getByRole('link', { name: 'Open' }));
  expect(await screen.findByRole('heading', { name: 'Market', level: 1 })).toBeInTheDocument();
});

it('does not turn an external path into an Open link', async () => {
  const { fetch } = mount('/tips/find-an-app', { ...market, opens: { ...market.opens, dashboard: '//example.invalid' } });
  expect(await screen.findByText('The screen for this tip is unavailable.')).toBeInTheDocument();
  expect(screen.queryByRole('link', { name: 'Open' })).not.toBeInTheDocument();
  expect(fetch.mock.calls.every(([url]) => new URL(String(url)).origin === window.location.origin)).toBe(true);
});

it('shows the actual checklist in Troubleshoot', async () => {
  mount('/troubleshoot');
  const guide = within(await screen.findByRole('region', { name: 'Getting started guide' }));
  expect(await guide.findByRole('link', { name: backup.title })).toHaveAttribute('href', '/tips/check-backups');
  expect(guide.getByRole('link', { name: 'Browse all Tips' })).toHaveAttribute('href', '/tips');
});
