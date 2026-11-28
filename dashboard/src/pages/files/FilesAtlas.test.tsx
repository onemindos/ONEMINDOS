// SPDX-License-Identifier: Apache-2.0
// Atlas Files (07): the sidebar of spaces, disks and backup destinations, the Copies column read from
// GET /v1/backups/status, the footer line and the drop zone (the same tus upload as the button).
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { App } from '../../App';
import { DEMO_TOKENS } from '../../api/fixtures';
import { MockApi } from '../../api/mock';
import { SessionProvider } from '../../session';
import { seriousViolations } from '../../test/helpers';
import { copiesLabel, copiesOf, copiesSummary, toBackupState, EXPORT_FILE } from './copies';

const LAST = '2026-11-21T02:10:00Z';
const NEXT = '2026-11-22T02:10:00Z';
const roots = [
  { root: 'home:owner', kind: 'home', name: 'My files', path: '/', access: 'read-write', writable: true, used_bytes: 2000, quota_bytes: null, free_bytes: 5_000_000 },
  { root: 'shared', kind: 'shared', name: 'Family', path: '/', access: 'read-write', writable: true, used_bytes: 1000, quota_bytes: null, free_bytes: 5_000_000 },
];
const entries = [
  { name: 'Seeds', path: '/Seeds', type: 'dir', size: null, mtime: '2026-11-19T10:00:00Z' },
  { name: 'plan.pdf', path: '/plan.pdf', type: 'file', size: 480_000, mtime: '2026-11-20T10:00:00Z' },
  { name: 'vent-rules.yaml', path: '/vent-rules.yaml', type: 'file', size: 3_000, mtime: '2026-11-21T09:00:00Z' },
];
const status = (over: Record<string, unknown> = {}) => ({
  health: 'ok', next_run_at: NEXT, copies: 2,
  destinations: [{ id: 'd1', kind: 'usb', label: 'black-usb', primary: true }, { id: 'd2', kind: 'peer', label: 'rosa-box', primary: false }],
  badges: { box: { state: 'ok' }, system: { state: 'ok', last_success_at: LAST }, apps: {} },
  builtin_units: [{ unit: 'gateway', in_snapshot: true }, { unit: 'builtin:files', in_snapshot: true, dirs: [{ name: 'ONEMIND_FILES_ROOT', configured: true, carried: true }] }],
  ...over,
});
/** One run as GET /v1/backups/runs returns it (core backups/store.py run_json). */
const run = (dest: string, startedAt: string, opts: { system?: string; exportOk?: boolean; state?: string } = {}) => ({
  id: `run-${dest}-${startedAt}`, destination_id: dest, state: opts.state ?? 'succeeded', started_at: startedAt, finished_at: startedAt,
  units: [{ unit: 'system', state: opts.system ?? 'succeeded' }], hooks: [{ unit: 'builtins', phase: 'pre', command: EXPORT_FILE, ok: opts.exportOk ?? true }],
});
const RUNS = [run('d1', LAST)];
type Call = { method: string; path: string; search: URLSearchParams };
const json = (v: unknown, code = 200, headers: Record<string, string> = {}) => new Response(JSON.stringify(v), { status: code, headers: { 'content-type': 'application/json', ...headers } });

function mount(opts: { backups?: unknown; runs?: unknown; backupsStatus?: number; token?: keyof typeof DEMO_TOKENS; noPrincipal?: boolean } = {}) {
  const calls: Call[] = [];
  const token = opts.token ?? 'owner-demo';
  vi.stubGlobal('fetch', vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    const u = new URL(String(url), 'http://hub.test');
    const c: Call = { method: init?.method ?? 'GET', path: u.pathname, search: u.searchParams };
    calls.push(c);
    if (c.path === '/v1/files/roots') return json(roots);
    if (c.path === '/v1/files/list') return json(entries);
    if (c.path === '/v1/backups/runs') return json(opts.runs ?? RUNS);
    if (c.path === '/v1/backups/status') return opts.backupsStatus ? json({ error: 'permission_denied', message: 'no' }, opts.backupsStatus) : json(opts.backups ?? status());
    if (c.path === '/v1/storage/devices') return json([{ path: '/dev/nvme0n1', model: 'hub NVMe', role: 'data', size_bytes: 2_000_000_000_000, health: { verdict: 'ok', temperature_c: 41 } }]);
    if (c.path === '/v1/files/uploads' && c.method === 'POST') return new Response('{}', { status: 201, headers: { Location: '/v1/files/uploads/upl_1', 'Upload-Offset': '0' } });
    if (c.path === '/v1/files/uploads/upl_1' && c.method === 'PATCH') return new Response(null, { status: 204, headers: { 'Upload-Offset': '3' } });
    return json([]);
  }));
  window.sessionStorage.setItem('onemind.token', token);
  const api = Object.assign(new MockApi(token), {
    me: async () => ({ principal: DEMO_TOKENS[token], token: null, session: null, passkeys: 0, scopes: DEMO_TOKENS[token]?.role === 'owner' ? ['*'] : [], capabilities: [], step_up: { passkeys_active: false, require_passkey_approval: false } }),
  });
  render(<MemoryRouter initialEntries={['/files']}><SessionProvider deps={{ mock: false, makeApi: () => api, knownPrincipal: () => (opts.noPrincipal ? undefined : DEMO_TOKENS[token]) }}><App mock={false} /></SessionProvider></MemoryRouter>);
  return calls;
}
afterEach(() => vi.unstubAllGlobals());

