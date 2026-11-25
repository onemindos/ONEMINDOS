// SPDX-License-Identifier: Apache-2.0
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { App } from '../App';
import { DEMO_TOKENS } from '../api/fixtures';
import { MockApi } from '../api/mock';
import { SessionProvider } from '../session';

afterEach(() => vi.unstubAllGlobals());

it('opens Settings > Care, shows gateway evidence and files only a pending backup request', async () => {
  const writes: string[] = [];
  vi.stubGlobal('fetch', async (url: string, init: RequestInit) => {
    const path = new URL(url).pathname;
    if (path === '/v1/care/checkup') return Response.json([
      { id: 'backup', state: 'finding', detail: 'No successful backup for music.', fix: 'backup.run' },
      { id: 'drill', state: 'unavailable', detail: 'No restore drill report is mounted.', fix: null },
    ]);
    writes.push(path);
    expect(path).toBe('/v1/backups/runs');
    expect(JSON.parse(String(init.body))).toMatchObject({ scope: 'box', approve: false });
    const key = new Headers(init.headers).get('Idempotency-Key');
    expect(key).toBeTruthy();
    return Response.json({ id: 'care-request', type: 'backup.run', state: 'awaiting_approval', idempotency_key: key });
  });
  const token = 'owner-demo';
  window.sessionStorage.setItem('onemind.token', token);
  render(<MemoryRouter initialEntries={['/settings/care']}><SessionProvider deps={{
    mock: false, makeApi: () => new MockApi(token), knownPrincipal: () => DEMO_TOKENS[token],
  }}><App mock={false} /></SessionProvider></MemoryRouter>);
  expect(await screen.findByText('No successful backup for music.')).toBeVisible();
  expect(screen.getByText('No restore drill report is mounted.')).toBeVisible();
  expect(writes).toEqual([]);
  fireEvent.click(screen.getByRole('button', { name: 'Request a whole-box backup' }));
  expect(await screen.findByRole('link', { name: 'View approval request' })).toHaveAttribute('href', '/approvals?highlight=care-request');
  expect(writes).toEqual(['/v1/backups/runs']);
});
