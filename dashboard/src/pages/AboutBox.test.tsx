// SPDX-License-Identifier: Apache-2.0
// Settings, About this box (UMB-P14, #432) through the real HTTP client: the facts are the gateway's, and
// Copy details leaves out serial numbers, addresses and (by default) the node id.
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { describe, expect, it, vi } from 'vitest';
import { App } from '../App';
import { HttpApi } from '../api/client';
import { MockApi } from '../api/mock';
import { SessionProvider } from '../session';
import { aboutText } from '../lib/aboutText';

const node = {
  node_id: 'box0123456789', hostname: 'beelink', board: 'x86_64-efi', status: 'online', os_pretty: 'Debian GNU/Linux 13 (trixie)',
  onemind_version: '0.1.1', booted_slot: 'A', kernel: '6.12.48-amd64', cpu_model: 'Intel(R) N100', cpus: 4, mem_total_mb: 15800,
  disk_total_gb: 476.9, disk_free_gb: 400, uptime_s: 93784,
  // a hostile or buggy hub could send more than the contract allows: none of it may reach the clipboard
  serial: 'SN-777', ip: '203.0.113.9',
};
const body = { hub_node_id: 'box0123456789', node_count: 1, nodes: [node] };

function setup(answer: () => Response) {
  const http = new HttpApi({ token: 'test-only', fetchFn: vi.fn(async (path: string) => (new URL(path, window.location.origin).pathname === '/v1/os/about' ? answer() : Response.json({ error: 'not_found', message: 'no' }, { status: 404 }))) });
  const api = Object.assign(new MockApi('owner-demo'), { about: http.about.bind(http) });
  window.sessionStorage.setItem('onemind.token', 'owner-demo');
  render(<MemoryRouter initialEntries={['/settings/about']}><SessionProvider deps={{ mock: false, makeApi: () => api, knownPrincipal: () => ({ id: 'test-owner', kind: 'person', role: 'owner' }) }}><App mock={false} /></SessionProvider></MemoryRouter>);
}

describe('About this box', () => {
  it('shows the device facts from the hub', async () => {
    setup(() => Response.json(body));
    expect(await screen.findByText('Debian GNU/Linux 13 (trixie)')).toBeInTheDocument();
    for (const t of ['6.12.48-amd64', '0.1.1', 'A', 'x86_64-efi', '15.4 GB', '1d 2h']) expect(screen.getAllByText(t).length).toBeGreaterThan(0);
    expect(screen.getByText(/1 node reporting/)).toBeInTheDocument();
  });

  it('Copy details leaves out serials, addresses and the node id until the owner turns the id on', async () => {
    const u = userEvent.setup();
    const copied = vi.spyOn(navigator.clipboard, 'writeText');
    setup(() => Response.json(body));
    await screen.findByText('Debian GNU/Linux 13 (trixie)');
    await u.click(screen.getByRole('button', { name: 'Copy details' }));
    const first = copied.mock.calls[0]![0];
    expect(first).toContain('Kernel: 6.12.48-amd64');
    for (const secret of ['SN-777', '203.0.113.9', 'box0123456789']) expect(first).not.toContain(secret);
    await u.click(screen.getByRole('checkbox', { name: /Include the node id/ }));
    await u.click(screen.getByRole('button', { name: 'Copy details' }));
    expect(copied.mock.calls[1]![0]).toContain('Node ID: box0123456789');
    expect(copied.mock.calls[1]![0]).not.toContain('SN-777');
    expect(await screen.findByText('Copied.')).toBeInTheDocument();
  });

  it('tells a person without access that the details are not available for their account', async () => {
    setup(() => Response.json({ error: 'permission_denied', message: 'needs nodes:read' }, { status: 403 }));
    expect(await screen.findByText('Device details are not available for your account.')).toBeInTheDocument();
    expect(screen.queryByText(/Could not read the device details/)).not.toBeInTheDocument();
  });

  it('says so when the hub cannot answer', async () => {
    setup(() => Response.json({ error: 'internal', message: 'The hub is busy' }, { status: 500 }));
    expect(await screen.findByText(/Could not read the device details: HTTP 500/)).toBeInTheDocument();
  });
});

describe('aboutText', () => {
  it('prints a dash for a field the box did not report', () => {
    const t = aboutText({ hub_node_id: null, node_count: 2, nodes: [{ node_id: 'x', status: 'online' }] }, false);
    expect(t).toContain('OneMind support details (2 nodes)');
    expect(t).toContain('Kernel: -');
    expect(t).not.toContain('Node ID');
  });
});
