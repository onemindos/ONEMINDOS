// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';
import { FirstRun, firstSite, landingAfterSetup, placeOf, useWizardPending } from './FirstRun';

const h = vi.hoisted(() => ({
  get: vi.fn(), save: vi.fn(), state: vi.fn(), issue: vi.fn(), confirm: vi.fn(), plan: vi.fn(), request: vi.fn(), destinations: vi.fn(), done: vi.fn(), navigate: vi.fn(),
  props: {} as Record<string, unknown>,
}));
vi.mock('../session', () => {
  const api = { onboardingSettings: h.get, saveOnboardingSettings: h.save, backupDestinations: h.destinations, onboardingState: h.state,
    issueKit: h.issue, confirmKit: h.confirm, appPlan: h.plan };
  return { useSignedIn: () => ({ api, token: 'owner-token', mock: false }) };
});
vi.mock('../data/hub', () => ({ useHub: () => ({ apps: { data: [] }, request: h.request }) }));
vi.mock('react-router', () => ({ useNavigate: () => h.navigate }));
vi.mock('@onemind/ui', async (actual) => ({
  ...(await actual<typeof import('@onemind/ui')>()),
  useToast: () => ({ show: vi.fn() }), applyTheme: vi.fn(),
  Onboarding: (props: Record<string, unknown>) => { h.props = props; return <div>Existing wizard</div>; },
}));
const noKit = { state: 'missing', confirmed_at: null, fingerprint: null, positions: [] };
h.state.mockResolvedValue({ complete: false, settings_saved: false, backups_enabled: true, destinations: 0, kit: noKit });
const values = { box_name: 'home-hub', time_zone: 'UTC', backup_choice: 'usb', backup_destination_id: 'dst_0123456789abcdef' };

it('loads durable settings and actual destinations, then awaits save and verified readback before allowing completion', async () => {
  let release!: (value: unknown) => void;
  h.get.mockResolvedValueOnce({ ...values, saved: true });
  h.destinations.mockResolvedValue([{ id: values.backup_destination_id, kind: 'usb', label: 'Existing disk' }]);
  h.save.mockImplementation(() => new Promise((r) => { release = r; }));
  render(<FirstRun onDone={h.done} />);
  expect(screen.getByRole('status')).toHaveTextContent(/Loading/);
  await screen.findByText('Existing wizard');
  expect(h.props.initial).toMatchObject({ boxName: 'home-hub', timeZone: 'UTC', backup: { destinationId: values.backup_destination_id, kitSaved: false } });
  expect(h.props.backupDestinations).toEqual([{ id: values.backup_destination_id, kind: 'usb', label: 'Existing disk' }]);
  const save = h.props.onSaveSettings as (d: unknown) => Promise<void>;
  let saved = false;
  const pending = save({ boxName: 'home-hub', timeZone: 'UTC', backup: { destination: 'usb', destinationId: values.backup_destination_id, kitSaved: false } }).then(() => { saved = true; });
  expect(h.save).toHaveBeenCalledWith(values);
  expect(saved).toBe(false);
  expect(h.done).not.toHaveBeenCalled();
  h.get.mockResolvedValueOnce({ ...values, saved: true });
  await act(async () => { release({ ...values, saved: true }); await pending; });
  expect(saved).toBe(true);
  expect(h.done).not.toHaveBeenCalled();
});

it('shows load failure and retries without presenting an empty destination list as real data', async () => {
  h.get.mockReset().mockRejectedValueOnce(new Error('Offline')).mockResolvedValueOnce({ box_name: null, time_zone: null, backup_choice: 'later', backup_destination_id: null, saved: false });
  h.destinations.mockResolvedValue([]);
  render(<FirstRun onDone={() => {}} />);
  expect(await screen.findByRole('alert')).toHaveTextContent('Offline');
  await userEvent.setup().click(screen.getByRole('button', { name: 'Try again' }));
  await waitFor(() => expect(screen.getByText('Existing wizard')).toBeInTheDocument());
});

