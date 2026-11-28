// SPDX-License-Identifier: Apache-2.0
// Settings > Appearance: the Dock and Home tiles lists reorder by button and persist.
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { App } from '../App';
import { DEMO_TOKENS } from '../api/fixtures';
import { MockApi } from '../api/mock';
import { SessionProvider } from '../session';

function mount() {
  vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 404, headers: { 'content-type': 'application/json' } })));
  window.sessionStorage.setItem('onemind.token', 'adult-demo');
  render(
    <MemoryRouter initialEntries={['/settings/appearance']}>
      <SessionProvider deps={{ mock: false, makeApi: () => new MockApi('adult-demo'), knownPrincipal: () => DEMO_TOKENS['adult-demo'] }}>
        <App mock={false} />
      </SessionProvider>
    </MemoryRouter>,
  );
}
afterEach(() => vi.unstubAllGlobals());

it('moves a dock item up, remembers it and can reset the order', async () => {
  const user = userEvent.setup();
  mount();
  const dock = await screen.findByRole('list', { name: 'Dock order' });
  const first = () => within(dock).getAllByRole('listitem').map((li) => li.textContent);
  const before = first();
  await user.click(within(dock).getByRole('button', { name: `Move ${before[1]!.replace(/(Up|Down)+$/, '').trim()} up` }));
  expect(first()[0]).toBe(before[1]);
  await user.click(screen.getByRole('button', { name: 'Reset dock order' }));
  expect(first()).toEqual(before);
});

it('lists Home tiles with Needs you locked first', async () => {
  mount();
  const tiles = await screen.findByRole('list', { name: 'Home tiles' });
  const items = within(tiles).getAllByRole('listitem');
  expect(items[0]).toHaveTextContent('always on');
  expect(within(items[0]!).queryByRole('button')).toBeNull();
});
