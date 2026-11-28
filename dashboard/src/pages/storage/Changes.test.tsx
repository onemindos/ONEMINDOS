// SPDX-License-Identifier: Apache-2.0
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, expect, it, vi } from 'vitest';
import { App } from '../../App';
import { DEMO_TOKENS } from '../../api/fixtures';
import { MockApi } from '../../api/mock';
import { SessionProvider } from '../../session';
import { diskSize } from './Changes';

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
let summary: Record<string, unknown> = { node_id: 'n', enabled: true, available: true, state: 'unprotected', members: [{ devid: 1, missing: false, size_bytes: 4e12 }] };
const oneMember = summary;
const disks = [{ path: '/dev/sda', model: 'System SSD', size_bytes: 256e9, role: 'system', serial_tail: '1111' }, { path: '/dev/sdb', model: 'Blank HDD', size_bytes: 4e12, role: 'unused', serial_tail: '2222' }];
const okPlan = { type: 'storage.mirror.add', risk: 'destructive', plan_sha256: 'abc123', plan: { blocked: false, encrypted: true, targets: [{ path: '/dev/sdb', model: 'Blank HDD', size_bytes: 4e12, serial_tail: '2222' }],
  checks: [{ id: 'blank', ok: true, detail: 'the disk is blank' }], warnings: ['Copying 4 TB takes a day.'], steps: [{}, {}, {}] } };
type Post = { path: string; body: Record<string, unknown>; key: string | null };
function mount(token: string, plan: Response | (() => Response) = json(okPlan)) {
  const posts: Post[] = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    const path = new URL(String(url)).pathname;
    if (init?.method === 'POST') {
      posts.push({ path, body: JSON.parse(String(init.body)), key: new Headers(init.headers).get('Idempotency-Key') });
      if (path === '/v1/storage/plans') return typeof plan === 'function' ? plan() : plan.clone();
      if (path === '/v1/storage/actions') return json({ action: { id: 'act_8', state: 'awaiting_approval' }, plan: okPlan.plan }, 202);
    }
    if (path === '/v1/storage') return json(summary);
    if (path === '/v1/storage/devices') return json(disks);
    return json({ error: 'not_found', message: path }, 404);
  }));
  window.sessionStorage.setItem('onemind.token', token);
  render(<MemoryRouter initialEntries={['/storage']}><SessionProvider deps={{ mock: false, makeApi: () => new MockApi(token), knownPrincipal: () => DEMO_TOKENS[token] }}><App mock={false} /></SessionProvider></MemoryRouter>);
  return posts;
}
afterEach(() => { vi.unstubAllGlobals(); summary = oneMember; });

it('shows the plan first and offers only blank disks, then files a request that waits for approval', async () => {
  const posts = mount('owner-demo');
  const u = userEvent.setup();
  await u.selectOptions(await screen.findByLabelText('What do you want to do?'), 'storage.mirror.add');
  const select = screen.getByLabelText('The blank disk');
  expect(within(select).queryByText(/System SSD/)).not.toBeInTheDocument();
  await u.selectOptions(select, '/dev/sdb');
  await u.click(screen.getByRole('button', { name: 'Show what would happen' }));
  const plan = await screen.findByRole('region', { name: 'Plan' });
  expect(within(plan).getByText(/anything on them erased/)).toBeInTheDocument();
  expect(within(plan).getByText('the disk is blank')).toBeInTheDocument();
  expect(within(plan).getByText('Copying 4 TB takes a day.')).toBeInTheDocument();
  expect(posts).toHaveLength(1); // the dry run only
  expect(posts[0]).toMatchObject({ path: '/v1/storage/plans', body: { type: 'storage.mirror.add', params: { device: '/dev/sdb' } } });
  await u.click(within(plan).getByRole('button', { name: 'Ask for approval' }));
  expect(await within(plan).findByRole('link', { name: 'Open it in Approvals' })).toHaveAttribute('href', '/approvals?highlight=act_8');
  expect(posts).toHaveLength(2);
  expect(posts[1]).toMatchObject({ path: '/v1/storage/actions', body: { type: 'storage.mirror.add', params: { device: '/dev/sdb' } } });
  expect(posts[1]!.key).toMatch(/^[a-f0-9-]{36}$/);
});