it('offers the recovery kit only when a destination exists, and the key goes through issue once, unstored', async () => {
  h.get.mockResolvedValue({ ...values, saved: true });
  h.destinations.mockResolvedValue([{ id: values.backup_destination_id, kind: 'usb', label: 'Existing disk' }]);
  h.state.mockResolvedValueOnce({ complete: false, settings_saved: true, backups_enabled: true, destinations: 1, kit: noKit });
  h.issue.mockResolvedValue({ kit: { ...noKit, state: 'issued', positions: [2, 5] }, one_time: { groups: ['AAAA'], check: 'ZZZZ', text: 'KIT TEXT' } });
  h.confirm.mockResolvedValue(undefined);
  render(<FirstRun onDone={h.done} />);
  await screen.findByText('Existing wizard');
  const kit = h.props.kit as { state: string; issue: () => Promise<unknown>; confirm: (a: Record<string, string>) => Promise<void> };
  expect(kit.state).toBe('missing');
  expect(await kit.issue()).toEqual({ groups: ['AAAA'], check: 'ZZZZ', text: 'KIT TEXT', positions: [2, 5] });
  await kit.confirm({ '2': 'AAAA', '5': 'BBBB' });
  expect(h.confirm).toHaveBeenCalledWith({ '2': 'AAAA', '5': 'BBBB' });
  expect(JSON.stringify({ ...window.sessionStorage })).not.toContain('AAAA');
});

it('does not offer a kit without any backup destination', async () => {
  h.get.mockResolvedValue({ ...values, saved: true });
  h.destinations.mockResolvedValue([]);
  render(<FirstRun onDone={h.done} />);
  await screen.findByText('Existing wizard');
  expect(h.props.kit).toBeUndefined();
});

it('previews each starter plan and files the install bound to the previewed plan hash', async () => {
  h.get.mockResolvedValue({ ...values, saved: true });
  h.destinations.mockResolvedValue([]);
  h.request.mockReset().mockResolvedValue({ id: 'a1' });
  const plan = (sha: string) => ({ app_id: 'notes', type: 'app.install', plan: { summary: 'Install Notes' }, plan_sha256: sha, policy_verdict: 'needs_approval', reason: null });
  h.plan.mockReset().mockResolvedValueOnce(plan('sha-1')).mockResolvedValueOnce(plan('sha-1'));
  render(<FirstRun onDone={h.done} />);
  await screen.findByText('Existing wizard');
  expect(await (h.props.previewPlan as (id: string) => Promise<string>)('notes')).toBe('Install Notes');
  const finish = h.props.onFinish as (d: unknown, r: unknown[]) => Promise<void>;
  await act(async () => { await finish({}, [{ type: 'app.install', params: { app_id: 'notes' } }]); });
  expect(h.request).toHaveBeenCalledWith('app.install', 'notes', {}, 'sha-1');
  expect(h.done).toHaveBeenCalled();
});

it('refuses to file an install whose plan changed after the owner saw it', async () => {
  h.get.mockResolvedValue({ ...values, saved: true });
  h.destinations.mockResolvedValue([]);
  h.request.mockReset();
  const plan = (sha: string) => ({ app_id: 'notes', type: 'app.install', plan: { summary: 'Install Notes' }, plan_sha256: sha, policy_verdict: 'needs_approval', reason: null });
  h.plan.mockReset().mockResolvedValueOnce(plan('sha-1')).mockResolvedValueOnce(plan('sha-2'));
  render(<FirstRun onDone={h.done} />);
  await screen.findByText('Existing wizard');
  await (h.props.previewPlan as (id: string) => Promise<string>)('notes');
  await act(async () => { await (h.props.onFinish as (d: unknown, r: unknown[]) => Promise<void>)({}, [{ type: 'app.install', params: { app_id: 'notes' } }]); });
  expect(h.request).not.toHaveBeenCalled();
});

function Probe() {
  const [pending] = useWizardPending();
  return <p>{pending === undefined ? 'asking' : pending ? 'open' : 'closed'}</p>;
}
it.each([
  [{ complete: false }, 'open'],
  [{ complete: true }, 'closed'],
])('the wizard opens from the gateway state %j, with no browser flag', async (state, expected) => {
  window.sessionStorage.setItem('onemind.wizard', '1');
  h.state.mockReset().mockResolvedValue(state);
  render(<Probe />);
  await waitFor(() => expect(screen.getByText(expected)).toBeInTheDocument());
});

it('a refused or failed state read never traps anyone in the wizard', async () => {
  h.state.mockReset().mockRejectedValue(new Error('403'));
  render(<Probe />);
  await waitFor(() => expect(screen.getByText('closed')).toBeInTheDocument());
});

