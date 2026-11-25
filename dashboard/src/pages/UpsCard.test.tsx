// SPDX-License-Identifier: Apache-2.0
// Settings > About, Power and UPS (IMG-06, #244) through the real HTTP client: what the gateway reads from upsd.
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { describe, expect, it, vi } from 'vitest';
import { App } from '../App';
import { HttpApi } from '../api/client';
import { MockApi } from '../api/mock';
import { SessionProvider } from '../session';

const none = { present: false, state: 'none', flags: [], battery_percent: null, runtime_seconds: null, load_percent: null, model: null };

function setup(answer: () => Response) {
  const fetchFn = vi.fn(async (path: string) => (new URL(path, window.location.origin).pathname === '/v1/system/ups' ? answer() : Response.json({ error: 'not_found', message: 'no' }, { status: 404 })));
  const http = new HttpApi({ token: 'test-only', fetchFn });
  const api = Object.assign(new MockApi('owner-demo'), { ups: http.ups.bind(http) });
  window.sessionStorage.setItem('onemind.token', 'owner-demo');
  render(<MemoryRouter initialEntries={['/settings/about']}><SessionProvider deps={{ mock: false, makeApi: () => api, knownPrincipal: () => ({ id: 'test-owner', kind: 'person', role: 'owner' }) }}><App mock={false} /></SessionProvider></MemoryRouter>);
  return fetchFn;
}

describe('Power and UPS', () => {
  it('shows the UPS on mains with its battery facts', async () => {
    const fetchFn = setup(() => Response.json({ ...none, present: true, state: 'online', flags: ['OL', 'CHRG'], battery_percent: 97, runtime_seconds: 4500, load_percent: 22, model: 'APC Back-UPS ES 700' }));
    expect(await screen.findByText('On mains power')).toBeInTheDocument();
    for (const t of ['APC Back-UPS ES 700', '97%', '1 h 15 min', '22%']) expect(screen.getByText(t)).toBeInTheDocument();
    expect(fetchFn.mock.calls.some(([p]) => String(p).includes('/v1/system/ups'))).toBe(true);
  });

  it('says the box is shutting down cleanly on a low battery', async () => {
    setup(() => Response.json({ ...none, present: true, state: 'low_battery', flags: ['OB', 'LB'], battery_percent: 4 }));
    expect(await screen.findByText('Battery low')).toBeInTheDocument();
    expect(screen.getByText(/shutting down cleanly now: apps first, then Kubernetes, then the data disk/)).toBeInTheDocument();
  });

  it('tells a box without a UPS how to add one', async () => {
    setup(() => Response.json(none));
    expect(await screen.findByText('No UPS')).toBeInTheDocument();
    expect(screen.getByText(/Plug one in by USB and restart the box/)).toBeInTheDocument();
  });

  it('tells a person without access that power details are not available', async () => {
    setup(() => Response.json({ error: 'permission_denied', message: 'needs nodes:read' }, { status: 403 }));
    expect(await screen.findByText('Power details are not available for your account.')).toBeInTheDocument();
  });
});