it('will not ask for approval when a safety check failed', async () => {
  const blocked = { ...okPlan, plan: { ...okPlan.plan, blocked: true, checks: [{ id: 'blank', ok: false, detail: 'the disk has data on it' }] } };
  const posts = mount('owner-demo', json(blocked));
  const u = userEvent.setup();
  await u.selectOptions(await screen.findByLabelText('What do you want to do?'), 'storage.mirror.add');
  await u.selectOptions(screen.getByLabelText('The blank disk'), '/dev/sdb');
  await u.click(screen.getByRole('button', { name: 'Show what would happen' }));
  expect(await screen.findByText(/a safety check failed/)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Ask for approval' })).toBeDisabled();
  expect(posts).toHaveLength(1);
});

it('says why when the box refuses the plan (409)', async () => {
  mount('owner-demo', json({ error: 'stale_precondition', message: 'the storage service refused the plan: no such disk' }, 409));
  const u = userEvent.setup();
  await u.selectOptions(await screen.findByLabelText('What do you want to do?'), 'storage.mirror.add');
  await u.selectOptions(screen.getByLabelText('The blank disk'), '/dev/sdb');
  await u.click(screen.getByRole('button', { name: 'Show what would happen' }));
  expect(await screen.findByRole('alert')).toHaveTextContent(/The box refused it/);
});

it('offers repair with no disk to choose, and nothing at all to an adult', async () => {
  mount('adult-demo');
  expect(await screen.findByText('Only an owner can change the disks.')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Show what would happen' })).not.toBeInTheDocument();
});

it('writes disk sizes in GB and TB, the same way as the CLI', () => {
  // The same values as TestStorageSizeReadsLikeADiskLabel in cmd/onemind/cli/storage_changes_test.go.
  expect(diskSize(256e9)).toBe('256 GB');
  expect(diskSize(1.5e12)).toBe('1.5 TB');
  expect(diskSize(4e12)).toBe('4 TB');
  expect(diskSize(999.96e9)).toBe('1 TB');
  expect(diskSize(null)).toBe('size not reported');
});

it('offers the two options the API has, in plain words, and sets them only when ticked', async () => {
  summary = { ...oneMember, state: 'protected', members: [{ devid: 1, missing: false, size_bytes: 4e12 }, { devid: 2, missing: false, size_bytes: 4e12 }] };
  const posts = mount('owner-demo');
  const u = userEvent.setup();
  await u.selectOptions(await screen.findByLabelText('What do you want to do?'), 'storage.mirror.add');
  expect(screen.queryByLabelText('Allow the mirror to drop to one disk')).not.toBeInTheDocument();
  expect(screen.queryByLabelText('Erase the old disk afterwards')).not.toBeInTheDocument();
  await u.selectOptions(screen.getByLabelText('What do you want to do?'), 'storage.mirror.remove');
  await u.selectOptions(screen.getByLabelText('The member'), 'devid:2');
  await u.click(screen.getByRole('button', { name: 'Show what would happen' }));
  await screen.findByRole('region', { name: 'Plan' });
  expect(posts[0]!.body).toEqual({ type: 'storage.mirror.remove', params: { member: 'devid:2', unprotect: false, wipe: false } });
  await u.click(screen.getByLabelText('Allow the mirror to drop to one disk'));
  await u.click(screen.getByLabelText('Erase the old disk afterwards'));
  expect(screen.queryByRole('region', { name: 'Plan' })).not.toBeInTheDocument(); // a changed choice needs a new plan
  await u.click(screen.getByRole('button', { name: 'Show what would happen' }));
  await screen.findByRole('region', { name: 'Plan' });
  expect(posts[1]!.body).toEqual({ type: 'storage.mirror.remove', params: { member: 'devid:2', unprotect: true, wipe: true } });
  await u.click(screen.getByRole('button', { name: 'Ask for approval' }));
  await screen.findByRole('link', { name: 'Open it in Approvals' });
  expect(posts[2]!.body).toEqual({ type: 'storage.mirror.remove', params: { member: 'devid:2', unprotect: true, wipe: true } });
  // Replace offers erasing the old disk but never dropping to one disk.
  await u.selectOptions(screen.getByLabelText('What do you want to do?'), 'storage.mirror.replace');
  expect(screen.getByLabelText('Erase the old disk afterwards')).not.toBeChecked();
  expect(screen.queryByLabelText('Allow the mirror to drop to one disk')).not.toBeInTheDocument();
});

it('tells two missing members apart in the member list', async () => {
  summary = { ...oneMember, state: 'degraded', members: [{ devid: 1, missing: false, size_bytes: 4e12 }, { devid: 2, missing: true, size_bytes: 4e12 }, { devid: 3, missing: true, size_bytes: 1.5e12 }] };
  mount('owner-demo');
  const u = userEvent.setup();
  await u.selectOptions(await screen.findByLabelText('What do you want to do?'), 'storage.mirror.remove');
  const options = within(screen.getByLabelText('The member')).getAllByRole('option').map((o) => (o as HTMLOptionElement).value).filter(Boolean);
  expect(options).toEqual(['devid:1', 'devid:2', 'devid:3']);
  expect(within(screen.getByLabelText('The member')).getByText('Member 3 (missing) · 1.5 TB')).toBeInTheDocument();
});