it('files each selected reviewed plan once and refuses an app with no preview', async () => {
  h.state.mockResolvedValue({ complete: false, settings_saved: true, backups_enabled: false, destinations: 0, kit: noKit });
  h.get.mockResolvedValue({ ...values, saved: true });
  h.destinations.mockResolvedValue([]);
  h.request.mockReset().mockResolvedValue({ id: 'a1' });
  h.plan.mockReset().mockImplementation(async (id: string) => ({
    app_id: id, type: 'app.install', plan: { summary: id }, plan_sha256: `sha-${id}`, policy_verdict: 'needs_approval',
  }));
  render(<FirstRun onDone={h.done} />);
  await screen.findByText('Existing wizard');
  const preview = h.props.previewPlan as (id: string) => Promise<string>;
  await preview('notes');
  await preview('photos');
  const finish = h.props.onFinish as (draft: unknown, requests: unknown[]) => Promise<void>;
  await act(async () => {
    await finish({}, ['notes', 'photos', 'unreviewed'].map((app_id) => ({ type: 'app.install', params: { app_id } })));
  });
  expect(h.request.mock.calls).toEqual([
    ['app.install', 'notes', {}, 'sha-notes'],
    ['app.install', 'photos', {}, 'sha-photos'],
  ]);
});

const place = { placeName: 'Rivera Home', address: '12 Orchard Lane', location: { lat: 40.7128, lon: -74.006, source: 'typed' as const } };

it('builds the first site from the place: its name, the owner\'s address text and three grid points', () => {
  expect(firstSite({ ...place, location: undefined })).toBeUndefined();
  const site = firstSite(place)!;
  expect(site).toMatchObject({ id: 'rivera-home', name: 'Rivera Home', address: '12 Orchard Lane', floors: [], areas: [] });
  expect(site.anchors).toHaveLength(3);
  expect(site.anchors[0]).toEqual({ x: 0, y: 0, lat: 40.7128, lon: -74.006 });
  expect(firstSite({ placeName: ' ', address: ' ', location: place.location })).not.toHaveProperty('address');
  expect(firstSite({ placeName: ' ', address: '', location: place.location })).toMatchObject({ id: 'home', name: 'Home' });
  expect(firstSite({ ...place, address: ' Lane\u0000 1\u202e ' })).toMatchObject({ address: 'Lane  1' });
  expect(placeOf('saved', { ...site, anchors: site.anchors.slice(1) })).toEqual({ status: 'saved', name: 'Rivera Home', address: '12 Orchard Lane' });
});

it('ends on the desktop Map when this build has it, otherwise on Approvals or Home', () => {
  expect(landingAfterSetup(2, [{ path: '/map' }, { path: '/approvals' }])).toBe('/map');
  expect(landingAfterSetup(0, [{ path: '/map' }])).toBe('/map');
  expect(landingAfterSetup(2, [{ path: '/approvals' }])).toBe('/approvals');
  expect(landingAfterSetup(0, [{ path: '/approvals' }])).toBe('/');
});

it('saves the place through POST /v1/sites with the owner token, and keeps an existing site as it is', async () => {
  h.get.mockResolvedValue({ ...values, saved: true });
  h.destinations.mockResolvedValue([]);
  const calls: Array<{ url: string; method: string; body: unknown; auth: string | null }> = [];
  const older = { ...firstSite({ ...place, address: 'Old Mill Road', location: { lat: 10.5, lon: 20.25, source: 'typed' } })!, id: 'rivera-home' };
  const replies = [Response.json(firstSite(place), { status: 201 }), Response.json({ error: 'conflict', message: 'Site ID already exists' }, { status: 409 }),
    Response.json([older]),
    Response.json({ error: 'permission_denied', message: 'Only an owner can write map records' }, { status: 403 })];
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const req = new Request(input, init);
    calls.push({ url: new URL(req.url).pathname, method: req.method, body: await req.clone().json().catch(() => undefined), auth: req.headers.get('authorization') });
    return replies.shift()!;
  }));
  try {
    render(<FirstRun onDone={h.done} />);
    await screen.findByText('Existing wizard');
    const saveLocation = h.props.onSaveLocation as (d: unknown) => Promise<unknown>;
    await expect(saveLocation(place)).resolves.toEqual({ status: 'saved', name: 'Rivera Home', address: '12 Orchard Lane', location: { lat: 40.7128, lon: -74.006 } });
    expect(calls[0]).toMatchObject({ url: '/v1/sites', method: 'POST', auth: 'Bearer owner-token', body: firstSite(place) });
    // 409: what is shown is the site already on the box, read back with GET /v1/sites.
    await expect(saveLocation(place)).resolves.toEqual({ status: 'exists', name: 'Rivera Home', address: 'Old Mill Road', location: { lat: 10.5, lon: 20.25 } });
    expect(calls[2]).toMatchObject({ url: '/v1/sites', method: 'GET' });
    await expect(saveLocation(place)).rejects.toThrow('Only an owner can write map records');
    expect(calls).toHaveLength(4);
  } finally {
    vi.unstubAllGlobals();
  }
});
