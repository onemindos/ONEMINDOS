// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';
import { FirstRun } from './FirstRun';

const h = vi.hoisted(() => ({
  get: vi.fn(), save: vi.fn(), destinations: vi.fn(), done: vi.fn(), navigate: vi.fn(),
  props: {} as Record<string, unknown>,
}));
vi.mock('../session', () => {
  const api = { onboardingSettings: h.get, saveOnboardingSettings: h.save, backupDestinations: h.destinations };
  return { useSignedIn: () => ({ api }) };
});
vi.mock('../data/hub', () => ({ useHub: () => ({ apps: { data: [] }, request: vi.fn() }) }));
vi.mock('react-router', () => ({ useNavigate: () => h.navigate }));
vi.mock('@onemind/ui', () => ({
  useToast: () => ({ show: vi.fn() }), applyTheme: vi.fn(),
  Onboarding: (props: Record<string, unknown>) => { h.props = props; return <div>Existing wizard</div>; },
}));
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
