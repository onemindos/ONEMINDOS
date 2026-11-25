// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useParams } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { DefaultApps, OpenWith } from './DefaultApps';

afterEach(() => vi.unstubAllGlobals());

const state = vi.hoisted(() => ({ token: 'adult', apps: [
  { id: 'firefox', name: 'Firefox', category: 'developer', browser: true, installed: true, web_port: 8080 },
  { id: 'chromium', name: 'Chromium', category: 'developer', browser: true, installed: true, web_port: 8080 },
  { id: 'removed', name: 'Removed', category: 'developer', browser: true, installed: false, web_port: 8080 },
] }));
vi.mock('../../session', () => ({
  useSignedIn: () => ({ token: state.token, person: state.token, mock: false, api: {} }),
  useSession: () => ({ signOut: null }),
}));
vi.mock('../../data/hub', () => ({ useHub: () => ({ apps: { data: state.apps } }) }));

function Browser() { return <h1>{useParams().id} browser window</h1>; }
function mount(settings: boolean) {
  return render(<MemoryRouter><Routes>
    <Route path="/" element={settings ? <DefaultApps /> : <OpenWith />} />
    <Route path="/browser/:id" element={<Browser />} />
  </Routes></MemoryRouter>);
}

it('saves a personal default, opens it from Installed apps, and prompts another person to choose', async () => {
  const homes: Record<string, Record<string, string>> = {};
  const put = vi.fn();
  vi.stubGlobal('fetch', vi.fn(async (url: string, init: RequestInit) => {
    expect(new URL(String(url)).pathname).toBe('/v1/me/home');
    const headers = new Headers(init.headers);
    const who = headers.get('Authorization')!;
    if (init.method === 'PUT') {
      const doc = JSON.parse(String(init.body));
      expect(headers.get('If-Match')).toBe('"first"');
      expect(doc.layout).toBe('classic');
      put(doc.default_apps);
      homes[who] = doc.default_apps;
    }
    return new Response(JSON.stringify({ version: 3, layout: 'classic', default_apps: homes[who] ?? {} }),
      { headers: { 'Content-Type': 'application/json', ETag: '"first"' } });
  }));
  const user = userEvent.setup();
  const settings = mount(true);
  const defaults = await screen.findByRole('combobox', { name: 'Web browser' });
  expect(screen.queryByRole('option', { name: 'Removed' })).toBeNull();
  await user.selectOptions(defaults, 'chromium');
  await waitFor(() => expect(put).toHaveBeenCalledWith({ browser: 'chromium' }));
  settings.unmount();
  const installed = mount(false);
  await user.click(await screen.findByRole('button', { name: 'Open with Chromium' }));
  expect(await screen.findByRole('heading', { name: 'chromium browser window' })).toBeInTheDocument();
  installed.unmount();
  state.token = 'owner';
  try {
    mount(false);
    const pick = await screen.findByRole('combobox', { name: 'Web browser' });
    expect(pick).toHaveValue('');
    await user.selectOptions(pick, 'firefox');
    await user.click(screen.getByRole('button', { name: 'Open with Firefox' }));
    expect(await screen.findByText('firefox browser window')).toBeInTheDocument();
    expect(put).toHaveBeenCalledTimes(1);
  } finally { state.token = 'adult'; }
});
