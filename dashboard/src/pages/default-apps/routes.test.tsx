// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { expect, it, vi } from 'vitest';
import { App } from '../../App';
import { DEMO_TOKENS } from '../../api/fixtures';
import { MockApi } from '../../api/mock';
import { SessionProvider } from '../../session';

it('mounts Default apps in Settings and opens the saved Media choice with a scoped app session', async () => {
  const originalUrl = window.location.href;
  const dom = (globalThis as unknown as { jsdom: { reconfigure(opts: { url: string }): void } }).jsdom;
  dom.reconfigure({ url: 'https://box.example.local/' });
  const tab = { opener: window, location: { href: '' } };
  const open = vi.spyOn(window, 'open').mockReturnValue(tab as unknown as Window);
  const openAppSession = vi.fn(async () => {});
  const api = Object.assign(new MockApi('owner-demo'), { openAppSession });
  const app = (await api.apps()).find((a) => a.id === 'jellyfin')!;
  vi.spyOn(api, 'apps').mockResolvedValue([{ ...app, installed: true, status: 'installed' }]);
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (new URL(String(url), window.location.origin).pathname === '/v1/me/home') {
      return new Response(JSON.stringify({ version: 3, default_apps: { media: 'jellyfin' } }),
        { headers: { 'Content-Type': 'application/json', ETag: '"chosen"' } });
    }
    return new Response('{}', { status: 404, headers: { 'Content-Type': 'application/json' } });
  }));
  const mount = (route: string) => render(<MemoryRouter initialEntries={[route]}>
    <SessionProvider deps={{ mock: false, makeApi: () => api, knownPrincipal: () => DEMO_TOKENS['owner-demo'] }}>
      <App mock={false} />
    </SessionProvider>
  </MemoryRouter>);
  try {
    window.sessionStorage.setItem('onemind.token', 'owner-demo');
    const settings = mount('/settings/default-apps');
    expect(await screen.findByRole('link', { name: 'Default apps' })).toHaveAttribute('aria-current', 'page');
    expect(await screen.findByRole('combobox', { name: 'Media' })).toHaveValue('jellyfin');
    settings.unmount();
    const installed = mount('/installed');
    await userEvent.click(await screen.findByRole('button', { name: 'Open with Jellyfin' }));
    expect(open).toHaveBeenCalledWith('about:blank', '_blank');
    expect(openAppSession).toHaveBeenCalledOnce();
    await waitFor(() => expect(tab.location.href).toBe('https://jellyfin.box.example.local/'));
    expect(tab.opener).toBeNull();
    installed.unmount();
  } finally {
    open.mockRestore();
    vi.unstubAllGlobals();
    dom.reconfigure({ url: originalUrl });
  }
});
