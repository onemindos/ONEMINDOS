// SPDX-License-Identifier: Apache-2.0
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';
import { Onboarding } from './Onboarding';
import { ONBOARDING_STEPS, emptyDraft } from './firstRun';

const BACKUPS = ONBOARDING_STEPS.findIndex((s) => s.id === 'backups');

it('awaits real settings persistence before summary, preserves failures for retry, and never claims protection', async () => {
  const user = userEvent.setup();
  let resolve!: () => void;
  const save = vi.fn().mockRejectedValueOnce(new Error('Hub unavailable')).mockImplementationOnce(() => new Promise<void>((r) => { resolve = r; }));
  const finish = vi.fn();
  render(<Onboarding apps={[]} initialStep={BACKUPS} initial={{ ...emptyDraft('UTC'), boxName: 'home-hub', ownerName: 'Owner', passkey: 'registered', backup: { destination: 'later', kitSaved: false } }} onSaveSettings={save} onFinish={finish} />);
  expect(screen.queryByRole('button', { name: /Download emergency kit/ })).toBeNull();
  await user.click(screen.getByRole('button', { name: /Finish setup/ }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Hub unavailable');
  expect(screen.queryByText('You are all set')).toBeNull();
  await user.click(screen.getByRole('button', { name: /Finish setup/ }));
  expect(screen.getByRole('button', { name: /Saving/ })).toBeDisabled();
  expect(finish).not.toHaveBeenCalled();
  await act(async () => resolve());
  expect(screen.getByRole('heading', { level: 2, name: 'You are all set' })).toBeInTheDocument();
  expect(screen.getByText(/does not enable backups/)).toBeInTheDocument();
  expect(screen.queryByText(/emergency kit saved/)).toBeNull();
  await user.click(screen.getByRole('button', { name: /Go to Home/ }));
  expect(finish).toHaveBeenCalledTimes(1);
});

it('offers only actual matching destinations and clears the binding when the choice changes', async () => {
  const user = userEvent.setup();
  const save = vi.fn().mockResolvedValue(undefined);
  render(<Onboarding apps={[]} initialStep={BACKUPS} initial={{ ...emptyDraft('UTC'), boxName: 'home-hub' }} backupDestinations={[{ id: 'dst_0123456789abcdef', kind: 'usb', label: 'Existing disk' }, { id: 'dst_fedcba9876543210', kind: 's3', label: 'Bucket' }]} onSaveSettings={save} onFinish={() => {}} />);
  await user.selectOptions(screen.getByLabelText('Existing backup destination'), 'dst_0123456789abcdef');
  expect(screen.queryByRole('option', { name: 'Bucket' })).toBeNull();
  await user.click(screen.getByRole('radio', { name: /Decide later/ }));
  await user.click(screen.getByRole('button', { name: /Finish setup/ }));
  expect(save).toHaveBeenCalledWith(expect.objectContaining({ backup: { destination: 'later', destinationId: undefined, kitSaved: false } }));
});

it('a wizard opened with an issued, unconfirmed kit can still skip it and finish, or re-issue', async () => {
  const user = userEvent.setup();
  const save = vi.fn().mockResolvedValue(undefined);
  const finish = vi.fn();
  const issue = vi.fn().mockResolvedValue({ groups: ['ABCD', 'EFGH', 'JKLM'], check: 'QRST', text: 'KIT', positions: [1, 3] });
  const kit = { state: 'issued' as const, positions: [2, 4], issue, confirm: vi.fn() };
  render(<Onboarding apps={[]} initialStep={BACKUPS} initial={{ ...emptyDraft('UTC'), boxName: 'home-hub', ownerName: 'Owner', passkey: 'registered', backup: { destination: 'later', kitSaved: false } }} kit={kit} onSaveSettings={save} onFinish={finish} />);
  await user.click(screen.getByRole('button', { name: /Finish setup/ }));
  expect(screen.getByRole('alert')).toHaveTextContent('Create and confirm your emergency kit first');
  await user.click(screen.getByRole('button', { name: /I lost my copy/ }));
  expect(await screen.findByLabelText('Owner recovery key')).toBeInTheDocument();
  expect(issue).toHaveBeenCalledTimes(1);
  await user.click(screen.getByRole('button', { name: 'Skip for now' }));
  await user.click(screen.getByRole('button', { name: /Finish setup/ }));
  expect(await screen.findByRole('heading', { level: 2, name: 'You are all set' })).toBeInTheDocument();
  expect(screen.getByText(/skipped for now/)).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: /Go to Home/ }));
  expect(finish).toHaveBeenCalledTimes(1);
});