describe('copies rule', () => {
  const s = toBackupState(status(), RUNS);
  it('counts the box plus the primary only for a file changed before a run to the primary that carried Files', () => {
    expect(copiesOf(entries[1]!, s)).toMatchObject({ kind: 'copied', count: 2, primary: 'black-usb' });
    expect(copiesOf(entries[0]!, s)).toEqual({ kind: 'folder' });
    expect(copiesSummary(entries, s)).toMatchObject({ copied: 1, waiting: 1 });
    expect(s.others.map((d) => d.label)).toEqual(['rosa-box']);
  });
  it('a file newer than the last primary run has 1 copy', () => {
    expect(copiesOf(entries[2]!, s)).toEqual({ kind: 'waiting', next: NEXT });
  });
  it('a failed primary run (system unit or Files export) is not a copy', () => {
    for (const r of [run('d1', LAST, { system: 'failed', state: 'failed' }), run('d1', LAST, { exportOk: false, state: 'partial' })])
      expect(copiesOf(entries[1]!, toBackupState(status(), [r]))?.kind).toBe('waiting');
  });
  it('off-site down while the primary is healthy still claims only the box and the primary', () => {
    const st = toBackupState(status({ health: 'failing' }), [run('d1', LAST), run('d2', '2026-11-20T02:10:00Z', { system: 'failed', state: 'failed' })]);
    expect(copiesOf(entries[1]!, st)).toMatchObject({ kind: 'copied', count: 2 });
  });
  it('never counts a destination with no run (just added), a run to another destination, or folders that do not travel', () => {
    expect(copiesOf(entries[1]!, toBackupState(status(), []))?.kind).toBe('waiting');
    expect(copiesOf(entries[1]!, toBackupState(status(), [run('d2', LAST)]))?.kind).toBe('waiting');
    expect(copiesOf(entries[1]!, toBackupState(status({ builtin_units: [{ unit: 'builtin:files', dirs: [{ configured: true, carried: false }] }] }), RUNS))?.kind).toBe('waiting');
    expect(copiesLabel(copiesOf(entries[1]!, toBackupState(status({ destinations: [] }), RUNS))!)).toBe('1 copy · no backup');
    expect(() => toBackupState([], [])).toThrow();
  });
});

describe('Atlas Files', () => {
  it('shows spaces, disks and destinations in the sidebar and a Copies column from the hub', async () => {
    mount();
    const nav = await screen.findByRole('navigation', { name: 'Places' });
    const spaces = within(nav).getByRole('list', { name: 'Spaces' });
    expect(within(spaces).getByRole('button', { name: /My files/ })).toHaveAttribute('aria-pressed', 'true');
    expect(await within(nav).findByText('hub NVMe')).toBeInTheDocument();
    expect(within(nav).getByText(/Health ok · 41 °C/)).toBeInTheDocument();
    expect(await within(nav).findByText('rosa-box')).toBeInTheDocument();
    expect(await screen.findByRole('columnheader', { name: 'Copies' })).toBeInTheDocument();
    const row = (await screen.findByRole('button', { name: 'Preview plan.pdf' })).closest('tr')!;
    expect(row).toHaveTextContent('2 copies');
    expect(screen.getByRole('button', { name: 'Preview vent-rules.yaml' }).closest('tr')!).toHaveTextContent(/1 copy · next/);
    expect(await screen.findByText(/1 has 2 copies/)).toBeInTheDocument();
    expect(screen.getByText('Also copied to: rosa-box (daily)')).toBeInTheDocument();
    expect(within(nav).getByText(/daily · not counted/)).toBeInTheDocument();
    expect(await seriousViolations(screen.getByRole('main'))).toEqual([]);
  });

  it('shows owner disks on a real box, where the role comes from GET /v1/me and no principal is injected', async () => {
    mount({ noPrincipal: true });
    const nav = await screen.findByRole('navigation', { name: 'Places' });
    expect(await within(nav).findByText('hub NVMe', {}, { timeout: 4000 })).toBeInTheDocument();
  });

  it('picking a space in the sidebar lists that space', async () => {
    const calls = mount();
    const u = userEvent.setup();
    await u.click(await screen.findByRole('button', { name: /Family/ }));
    await waitFor(() => expect(calls.some((c) => c.path === '/v1/files/list' && c.search.get('root') === 'shared')).toBe(true));
  });

  it('a role that may not read backups gets no Copies column and no destinations, and nothing is guessed', async () => {
    mount({ backupsStatus: 403 });
    await screen.findByRole('button', { name: 'Preview plan.pdf' });
    expect(screen.queryByRole('columnheader', { name: 'Copies' })).toBeNull();
    expect(screen.queryByText(/copies/)).toBeNull();
  });

  it('dropping a file uploads it over tus into the open folder', async () => {
    const calls = mount();
    const zone = await screen.findByRole('region', { name: /Drop files here/ });
    fireEvent.drop(zone, { dataTransfer: { files: [new File(['abc'], 'drop.txt', { type: 'text/plain' })] } });
    await waitFor(() => expect(calls.some((c) => c.method === 'PATCH' && c.path === '/v1/files/uploads/upl_1')).toBe(true));
  });
});
