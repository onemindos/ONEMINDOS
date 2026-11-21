// SPDX-License-Identifier: Apache-2.0
// Home's backups and updates widgets read the real gateway routes, never made-up numbers.
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { App } from '../App';
import { DEMO_TOKENS } from '../api/fixtures';
import { MockApi } from '../api/mock';
import { backupsFromStatus, meshFromHub, osUpdatesFromHub, updatesFromHub } from '../data/homeExtras';
import { SessionProvider } from '../session';

const NOW = '2026-11-21T10:00:00Z';
const backupStatus = { health: 'ok', reason: null, last_success_at: '2026-11-21T04:00:00Z', last_verified_restore_at: null, destinations: [{ id: 'd1' }] };
const osStatus = { nodes: [{ node_id: 'box1', current_version: '0.1.1', available_version: '0.1.2', channel: 'security', last_check: '2026-11-21T09:00:00Z' }] };
function response(value: unknown, code = 200) { return new Response(JSON.stringify(value), { status: code, headers: { 'content-type': 'application/json' } }); }
afterEach(() => vi.unstubAllGlobals());

it('feeds Home from /v1/backups/status and /v1/os/updates', async () => {
  const paths: string[] = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string | URL | Request) => {
    const path = new URL(String(url)).pathname;
    paths.push(path);
    if (path === '/v1/backups/status') return response(backupStatus);
    if (path === '/v1/os/updates') return response(osStatus);
    if (path === '/v1/mesh') return response({ nodes: [], control: { state: 'off' } });
    return response({ error: 'not_found', message: path }, 404);
  }));
  window.sessionStorage.setItem('onemind.token', 'owner-demo');
  render(<MemoryRouter initialEntries={['/']}><SessionProvider deps={{ mock: false, makeApi: () => new MockApi('owner-demo'), knownPrincipal: () => DEMO_TOKENS['owner-demo'] }}><App mock={false} /></SessionProvider></MemoryRouter>);
  expect(await screen.findByText('0.1.1 → 0.1.2', { exact: false }, { timeout: 4000 })).toBeInTheDocument();
  expect(await screen.findByText('Restore verified')).toBeInTheDocument();
  expect(paths).toEqual(expect.arrayContaining(['/v1/backups/status', '/v1/os/updates', '/v1/mesh']));
  expect(screen.queryByText(/come with CORE-/)).not.toBeInTheDocument();
});

it('maps backups, updates and mesh without inventing values', () => {
  expect(backupsFromStatus(backupStatus, NOW)).toEqual({ last_run: '2026-11-21T04:00:00Z', last_verified_restore: null, destinations: [], observed_at: NOW });
  expect(() => backupsFromStatus({ health: 'failing', reason: 'agent unreachable' }, NOW)).toThrow('agent unreachable');
  expect(() => backupsFromStatus([], NOW)).toThrow(/invalid/);
  const u = updatesFromHub(osStatus, [{ id: 'kuma', version: '1', update_available: '2' } as never, { id: 'x', version: '1' } as never], NOW);
  expect(u.os).toEqual({ from: '0.1.1', to: '0.1.2', channel: 'security' });
  expect(u.apps).toEqual([{ app_id: 'kuma', from: '1', to: '2' }]);
  expect(u.checked_at).toBe('2026-11-21T09:00:00Z');
  expect(updatesFromHub({ nodes: [{ node_id: 'a' }] }, undefined, NOW)).toMatchObject({ os: null, apps: [], checked_at: NOW });
  expect(() => updatesFromHub({ nodes: 'x' }, [], NOW)).toThrow(/invalid/);
  const m = meshFromHub({ control: { state: 'up' }, nodes: [{ node_id: 'n1', name: 'node-n1', state: 'up' }, { name: 'w', state: 'weird' }] }, NOW);
  expect(m.links).toEqual([{ hostname: 'node-n1', via: 'mesh', state: 'up' }, { hostname: 'w', via: 'mesh', state: 'degraded' }]);
  expect(m.remote_access).toBe('mesh');
  expect(meshFromHub({ nodes: [] }, NOW).remote_access).toBe('off');
});

it('keeps Home mounted and shows a widget error when /v1/os/updates has no nodes array', async () => {
  vi.stubGlobal('fetch', vi.fn(async (url: string | URL | Request) => {
    const path = new URL(String(url)).pathname;
    if (path === '/v1/backups/status') return response(backupStatus);
    if (path === '/v1/os/updates') return response({});
    if (path === '/v1/mesh') return response({ nodes: [], control: { state: 'off' } });
    return response({ error: 'not_found', message: path }, 404);
  }));
  window.sessionStorage.setItem('onemind.token', 'owner-demo');
  render(<MemoryRouter initialEntries={['/']}><SessionProvider deps={{ mock: false, makeApi: () => new MockApi('owner-demo'), knownPrincipal: () => DEMO_TOKENS['owner-demo'] }}><App mock={false} /></SessionProvider></MemoryRouter>);
  expect(await screen.findByText(/invalid update status/i, {}, { timeout: 4000 })).toBeInTheDocument();
  expect(await screen.findByText('Restore verified')).toBeInTheDocument();
});

it('osUpdatesFromHub rejects a payload without nodes', () => {
  expect(() => osUpdatesFromHub({}, NOW)).toThrow(/invalid/);
});
