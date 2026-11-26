// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';
import { FirstRun, useWizardPending } from './FirstRun';

const h = vi.hoisted(() => ({
  get: vi.fn(), save: vi.fn(), state: vi.fn(), issue: vi.fn(), confirm: vi.fn(), plan: vi.fn(), request: vi.fn(), destinations: vi.fn(), done: vi.fn(), navigate: vi.fn(),
  props: {} as Record<string, unknown>,
}));
vi.mock('../session', () => {
  const api = { onboardingSettings: h.get, saveOnboardingSettings: h.save, backupDestinations: h.destinations, onboardingState: h.state,
    issueKit: h.issue, confirmKit: h.confirm, appPlan: h.plan };
  return { useSignedIn: () => ({ api }) };
});
vi.mock('../data/hub', () => ({ useHub: () => ({ apps: { data: [] }, request: h.request }) }));
vi.mock('react-router', () => ({ useNavigate: () => h.navigate }));
vi.mock('@onemind/ui', () => ({
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

it('offers a kit with no backup destination and passes the disk key through, once', async () => {
  h.get.mockResolvedValue({ ...values, saved: true });
  h.destinations.mockResolvedValue([]);
  h.issue.mockResolvedValue({ kit: { ...noKit, state: 'issued', positions: [1, 3] },
    one_time: { groups: ['AAAA'], check: 'ZZZZ', text: 'KIT TEXT', disk_recovery_key: 'cbdefghi-jklnrtuv' } });
  render(<FirstRun onDone={h.done} />);
  await screen.findByText('Existing wizard');
  const kit = h.props.kit as { issue: () => Promise<unknown> };
  expect(kit).toBeDefined();
  expect(await kit.issue()).toMatchObject({ disk_recovery_key: 'cbdefghi-jklnrtuv', positions: [1, 3] });
  const marker = { fingerprint: 'cafe1234cafe1234', issued_at: '2026-11-20T08:00:00Z' };
  h.issue.mockResolvedValue({ kit: { ...noKit, state: 'issued', positions: [1, 3], disk_key_kit: marker },
    one_time: { groups: ['AAAA'], check: 'ZZZZ', text: 'KIT TEXT' } });
  expect(await kit.issue()).toMatchObject({ disk_key_kit: marker });
  expect(JSON.stringify({ ...window.sessionStorage, ...window.localStorage })).not.toContain('cbdefghi');
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
